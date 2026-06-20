import React, { useState } from 'react';
import SBIcon from './SBIcon.jsx';

export default function SBButton({
  children,
  variant = 'primary',
  size = 'md',
  icon,
  iconRight,
  onClick,
  active,
  type = 'button',
  disabled,
  style: extraStyle,
}) {
  const sizes = {
    xs: { padding: '4px 9px', fontSize: 11 },
    sm: { padding: '6px 12px', fontSize: 12 },
    md: { padding: '8px 16px', fontSize: 12.5 },
    lg: { padding: '11px 22px', fontSize: 13 },
  };
  const [hover, setHover] = useState(false);
  const h = (hover || active) && !disabled;
  const variants = {
    primary:   { background: h ? '#fff' : 'var(--sb-accent)', color: '#000', border: 'none',
                 boxShadow: h ? '0 0 24px var(--sb-accent-glow)' : 'none' },
    secondary: { background: h ? 'var(--sb-card-2)' : 'var(--sb-card)', color: 'var(--sb-fg)',
                 border: '1px solid var(--sb-line-2)' },
    ghost:     { background: h ? 'var(--sb-card)' : 'transparent', color: 'var(--sb-fg-2)', border: 'none' },
    outline:   { background: 'transparent', color: h ? 'var(--sb-accent)' : 'var(--sb-fg)',
                 border: `1px solid ${h ? 'var(--sb-accent)' : 'var(--sb-line-2)'}` },
    danger:    { background: 'transparent', color: 'var(--sb-hot)', border: '1px solid var(--sb-hot)' },
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        ...sizes[size],
        ...variants[variant],
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        fontFamily: 'var(--sb-font)',
        fontWeight: 600,
        letterSpacing: '0.01em',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 7,
        transition: 'all 160ms ease',
        whiteSpace: 'nowrap',
        ...extraStyle,
      }}
    >
      {icon && <SBIcon name={icon} size={13} stroke={1.6} />}
      {children}
      {iconRight && <SBIcon name={iconRight} size={13} stroke={1.6} />}
    </button>
  );
}
