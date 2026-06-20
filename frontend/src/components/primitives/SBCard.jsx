import React, { useState } from 'react';

export default function SBCard({ children, style, hover, bracket, onClick }) {
  const [h, setH] = useState(false);
  return (
    <div
      onMouseEnter={() => hover && setH(true)}
      onMouseLeave={() => hover && setH(false)}
      onClick={onClick}
      className={bracket ? 'sb-brackets' : ''}
      style={{
        background: 'var(--sb-card)',
        border: `1px solid ${h ? 'var(--sb-line-3)' : 'var(--sb-line)'}`,
        transition: 'border-color 200ms',
        cursor: onClick ? 'pointer' : 'default',
        ...style,
      }}
    >
      {children}
    </div>
  );
}
