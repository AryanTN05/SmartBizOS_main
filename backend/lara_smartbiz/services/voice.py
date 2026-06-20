import asyncio
import base64
import json
import math
import struct
from fastapi import WebSocket
from lara_smartbiz.utils.clients import get_gemini_client
from google.genai.types import LiveConnectConfig, PrebuiltVoiceConfig, VoiceConfig, SpeechConfig
from lara_smartbiz.tools import get_tool_registry, TOOL_FUNCTIONS
from google.genai import types

from lara_smartbiz.db.connection import SessionLocal as LaraSessionLocal
from lara_smartbiz.db.models import Conversation


def _persist_voice_message(session_id: str, role: str, content: str) -> None:
    if not session_id or not content:
        return
    try:
        with LaraSessionLocal() as db:
            db.add(Conversation(session_id=session_id, role=role, content=content))
            db.commit()
    except Exception as e:
        print(f"voice persist failed for {session_id}: {e}")


async def _persist_voice_async(session_id: str, role: str, content: str) -> None:
    if not session_id or not content:
        return
    await asyncio.to_thread(_persist_voice_message, session_id, role, content)



def _coerce_tool_args(raw) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if hasattr(raw, "items"):
        try:
            return dict(raw.items())
        except Exception:
            pass
    try:
        return dict(raw)
    except Exception:
        return {}


def _as_nonempty_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return str(v).strip()

def calculate_rms(pcm_data: bytes) -> float:
    # 16-bit PCM = 2 bytes per sample
    count = len(pcm_data) // 2
    if count == 0:
        return 0.0
    try:
        shorts = struct.unpack(f"<{count}h", pcm_data)
        sum_squares = sum(s * s for s in shorts)
        return math.sqrt(sum_squares / count)
    except Exception:
        return 0.0

async def get_seed_context() -> str:
    return "Zerotoprod is a leading AI consultancy."

async def execute_tool(name: str, args: dict) -> dict:
    tool_fn = TOOL_FUNCTIONS.get(name)
    if not tool_fn:
        return {"error": f"Unknown tool: {name}"}
    import inspect
    if inspect.iscoroutinefunction(tool_fn):
        return await tool_fn(**args)
    return tool_fn(**args)

