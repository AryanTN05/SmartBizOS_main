/**
 * SVG icon path data for flowchart nodes.
 * Each icon is designed for a 16x16 coordinate space.
 * The FlowChart component positions these inside node circles.
 */

interface IconPath {
  /** SVG content (paths, rects, circles) — no wrapping <g> or <svg> */
  d: string;
}

export const FLOW_ICONS: Record<string, IconPath> = {
  shield: {
    d: '<path d="M8 1.5 L14 4.5 V9.5 C14 12.5 11 15 8 16.5 C5 15 2 12.5 2 9.5 V4.5 Z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><rect x="6" y="7.5" width="4" height="3.5" rx="0.5" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M6.5 7.5 V6 C6.5 4.5 9.5 4.5 9.5 6 V7.5" fill="none" stroke="currentColor" stroke-width="1.1"/>',
  },
  eye: {
    d: '<ellipse cx="8" cy="8" rx="7" ry="4.5" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2.5" fill="none" stroke="currentColor" stroke-width="1.2"/><circle cx="8" cy="8" r="0.8" fill="currentColor"/>',
  },
  agents: {
    d: '<circle cx="5" cy="5.5" r="3" fill="none" stroke="currentColor" stroke-width="1.2"/><circle cx="11" cy="5.5" r="3" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M5 8.5 V11 M11 8.5 V11" stroke="currentColor" stroke-width="1.2"/><path d="M7 4 L9 4" stroke="currentColor" stroke-width="0.8" stroke-dasharray="1.5 1"/>',
  },
  chart: {
    d: '<rect x="1" y="1" width="14" height="11" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.2"/><rect x="3.5" y="5" width="2.2" height="5" rx="0.3" fill="currentColor" opacity="0.5"/><rect x="6.9" y="3" width="2.2" height="7" rx="0.3" fill="currentColor" opacity="0.7"/><rect x="10.3" y="6" width="2.2" height="4" rx="0.3" fill="currentColor" opacity="0.4"/>',
  },
  brain: {
    d: '<path d="M8 14 V8" stroke="currentColor" stroke-width="1.2"/><path d="M8 8 C8 4 4 3 3.5 5.5 C2 5 1 7 2.5 8.5 C1.5 9.5 2.5 11.5 4 11 C4.5 12.5 7 13 8 11" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M8 8 C8 4 12 3 12.5 5.5 C14 5 15 7 13.5 8.5 C14.5 9.5 13.5 11.5 12 11 C11.5 12.5 9 13 8 11" fill="none" stroke="currentColor" stroke-width="1.2"/>',
  },
  audio: {
    d: '<rect x="5.5" y="2" width="5" height="8" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M3 8 C3 11.5 5 13 8 13 C11 13 13 11.5 13 8" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M8 13 V15" stroke="currentColor" stroke-width="1.2"/><path d="M5.5 15 L10.5 15" stroke="currentColor" stroke-width="1.2"/>',
  },
  globe: {
    d: '<circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.2"/><ellipse cx="8" cy="8" rx="3" ry="6.5" fill="none" stroke="currentColor" stroke-width="1"/><path d="M1.5 8 L14.5 8" stroke="currentColor" stroke-width="0.8"/><path d="M2.5 4.5 L13.5 4.5 M2.5 11.5 L13.5 11.5" stroke="currentColor" stroke-width="0.7"/>',
  },
  zap: {
    d: '<path d="M9 1.5 L4 8.5 H7.5 L6.5 14.5 L12 7.5 H8.5 Z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>',
  },
  database: {
    d: '<ellipse cx="8" cy="4" rx="5.5" ry="2.5" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M2.5 4 V12 C2.5 13.4 5 14.5 8 14.5 C11 14.5 13.5 13.4 13.5 12 V4" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M2.5 8 C2.5 9.4 5 10.5 8 10.5 C11 10.5 13.5 9.4 13.5 8" fill="none" stroke="currentColor" stroke-width="1"/>',
  },
  medical: {
    d: '<rect x="1.5" y="1.5" width="13" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M8 4.5 V11.5 M4.5 8 L11.5 8" stroke="currentColor" stroke-width="1.5"/>',
  },
  factory: {
    d: '<path d="M1 14 V6 L5 9 V6 L9 9 V4 L15 4 V14 Z" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><rect x="11" y="8" width="2" height="2.5" fill="currentColor" opacity="0.5"/><rect x="11" y="11.5" width="2" height="2.5" fill="currentColor" opacity="0.5"/>',
  },
  memory: {
    d: '<rect x="3" y="2" width="10" height="12" rx="1" fill="none" stroke="currentColor" stroke-width="1.2"/><circle cx="8" cy="7" r="2.5" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M8 4.5 V5 M8 9 V9.5 M5.5 7 H6 M10 7 H10.5" stroke="currentColor" stroke-width="1"/><path d="M1 5 H3 M1 9 H3 M1 12 H3 M13 5 H15 M13 9 H15 M13 12 H15" stroke="currentColor" stroke-width="1"/>',
  },
};
