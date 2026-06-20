import React, { useEffect, useMemo, useRef, useState } from 'react';
import { SBButton, SBChip, SBIcon } from '../../../components/primitives';
import api from '../../../lib/api.js';
import { toast } from '../../leads/lib/toast.jsx';
import { ARCHETYPES, archetypeByKey } from '../icpTemplates.js';

// 3-step ICP wizard. Replaces the blank textarea on /admin/settings when
// icp_description is empty (or when the user clicks "Re-run wizard" later).
//
// Step 1 — product URL + 1-line tagline
// Step 2 — pick from 6 archetype templates (one is "start blank")
// Step 3 — drafted ICP shown in editable textarea, save closes the wizard
//
// Pure frontend — no new backend. Templates assemble client-side, save uses
// the existing PATCH /api/workspace/settings.
//
// Aesthetic: matches the rest of the app (terminal mono + cyan accents)
// but layered with a step ribbon, archetype cards, and a typewriter-style
// reveal of the drafted text on step 3 to make the moment feel alive.

const STEPS = [
  { n: 1, label: 'About you',     hint: 'Two questions, 30 seconds.' },
  { n: 2, label: 'Pick a shape',  hint: 'We start from the right archetype.' },
  { n: 3, label: 'Tune it',       hint: 'Edit, then save. You can re-run later.' },
];

