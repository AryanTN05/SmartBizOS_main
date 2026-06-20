import React, { useState } from 'react';
import { SBChip, SBIcon } from '../../../components/primitives';
import { scoreTone, tagTone, sourceIcon, intentMeta, triggerMeta } from '../lib/helpers.js';

// One card in a Kanban column. Matches the UI-kit visual language exactly.
// Supports native drag/drop; falls back gracefully (parent handles the click).

export default function LeadCard({ lead, onClick, onDragStart, onDragEnd, dragging }) {
  const [hover, setHover] = useState(false);
  const score = lead.score?.value ?? null;
  const tone = scoreTone(score);

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', lead.id);
        onDragStart?.(lead);
      }}
      onDragEnd={() => onDragEnd?.()}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        padding: 12,
        background: 'var(--sb-card)',
        border: `1px solid ${hover ? 'var(--sb-line-3)' : 'var(--sb-line)'}`,
        cursor: 'pointer',
        transition: 'border-color 160ms',
        opacity: dragging ? 0.4 : 1,
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 10, marginBottom: 8,
      }}>
        <div style={{ minWidth: 0 }}>
          <div style={{
            fontSize: 13, fontWeight: 600, color: 'var(--sb-fg)',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>{lead.name || '(unnamed)'}</div>
          <div style={{ fontSize: 11.5, color: 'var(--sb-fg-4)', marginTop: 2 }}>
            {lead.company || lead.company_domain || '—'}
          </div>
        </div>
        <div style={{
          display: 'flex', alignItems: 'baseline', gap: 2,
          fontFamily: 'var(--sb-font-mono)', color: tone,
        }}>
          <span style={{ fontSize: 18, fontWeight: 700, lineHeight: 1 }}>
            {score != null ? score : '—'}
          </span>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {lead.sequence_state === 'paused_replied' && (() => {
            const m = intentMeta(lead.last_reply_intent);
            return m ? (
              <SBChip tone={m.tone} icon={m.icon}>{m.label}</SBChip>
            ) : (
              <SBChip tone="hot" icon="check">replied</SBChip>
            );
          })()}
          {(lead.triggers || []).slice(0, 2).map((t) => {
            const m = triggerMeta(t);
            return <SBChip key={`trg-${t}`} tone={m.tone} icon={m.icon}>{m.label}</SBChip>;
          })}
          {(lead.tags || []).slice(0, 3).map((t) => (
            <SBChip key={t} tone={tagTone(t)}>{t}</SBChip>
          ))}
        </div>
        {lead._value && (
          <div style={{ fontFamily: 'var(--sb-font-mono)', fontSize: 11, color: 'var(--sb-fg-3)' }}>
            {lead._value}
          </div>
        )}
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--sb-line)',
        fontSize: 10.5, color: 'var(--sb-fg-5)', fontFamily: 'var(--sb-font-mono)',
      }}>
        <SBIcon name={sourceIcon(lead.source)} size={11} stroke={1.4} />
        {lead.source || 'unknown'}
        <span style={{ marginLeft: 'auto' }}>{lead.owner_admin_user_id || '—'}</span>
      </div>
    </div>
  );
}
