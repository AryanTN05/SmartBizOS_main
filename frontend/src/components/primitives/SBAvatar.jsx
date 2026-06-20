import React from 'react';

export default function SBAvatar({ name = '', color, size = 24 }) {
  const initials = name.split(' ').map(s => s[0]).filter(Boolean).join('').slice(0, 2).toUpperCase() || '?';
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: color || 'var(--sb-card-2)', color: '#000',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: size * 0.38, fontWeight: 700, fontFamily: 'var(--sb-font-mono)',
      flexShrink: 0,
    }}>{initials}</div>
  );
}
