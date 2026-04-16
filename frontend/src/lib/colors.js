// Stable per-robot colour palette — muted industrial tones, not rainbow.
export const ROBOT_PALETTE = [
  '#d9a441', // amber
  '#bfe847', // lime
  '#5aa6c9', // sky
  '#a88dc9', // violet
  '#e89a7e', // coral
  '#7ed9a4', // mint
  '#d97e9a', // rose
  '#c9c05a', // ochre
  '#89a2c9', // steel
  '#c98d5a', // copper
];

export function robotColor(id) {
  // extract trailing digits for stable indexing
  const m = String(id).match(/(\d+)/);
  const n = m ? parseInt(m[1], 10) : 0;
  return ROBOT_PALETTE[n % ROBOT_PALETTE.length];
}

// Lane stroke colour, picks a hue based on lane_type + critical.
export function laneBaseColor(lane) {
  if (lane.critical) return '#7e2e1c';
  if (lane.lane_type === 'human_zone') return '#8a6523';
  if (lane.lane_type === 'narrow') return '#55544d';
  if (lane.lane_type === 'intersection') return '#3d5566';
  return '#24271f';
}

// Heatmap: mix from base (dim) -> amber -> red as usage grows.
// usageRatio is 0..1 normalised by max usage in graph.
export function heatColor(usageRatio) {
  if (usageRatio <= 0) return '#2a2d24';
  // step through three anchors: dim -> amber -> red
  const t = Math.min(1, usageRatio);
  if (t < 0.5) {
    // 0..0.5 -> dim to amber
    const k = t / 0.5;
    return mix('#2a2d24', '#d9a441', k);
  } else {
    const k = (t - 0.5) / 0.5;
    return mix('#d9a441', '#e25c3f', k);
  }
}

function mix(a, b, t) {
  const ax = parseInt(a.slice(1), 16);
  const bx = parseInt(b.slice(1), 16);
  const ar = (ax >> 16) & 0xff, ag = (ax >> 8) & 0xff, ab = ax & 0xff;
  const br = (bx >> 16) & 0xff, bg = (bx >> 8) & 0xff, bb = bx & 0xff;
  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const b2 = Math.round(ab + (bb - ab) * t);
  return `rgb(${r},${g},${b2})`;
}