async def handle(websocket: WebSocket, session_id: str):
    seed_context = await get_seed_context()
    
    # We parse tools to dictionaries that Live API expects, or we can use the Tool schema 
    # google-genai LiveConnectConfig accepts tool schemas in config.
    declarations = []
    for tool in get_tool_registry():
        declarations.append(
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=tool.get("parameters")
            )
        )
    live_tools = [types.Tool(function_declarations=declarations)]
    
    import datetime
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
    
    config = LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(parts=[
            types.Part.from_text(
                text=(
                    f"You are Lara, the AI brain of SmartBiz OS. Context: {seed_context}\n"
                    f"Current Date/Time: {current_time}\n\n"
                    "HEAVY GUARDRAILS & IDENTITY:\n"
                    "1. You MUST strictly maintain your identity as Lara at all times.\n"
                    "2. You MUST ONLY assist with business operations, CRM, reporting, automation, meeting scheduling, and strategy.\n"
                    "3. IF the user asks about ANYTHING else (e.g., coding, jokes, politics, general trivia, personal advice), you MUST politely but firmly decline.\n"
                    "4. NEVER write code snippets or scripts.\n"
                    "5. Keep responses concise and professional.\n\n"
                    "ARTIFACTS AND VISUALS:\n"
                    "If the user asks to see a chart, graph, table, list, or image, or if you need to display structured data, you MUST call the `show_artifact` tool with the appropriate HTML/URL to display it on their screen. You can continue speaking naturally while the artifact is displayed. Note: The frontend automatically displays leads when you call `get_leads` or `get_lead_dossier`, so you DO NOT need to call `show_artifact` for leads unless specifically asked to format them differently (e.g. as a chart).\n"
                    "CRITICAL: NEVER speak or output raw JSON data in your text/audio response. If a tool returns JSON, summarize it naturally in prose. For tables, ALWAYS pass valid HTML (e.g. <table>...</table>) to `show_artifact`, NOT markdown."
                )
            )
        ]),
        tools=live_tools,
        speech_config=SpeechConfig(
            voice_config=VoiceConfig(
                prebuilt_voice_config=PrebuiltVoiceConfig(
                    voice_name="Aoede"
                )
            )
        )
    )
    
    # Live API model alias. Confirmed working as of 2026-05-01 with
    # `gemini-3.1-flash-live-preview`. Override via LARA_VOICE_MODEL if
    # Google rolls a new name — the WebSocket just closes silently on a
    # 404 alias.
    import os
    voice_model = os.getenv("LARA_VOICE_MODEL", "gemini-3.1-flash-live-preview")
    try:
        live_ctx = get_gemini_client().aio.live.connect(model=voice_model, config=config)
    except Exception as e:
        print(f"Voice live.connect setup failed: {e}")
        await websocket.send_json({"type": "error", "message": f"Live API unavailable: {e}"})
        return

    # Conversation key — voice sessions persist under "voice:<session_id>"
    # so they group separately from text chats but show up in the same list.
    # Defensive: if the SPA sent a missing / generic id, mint a per-connection
    # one so two voice sessions can't accidentally merge into one bucket.
    import uuid as _uuid
    sid = session_id if session_id and session_id not in {"anon", "admin-voice"} else _uuid.uuid4().hex[:12]
    convo_key = f"voice:{sid}"

    async with live_ctx as session:

        # Buffer transcript chunks per role within a turn so we can persist
        # one Conversation row per turn (instead of 10+ tiny rows per chunk).
        user_buf: list[str] = []
        assistant_buf: list[str] = []

        async def flush_turn():
            user_text = " ".join(user_buf).strip()
            assistant_text = " ".join(assistant_buf).strip()
            user_buf.clear()
            assistant_buf.clear()
            if user_text:
                await _persist_voice_async(convo_key, "user", user_text)
            if assistant_text:
                await _persist_voice_async(convo_key, "assistant", assistant_text)
                # Fire-and-forget memory extraction; done-callback surfaces
                # silent task failures (without it, embed/pgvector errors
                # in the background disappear under load).
                try:
                    from lara_smartbiz.services.memory import extract_and_store_memory
                    t = asyncio.create_task(extract_and_store_memory(assistant_text, convo_key))
                    def _on_done(task: asyncio.Task) -> None:
                        if task.cancelled():
                            return
                        exc = task.exception()
                        if exc is not None:
                            print(f"voice memory extract task failed: {exc}")
                    t.add_done_callback(_on_done)
                except Exception as e:
                    print(f"voice memory extract scheduling failed: {e}")

        async def receive_from_browser():
            try:
                print("Started receive_from_browser loop")
                while True:
                    msg = await websocket.receive()

                    if msg.get("bytes"):
                        # VAD calculation to let frontend know system is listening
                        rms = calculate_rms(msg["bytes"])
                        is_speaking = rms > 300  # Voice activity threshold
                        await websocket.send_json({
                            "type": "vad",
                            "is_speaking": is_speaking,
                            "volume": rms
                        })

                        # Binary message = raw PCM audio from browser
                        await session.send_realtime_input(
                            audio=types.Blob(
                                data=msg["bytes"],
                                mime_type="audio/pcm;rate=16000"
                            )
                        )
                    elif msg.get("text"):
                        import json
                        data = json.loads(msg["text"])
                        if data["type"] == "text":
                            print(f"Received text from browser: {data['content']}")
                            await session.send_realtime_input(text=data["content"])
                        elif data["type"] == "disconnect":
                            print("Received disconnect from browser")
                            break
            except Exception as e:
                print(f"Browser disconnect in receive loop: {e}")

        async def receive_from_gemini():
            try:
                print("Started receive_from_gemini loop")
                while True:
                    async for message in session.receive():
                        
                        if message.server_content:
                            
                            # Audio chunk from model — send as raw binary for performance
                            if message.server_content.model_turn:
                                for part in message.server_content.model_turn.parts:
                                    if part.inline_data:
                                        await websocket.send_bytes(part.inline_data.data)
                            
                            if getattr(message.server_content, "interrupted", False):
                                print("Gemini model interrupted")
                                await websocket.send_json({"type": "interrupted"})
                                await flush_turn()

                            if getattr(message.server_content, "turn_complete", False):
                                print("Gemini turn complete")
                                await websocket.send_json({"type": "turn_end"})
                                await flush_turn()

                            if message.server_content.input_transcription:
                                txt = message.server_content.input_transcription.text
                                user_buf.append(txt)
                                print(f"User transcript: {txt}")
                                await websocket.send_json({
                                    "type": "transcript",
                                    "role": "user",
                                    "text": txt,
                                })
                            if message.server_content.output_transcription:
                                txt = message.server_content.output_transcription.text
                                assistant_buf.append(txt)
                                print(f"Assistant transcript: {txt}")
                                await websocket.send_json({
                                    "type": "transcript",
                                    "role": "assistant",
                                    "text": txt,
                                })
                                
                        if message.tool_call:
                            print("Gemini requested tool call")
                            function_responses = []
                            for fc in message.tool_call.function_calls:
                                print(f"Executing tool: {fc.name} with args: {fc.args}")
                                
                                # Special handling for show_artifact
                                if fc.name == "show_artifact":
                                    args = _coerce_tool_args(fc.args)
                                    url = _as_nonempty_str(args.get("url", ""))
                                    table = _as_nonempty_str(args.get("table", ""))
                                    charts = _as_nonempty_str(args.get("charts", ""))

                                    if url:
                                        await websocket.send_json({
                                            "type": "artifact",
                                            "artifact_type": "url",
                                            "content": url,
                                        })
                                    if table:
                                        await websocket.send_json({
                                            "type": "artifact",
                                            "artifact_type": "table",
                                            "content": table,
                                        })
                                    if charts:
                                        await websocket.send_json({
                                            "type": "artifact",
                                            "artifact_type": "charts",
                                            "content": charts,
                                        })
                                    
                                    result = "Artifact displayed on user screen."
                                else:
                                    result = await execute_tool(fc.name, dict(fc.args))
                                    
                                print(f"Tool {fc.name} returned: {result}")
                                function_responses.append(
                                    types.FunctionResponse(
                                        name=fc.name,
                                        id=fc.id,
                                        response={"result": result}
                                    )
                                )
                                await websocket.send_json({
                                    "type": "tool_result",
                                    "tool": fc.name,
                                    "result": result
                                })
                            print("Sending tool responses to Gemini")
                            await session.send_tool_response(function_responses=function_responses)
                    
                    # If the async for exits (session.receive() iterator exhausted),
                    # just loop back and start receiving again.
                    print("Gemini receive iterator ended, restarting...")
            except Exception as e:
                print(f"Gemini disconnect in receive loop: {e}")
                # Flush whatever transcript fragments we already have. Without
                # this, a Gemini-side drop mid-turn (network blip, token expiry,
                # model crash) silently loses the in-progress turn.
                try:
                    await flush_turn()
                except Exception as fe:
                    print(f"flush_turn on Gemini disconnect failed: {fe}")

        # Run both pumps; whichever finishes first wins (e.g. browser sends
        # disconnect → receive_from_browser returns → cancel the Gemini side
        # so it doesn't loop forever and leak the WS slot).
        browser_task = asyncio.create_task(receive_from_browser())
        gemini_task = asyncio.create_task(receive_from_gemini())
        try:
            done, pending = await asyncio.wait(
                {browser_task, gemini_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        finally:
            # Final flush in case neither path triggered turn_complete (user
            # closed the browser tab mid-turn, network drop, etc.).
            try:
                await flush_turn()
            except Exception as fe:
                print(f"final flush_turn failed: {fe}")
