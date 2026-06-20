import { useCallback, useEffect, useRef, useState } from 'react';

// Hook for the /lara-smartbiz/voice WebSocket session.
// State machine: idle → connecting → listening → … → idle.
//
// Captures mic via getUserMedia, downsamples to 16kHz mono 16-bit PCM,
// streams to the server as binary frames. Receives 24kHz PCM back and
// schedules it through a single AudioContext queue for gap-less playback.
//
// JSON events (vad / transcript / turn_end / interrupted / tool_result /
// artifact / error) are surfaced via the returned `events` array.

const TARGET_RATE = 16000;       // Gemini Live API expects 16kHz mic input
const PLAYBACK_RATE = 24000;     // ...and emits 24kHz output

function downsampleToInt16(input, inputRate, targetRate) {
  if (inputRate === targetRate) {
    const out = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1, Math.min(1, input[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }
  const ratio = inputRate / targetRate;
  const length = Math.floor(input.length / ratio);
  const out = new Int16Array(length);
  for (let i = 0; i < length; i++) {
    const idx = Math.floor(i * ratio);
    const s = Math.max(-1, Math.min(1, input[idx]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

export function useVoiceSession() {
  const [state, setState] = useState('idle');     // idle | connecting | listening | error
  const [activity, setActivity] = useState('quiet'); // quiet | user-speaking | lara-speaking
  const [error, setError] = useState(null);
  const [events, setEvents] = useState([]);  // transcript / artifact / tool_result events
  const [volume, setVolume] = useState(0);   // real-time VAD volume (RMS) from server

  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const audioCtxRef = useRef(null);
  const sourceNodeRef = useRef(null);
  const scriptNodeRef = useRef(null);
  const playbackCtxRef = useRef(null);
  const playbackTimeRef = useRef(0);
  // Track every in-flight BufferSource so a barge-in interrupt can call
  // .stop() on each to flush the queue. Without this, audio Gemini already
  // emitted (and we already scheduled) keeps playing for the next few
  // hundred ms after the user starts talking, masking the cut-off.
  const playingNodesRef = useRef(new Set());

  const stop = useCallback(() => {
    try { wsRef.current?.send(JSON.stringify({ type: 'disconnect' })); } catch (_) {}
    try { wsRef.current?.close(); } catch (_) {}
    wsRef.current = null;
    try { scriptNodeRef.current?.disconnect(); } catch (_) {}
    try { sourceNodeRef.current?.disconnect(); } catch (_) {}
    scriptNodeRef.current = null;
    sourceNodeRef.current = null;
    // Stop any still-scheduled playback so closing the session is silent.
    for (const node of playingNodesRef.current) {
      try { node.stop(); } catch (_) {}
    }
    playingNodesRef.current.clear();
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    try { audioCtxRef.current?.close(); } catch (_) {}
    audioCtxRef.current = null;
    try { playbackCtxRef.current?.close(); } catch (_) {}
    playbackCtxRef.current = null;
    playbackTimeRef.current = 0;
    setState('idle');
    setActivity('quiet');
    setVolume(0);
  }, []);

  const start = useCallback(async () => {
    if (wsRef.current) return;
    setError(null);
    setEvents([]);
    setState('connecting');

    // Create + resume the playback AudioContext NOW, inside the click
    // handler. Browsers require a user gesture to unlock audio output;
    // creating it later in the WS message handler leaves it suspended
    // (silent assistant audio).
    const Ctx = window.AudioContext || window.webkitAudioContext;
    try {
      const playCtx = new Ctx({ sampleRate: PLAYBACK_RATE });
      // Force-resume: some browsers create suspended even from a gesture.
      if (playCtx.state === 'suspended') await playCtx.resume();
      playbackCtxRef.current = playCtx;
      playbackTimeRef.current = playCtx.currentTime;
    } catch (e) {
      setError({ code: 'audio_unavailable', message: 'Browser audio context unavailable' });
      setState('error');
      return;
    }

    let stream;
    try {
      // Don't constrain sampleRate — Chrome silently produces zero buffers
      // when the requested rate doesn't match the device. We downsample in
      // JS using the actual ctx.sampleRate. Echo/noise/AGC defaults left
      // to the browser; explicit `false` for AGC kept as a guard against
      // silent-mic situations in quiet rooms.
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: false,
        },
        video: false,
      });
    } catch (e) {
      setError({ code: 'mic_denied', message: e.message || 'Microphone permission denied' });
      setState('error');
      try { playbackCtxRef.current?.close(); } catch (_) {}
      playbackCtxRef.current = null;
      return;
    }
    streamRef.current = stream;

    // Open WS *after* mic permission so a denial doesn't leave a half-open socket.
    //
    // Host resolution mirrors lib/api.js: if VITE_API_BASE_URL is set (prod
    // build pointing at a separate backend host, e.g. Vercel → Render), use
    // that host directly. Otherwise fall back to window.location.host so dev
    // (Vite proxy) and same-origin deploys still work. Without this the WS
    // hits the static-host domain (Vercel), which doesn't proxy WebSockets,
    // and the voice path 404s in prod.
    const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE_URL) || '';
    let wsHost, wsProto;
    if (apiBase) {
      const u = new URL(apiBase);
      wsHost = u.host;
      wsProto = u.protocol === 'https:' ? 'wss:' : 'ws:';
    } else {
      wsHost = window.location.host;
      wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    }
    // Mint a fresh session id per voice attempt. The previous hardcoded
    // "admin-voice" merged every voice transcript into one DB bucket.
    const voiceSessionId = (typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `voice-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`);
    const url = `${wsProto}//${wsHost}/lara-smartbiz/voice?session_id=${voiceSessionId}`;
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      setError({ code: 'ws_open_failed', message: e.message || 'Could not open voice socket' });
      setState('error');
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.addEventListener('open', () => {
      setState('listening');
    });

    ws.addEventListener('error', () => {
      setError({ code: 'ws_error', message: 'Voice socket error' });
      setState('error');
    });

    ws.addEventListener('close', () => {
      // Don't tear down here if we're already idle; closes can race with stop().
      if (wsRef.current === ws) stop();
    });

    ws.addEventListener('message', (ev) => {
      if (ev.data instanceof ArrayBuffer) {
        setActivity('lara-speaking');
        playPCM(ev.data);
        return;
      }
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'vad') {
          setVolume(msg.volume || 0);
          if (msg.is_speaking) setActivity('user-speaking');
          return;
        }
        if (msg.type === 'turn_end') setActivity('quiet');
        if (msg.type === 'interrupted') {
          // Yank the still-playing audio queue so the user's barge-in
          // actually cuts Gemini off (otherwise pre-buffered chunks keep
          // talking for ~500ms after the model has stopped emitting).
          flushPlayback();
          setActivity('user-speaking');
        }
        setEvents((prev) => [...prev, msg]);
      } catch (_) { /* non-JSON text */ }
    });

    // Set up mic capture pipeline (separate context — input runs at the
    // device's native rate, we downsample to TARGET_RATE before sending).
    const ctx = new Ctx();
    if (ctx.state === 'suspended') {
      try { await ctx.resume(); } catch (_) { /* best-effort */ }
    }
    audioCtxRef.current = ctx;
    const source = ctx.createMediaStreamSource(stream);
    sourceNodeRef.current = source;
    // ScriptProcessor is deprecated but works everywhere and avoids the
    // async AudioWorklet bootstrapping. 4096 samples ≈ 256ms at 16kHz.
    const bufferSize = 4096;
    const node = ctx.createScriptProcessor(bufferSize, 1, 1);
    scriptNodeRef.current = node;

    node.onaudioprocess = (e) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      const input = e.inputBuffer.getChannelData(0);
      const pcm = downsampleToInt16(input, ctx.sampleRate, TARGET_RATE);
      try { wsRef.current.send(pcm.buffer); } catch (_) { /* socket closed mid-tick */ }
    };

    source.connect(node);
    // ScriptProcessor needs to be connected to the destination to fire onaudioprocess.
    // Route through a muted gain so we don't echo the user's mic locally.
    const mute = ctx.createGain();
    mute.gain.value = 0;
    node.connect(mute);
    mute.connect(ctx.destination);
  }, [stop]);

  // Schedule incoming PCM at PLAYBACK_RATE on a single timeline.
  // playbackCtxRef is set up inside start() so we know it's been unlocked
  // by the click gesture; if it's somehow missing, bail rather than
  // creating a suspended one from this WS-message context.
  const playPCM = useCallback((arrayBuffer) => {
    const ctx = playbackCtxRef.current;
    if (!ctx) return;
    if (ctx.state === 'suspended') ctx.resume().catch(() => {});
    const view = new DataView(arrayBuffer);
    const sampleCount = arrayBuffer.byteLength / 2;
    if (sampleCount === 0) return;
    const buf = ctx.createBuffer(1, sampleCount, PLAYBACK_RATE);
    const channel = buf.getChannelData(0);
    for (let i = 0; i < sampleCount; i++) {
      channel[i] = view.getInt16(i * 2, true) / 0x8000;
    }
    const node = ctx.createBufferSource();
    node.buffer = buf;
    node.connect(ctx.destination);
    const startAt = Math.max(playbackTimeRef.current, ctx.currentTime);
    node.start(startAt);
    playbackTimeRef.current = startAt + buf.duration;
    // Track this source so we can yank it out on barge-in.
    playingNodesRef.current.add(node);
    node.onended = () => playingNodesRef.current.delete(node);
  }, []);

  // Stop every scheduled BufferSource immediately. Called on `interrupted`
  // so a user barge-in cuts Gemini's voice mid-word.
  const flushPlayback = useCallback(() => {
    for (const node of playingNodesRef.current) {
      try { node.stop(); } catch (_) { /* already finished */ }
    }
    playingNodesRef.current.clear();
    if (playbackCtxRef.current) {
      playbackTimeRef.current = playbackCtxRef.current.currentTime;
    }
  }, []);

  // Cleanup on real unmount only. React.StrictMode (dev) mounts → unmounts →
  // remounts components, which would otherwise tear down a fresh-but-not-yet-
  // started session and produce the WS rapid-open/close pattern in the server
  // log. Guarding on `wsRef.current` means we only call stop() if a session
  // was actually live.
  useEffect(() => () => { if (wsRef.current) stop(); }, [stop]);

  return { state, activity, error, events, volume, start, stop };
}