export default function IcpWizard({ initialIcp = '', onSaved, onCancel }) {
  const [step, setStep] = useState(1);
  const [url, setUrl] = useState('');
  const [tagline, setTagline] = useState('');
  const [archetypeKey, setArchetypeKey] = useState(null);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [revealLen, setRevealLen] = useState(0); // typewriter cursor

  // When step 3 mounts (or archetype changes mid-wizard), build the draft
  // and reveal it character-by-character. If the user already had an ICP
  // saved, we skip the typewriter and just show their text.
  const targetDraft = useMemo(() => {
    if (!archetypeKey) return '';
    return archetypeByKey(archetypeKey).draft({ url: url.trim(), tagline: tagline.trim() });
  }, [archetypeKey, url, tagline]);

  useEffect(() => {
    if (step !== 3) return;
    // If user is editing an existing ICP, prefill that instead of re-drafting.
    if (initialIcp && draft === '') {
      setDraft(initialIcp);
      setRevealLen(initialIcp.length);
      return;
    }
    setDraft(targetDraft);
    setRevealLen(0);
  }, [step]);

  // Typewriter reveal — only fires for fresh drafts (not edits of existing).
  useEffect(() => {
    if (step !== 3) return;
    if (revealLen >= draft.length) return;
    const id = setTimeout(() => setRevealLen((n) => Math.min(n + 4, draft.length)), 12);
    return () => clearTimeout(id);
  }, [step, revealLen, draft]);

  const canAdvanceFrom1 = url.trim().length > 0 || tagline.trim().length > 0;
  const canAdvanceFrom2 = !!archetypeKey;

  const next = () => {
    if (step === 1 && !canAdvanceFrom1) return;
    if (step === 2 && !canAdvanceFrom2) return;
    setStep((s) => Math.min(3, s + 1));
  };
  const back = () => setStep((s) => Math.max(1, s - 1));

  const save = async () => {
    setSaving(true);
    try {
      await api.patch('/api/workspace/settings', {
        icp_description: draft.trim(),
      });
      toast.success('ICP saved · scoring will use this on next enrichment');
      onSaved?.(draft.trim());
    } catch (err) {
      toast.error(err?.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={card}>
      {/* Header — step ribbon */}
      <div style={ribbon}>
        <div className="sb-label" style={{ color: 'var(--sb-accent)' }}>Workspace · ICP wizard</div>
        <div style={{ flex: 1 }} />
        {onCancel && (
          <button onClick={onCancel} style={cancelBtn} title="Close wizard">
            <SBIcon name="close" size={12} />
          </button>
        )}
      </div>

      <Stepper step={step} />

      {/* Body */}
      <div style={body}>
        {step === 1 && (
          <Step1
            url={url} setUrl={setUrl}
            tagline={tagline} setTagline={setTagline}
          />
        )}
        {step === 2 && (
          <Step2
            picked={archetypeKey}
            onPick={(key) => { setArchetypeKey(key); }}
          />
        )}
        {step === 3 && (
          <Step3
            draft={draft}
            setDraft={(v) => { setDraft(v); setRevealLen(v.length); }}
            revealLen={revealLen}
            archetypeLabel={archetypeKey ? archetypeByKey(archetypeKey).label : ''}
          />
        )}
      </div>

      {/* Footer — nav */}
      <div style={footer}>
        <SBButton variant="ghost" size="sm"
          onClick={back} disabled={step === 1 || saving}>
          Back
        </SBButton>
        <div style={{ flex: 1 }} />
        {step < 3 ? (
          <SBButton
            variant="primary" size="sm" iconRight="arrow"
            disabled={(step === 1 && !canAdvanceFrom1) || (step === 2 && !canAdvanceFrom2)}
            onClick={next}
          >
            {step === 1 ? 'Pick an archetype' : 'See the draft'}
          </SBButton>
        ) : (
          <SBButton
            variant="primary" size="sm" icon="check"
            onClick={save} disabled={saving || !draft.trim()}
          >
            {saving ? 'Saving…' : 'Save ICP'}
          </SBButton>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Steps
// ─────────────────────────────────────────────────────────────────────────────

function Step1({ url, setUrl, tagline, setTagline }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Question
        n="01"
        title="Where does your product live?"
        sub="Your URL anchors the draft to your actual buyer language."
      >
        <Input
          value={url}
          onChange={setUrl}
          placeholder="https://yourproduct.com"
          mono
        />
      </Question>
      <Question
        n="02"
        title="What does it do, in one line?"
        sub="Plain language. The way you'd describe it to a smart friend at dinner."
      >
        <Input
          value={tagline}
          onChange={setTagline}
          placeholder="e.g. AI-powered RevOps for Indian SaaS startups"
        />
      </Question>
    </div>
  );
}

function Step2({ picked, onPick }) {
  return (
    <div>
      <div style={{ marginBottom: 14, fontSize: 12, color: 'var(--sb-fg-4)', lineHeight: 1.55 }}>
        Pick the archetype closest to your buyer. We'll seed a draft you can edit on the next step.
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10,
      }}>
        {ARCHETYPES.map((a) => (
          <ArchetypeCard
            key={a.key}
            arch={a}
            picked={picked === a.key}
            onClick={() => onPick(a.key)}
          />
        ))}
      </div>
    </div>
  );
}

function Step3({ draft, setDraft, revealLen, archetypeLabel }) {
  const visibleDraft = draft.slice(0, revealLen);
  const isStillRevealing = revealLen < draft.length;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        fontSize: 11.5, color: 'var(--sb-fg-5)',
      }}>
        <SBChip tone="muted">{archetypeLabel}</SBChip>
        <span style={{ fontFamily: 'var(--sb-font-mono)' }}>· drafted · edit freely</span>
      </div>
      <div style={{ position: 'relative' }}>
        <textarea
          value={isStillRevealing ? visibleDraft : draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={11}
          spellCheck={false}
          maxLength={4000}
          style={{
            width: '100%', boxSizing: 'border-box',
            background: 'var(--sb-panel)', color: 'var(--sb-fg)',
            border: '1px solid var(--sb-line-2)',
            padding: '14px 16px', fontSize: 13,
            fontFamily: 'var(--sb-font-mono)', lineHeight: 1.7,
            resize: 'vertical', outline: 'none',
            caretColor: 'var(--sb-accent)',
          }}
        />
        {isStillRevealing && (
          <span style={{
            position: 'absolute', right: 16, top: 14,
            fontSize: 10, color: 'var(--sb-accent)', fontFamily: 'var(--sb-font-mono)',
            letterSpacing: '0.1em', textTransform: 'uppercase',
          }}>typing…</span>
        )}
      </div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', fontSize: 10.5,
        color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
      }}>
        <span>edit lines, keep what's useful, drop what isn't</span>
        <span>{draft.length} / 4000</span>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function Stepper({ step }) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0,
      borderTop: '1px solid var(--sb-line)',
      borderBottom: '1px solid var(--sb-line)',
    }}>
      {STEPS.map((s) => {
        const active = s.n === step;
        const done = s.n < step;
        return (
          <div key={s.n} style={{
            padding: '12px 16px',
            borderRight: s.n < 3 ? '1px solid var(--sb-line)' : 'none',
            background: active ? 'var(--sb-card)' : 'transparent',
            transition: 'background 180ms',
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <div style={{
              width: 24, height: 24, flexShrink: 0,
              fontFamily: 'var(--sb-font-mono)', fontSize: 11, fontWeight: 600,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: `1px solid ${active ? 'var(--sb-accent)' : done ? 'var(--sb-accent)' : 'var(--sb-line-2)'}`,
              color: active ? 'var(--sb-accent)' : done ? 'var(--sb-accent)' : 'var(--sb-fg-5)',
              background: done ? 'var(--sb-accent-bg)' : 'transparent',
            }}>
              {done ? <SBIcon name="check" size={11} /> : s.n}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{
                fontSize: 12, fontWeight: 600,
                color: active ? 'var(--sb-fg)' : 'var(--sb-fg-4)',
                lineHeight: 1.2,
              }}>
                {s.label}
              </div>
              <div style={{
                fontSize: 10.5, color: 'var(--sb-fg-5)',
                fontFamily: 'var(--sb-font-mono)', marginTop: 2,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {s.hint}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Question({ n, title, sub, children }) {
  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 4,
      }}>
        <span style={{
          fontFamily: 'var(--sb-font-mono)', fontSize: 11,
          color: 'var(--sb-accent)', letterSpacing: '0.16em',
        }}>{n}</span>
        <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--sb-fg)' }}>
          {title}
        </div>
      </div>
      <div style={{
        fontSize: 12, color: 'var(--sb-fg-4)', lineHeight: 1.55,
        marginLeft: 26, marginBottom: 10,
      }}>{sub}</div>
      <div style={{ marginLeft: 26 }}>{children}</div>
    </div>
  );
}

function Input({ value, onChange, placeholder, mono }) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        width: '100%', boxSizing: 'border-box',
        padding: '10px 12px',
        background: 'var(--sb-panel)', color: 'var(--sb-fg)',
        border: '1px solid var(--sb-line-2)',
        fontSize: 13.5,
        fontFamily: mono ? 'var(--sb-font-mono)' : 'var(--sb-font)',
        outline: 'none',
      }}
    />
  );
}

