// SmartBiz OS — icon set. Single 20×20 grid, currentColor stroke, square linecaps.
// DO NOT cleanup paths; the UI kit is the spec.

import React from 'react';

export default function SBIcon({ name, size = 16, stroke = 1.5 }) {
  const p = {
    // nav
    lara: <><circle cx="10" cy="10" r="3" /><circle cx="10" cy="10" r="6" /><path d="M10 1 V3 M10 17 V19 M1 10 H3 M17 10 H19" /></>,
    leads: <><path d="M3 16 V14 A3 3 0 0 1 6 11 H10 A3 3 0 0 1 13 14 V16" /><circle cx="8" cy="6" r="3" /><path d="M14 11 L16 13 M18 9 L16 11" /></>,
    flow: <><circle cx="4" cy="5" r="2" /><circle cx="4" cy="15" r="2" /><circle cx="16" cy="10" r="2" /><path d="M6 5 H10 A4 4 0 0 1 14 9 M6 15 H10 A4 4 0 0 0 14 11" /></>,
    reports: <><path d="M3 17 H17" /><path d="M5 17 V11 M9 17 V7 M13 17 V13 M16 17 V5" /></>,
    docs: <><path d="M4 3 H12 L16 7 V17 H4 Z" /><path d="M12 3 V7 H16" /><path d="M7 11 H13 M7 14 H11" /></>,
    settings: <><circle cx="10" cy="10" r="2.2" /><path d="M10 2 L11 4 L13.5 3.5 L14 6 L16.5 7 L15.5 9 L17 11 L15 12.5 L15.5 15 L13 15.5 L11.5 17.5 L10 16 L8.5 17.5 L7 15.5 L4.5 15 L5 12.5 L3 11 L4.5 9 L3.5 7 L6 6 L6.5 3.5 L9 4 Z" /></>,
    // actions
    plus: <><path d="M10 4 V16 M4 10 H16" /></>,
    search: <><circle cx="9" cy="9" r="5" /><path d="M13 13 L17 17" /></>,
    send: <><path d="M3 10 L17 3 L13 17 L10 11 L3 10 Z" /></>,
    close: <><path d="M5 5 L15 15 M15 5 L5 15" /></>,
    check: <><path d="M4 10 L8 14 L16 5" /></>,
    arrow: <><path d="M4 10 H16 M12 6 L16 10 L12 14" /></>,
    arrowDown: <><path d="M10 4 V16 M6 12 L10 16 L14 12" /></>,
    arrowUp: <><path d="M10 16 V4 M6 8 L10 4 L14 8" /></>,
    chevronR: <><path d="M8 5 L13 10 L8 15" /></>,
    chevronL: <><path d="M12 5 L7 10 L12 15" /></>,
    chevronD: <><path d="M5 8 L10 13 L15 8" /></>,
    // content
    dot: <><circle cx="10" cy="10" r="2.5" fill="currentColor" stroke="none" /></>,
    bolt: <><path d="M11 2 L5 11 H9 L8 18 L15 9 H11 Z" fill="currentColor" stroke="none" /></>,
    spark: <><path d="M10 2 V5 M10 15 V18 M2 10 H5 M15 10 H18 M4.2 4.2 L6.3 6.3 M13.7 13.7 L15.8 15.8 M4.2 15.8 L6.3 13.7 M13.7 6.3 L15.8 4.2" /></>,
    mail: <><path d="M3 5 H17 V15 H3 Z" /><path d="M3 5 L10 11 L17 5" /></>,
    phone: <><path d="M4 3 H7 L8 7 L6 8 A8 8 0 0 0 12 14 L13 12 L17 13 V16 A1 1 0 0 1 16 17 C10 17 3 10 3 4 A1 1 0 0 1 4 3 Z" /></>,
    linkedin: <><rect x="3" y="3" width="14" height="14" /><path d="M6 8 V14 M6 6 V6.5 M9 14 V8 M13 14 V11 A2 2 0 0 0 9 11 V14" /></>,
    building: <><path d="M3 17 H17 M5 17 V4 H11 V17 M11 9 H15 V17 M7 7 H9 M7 10 H9 M7 13 H9 M13 11 H14" /></>,
    user: <><circle cx="10" cy="7" r="3" /><path d="M4 17 V15 A4 4 0 0 1 8 11 H12 A4 4 0 0 1 16 15 V17" /></>,
    mic: <><rect x="8" y="3" width="4" height="9" rx="2" /><path d="M5 10 A5 5 0 0 0 15 10 M10 15 V17 M7 17 H13" /></>,
    at: <><circle cx="10" cy="10" r="3" /><path d="M13 10 V11 A2 2 0 0 0 17 11 V10 A7 7 0 1 0 14 16" /></>,
    slash: <><path d="M13 3 L7 17" /></>,
    tool: <><path d="M9 3 A4 4 0 0 0 5 8 L12 15 A4 4 0 0 0 16 11 L14 9 L16 7 L13 4 L11 6 Z" /></>,
    eye: <><path d="M2 10 C4 5 7 3 10 3 C13 3 16 5 18 10 C16 15 13 17 10 17 C7 17 4 15 2 10 Z" /><circle cx="10" cy="10" r="2.5" /></>,
    // domain
    flame: <><path d="M10 3 C8 6 6 7 6 11 A4 4 0 0 0 14 12 C14 9 11 8 12 5 C11 7 10 5 10 3 Z" /></>,
    warn: <><path d="M10 2 L18 16 H2 Z M10 8 V12 M10 14 V14.5" /></>,
    trend: <><path d="M3 14 L8 9 L11 12 L17 5" /><path d="M13 5 H17 V9" /></>,
    filter: <><path d="M3 4 H17 L12 10 V15 L8 17 V10 Z" /></>,
    more: <><circle cx="4" cy="10" r="1" fill="currentColor" stroke="none" /><circle cx="10" cy="10" r="1" fill="currentColor" stroke="none" /><circle cx="16" cy="10" r="1" fill="currentColor" stroke="none" /></>,
    star: <><path d="M10 2 L12 7 L17 7.5 L13 11 L14 16 L10 13.5 L6 16 L7 11 L3 7.5 L8 7 Z" /></>,
    clock: <><circle cx="10" cy="10" r="7" /><path d="M10 6 V10 L13 12" /></>,
    money: <><circle cx="10" cy="10" r="7" /><path d="M12 7 H9 A1.5 1.5 0 0 0 9 10 H11 A1.5 1.5 0 0 1 11 13 H8 M10 6 V14" /></>,
    command: <><path d="M5 5 A2 2 0 1 1 7 7 V13 A2 2 0 1 1 5 15 V5 M15 15 A2 2 0 1 1 13 13 V7 A2 2 0 1 1 15 5 V15 M7 7 H13 V13 H7 Z" /></>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
      {p[name] || <rect x="4" y="4" width="12" height="12" />}
    </svg>
  );
}