function ArchetypeCard({ arch, picked, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: picked ? 'var(--sb-accent-bg)' : 'var(--sb-card)',
        border: `1px solid ${picked ? 'var(--sb-accent)' : 'var(--sb-line)'}`,
        padding: '14px 14px 12px',
        textAlign: 'left',
        cursor: 'pointer',
        transition: 'all 140ms',
        display: 'flex', flexDirection: 'column', gap: 6,
        position: 'relative',
        outline: 'none',
      }}
      onMouseEnter={(e) => {
        if (!picked) e.currentTarget.style.borderColor = 'var(--sb-line-2)';
      }}
      onMouseLeave={(e) => {
        if (!picked) e.currentTarget.style.borderColor = 'var(--sb-line)';
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          color: picked ? 'var(--sb-accent)' : 'var(--sb-fg-3)',
        }}>
          <SBIcon name={arch.icon} size={14} stroke={1.4} />
        </span>
        <span style={{
          fontSize: 13, fontWeight: 600,
          color: picked ? 'var(--sb-accent)' : 'var(--sb-fg)',
        }}>
          {arch.label}
        </span>
        {picked && (
          <span style={{ marginLeft: 'auto', color: 'var(--sb-accent)' }}>
            <SBIcon name="check" size={12} />
          </span>
        )}
      </div>
      <div style={{
        fontSize: 11.5, color: 'var(--sb-fg-4)', lineHeight: 1.55,
      }}>
        {arch.blurb}
      </div>
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Styles
// ─────────────────────────────────────────────────────────────────────────────

const card = {
  background: 'var(--sb-bg-2)',
  border: '1px solid var(--sb-line-2)',
};

const ribbon = {
  display: 'flex', alignItems: 'center', gap: 12,
  padding: '14px 18px',
};

const body = {
  padding: '22px 22px 20px',
  minHeight: 280,
};

const footer = {
  display: 'flex', alignItems: 'center', gap: 8,
  padding: '12px 18px',
  borderTop: '1px solid var(--sb-line)',
  background: 'var(--sb-card)',
};

const cancelBtn = {
  background: 'transparent', border: 'none',
  color: 'var(--sb-fg-5)', cursor: 'pointer', padding: 4,
  display: 'flex', alignItems: 'center',
};
