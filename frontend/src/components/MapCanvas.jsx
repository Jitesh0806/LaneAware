import React, { useEffect, useRef, useMemo } from 'react';
import { robotColor, laneBaseColor, heatColor } from '../lib/colors';

/**
 * MapCanvas
 * Renders the lane graph + live robots on a scaled canvas.
 *
 * Visual language:
 *  - background: sunken charcoal with a subtle grid
 *  - lanes: hairline strokes, coloured by type; heatmap-coloured overlay sits on top,
 *           stroke width proportional to usage
 *  - directed lanes: chevron glyphs along the centreline
 *  - critical lanes: dashed amber outline when actively reserved
 *  - nodes: 12px filled squares with tick marks + label
 *  - robots: 14px squares with a 4-segment trail behind, id label floating above,
 *            a ring pulses when in ESTOP
 *  - goal: 8px outlined cross at target node for each robot (dimmed)
 */
export default function MapCanvas({ snapshot, mode }) {
  const canvasRef = useRef(null);
  const trailsRef = useRef({}); // robot id -> array of {x,y}
  const animationRef = useRef(null);

  // Derive max usage for heatmap normalization
  const maxUsage = useMemo(() => {
    if (!snapshot) return 1;
    return Math.max(1, ...snapshot.graph.lanes.map(l => l.usage));
  }, [snapshot]);

  // Track trails
  useEffect(() => {
    if (!snapshot) return;
    const trails = trailsRef.current;
    for (const r of snapshot.robots) {
      if (!trails[r.id]) trails[r.id] = [];
      const arr = trails[r.id];
      const last = arr[arr.length - 1];
      if (!last || Math.hypot(last.x - r.x, last.y - r.y) > 0.05) {
        arr.push({ x: r.x, y: r.y });
        if (arr.length > 24) arr.shift();
      }
    }
  }, [snapshot]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      if (canvas.width !== rect.width * dpr || canvas.height !== rect.height * dpr) {
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
      }
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, rect.width, rect.height);

      if (!snapshot) {
        drawWaiting(ctx, rect);
        animationRef.current = requestAnimationFrame(draw);
        return;
      }

      // compute transform to fit graph with padding
      const nodes = snapshot.graph.nodes;
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      for (const n of nodes) {
        if (n.x < minX) minX = n.x;
        if (n.x > maxX) maxX = n.x;
        if (n.y < minY) minY = n.y;
        if (n.y > maxY) maxY = n.y;
      }
      const padX = 48, padY = 48;
      const gw = Math.max(1, maxX - minX);
      const gh = Math.max(1, maxY - minY);
      const scale = Math.min(
        (rect.width - padX * 2) / gw,
        (rect.height - padY * 2) / gh
      );
      const offX = (rect.width - gw * scale) / 2 - minX * scale;
      const offY = (rect.height - gh * scale) / 2 - minY * scale;

      const toPx = (x, y) => [x * scale + offX, y * scale + offY];

      // background grid
      drawGrid(ctx, rect);

      // node lookup
      const nodePos = {};
      for (const n of nodes) nodePos[n.id] = [...toPx(n.x, n.y)];

      // draw lanes - first pass: base stroke
      for (const ln of snapshot.graph.lanes) {
        const [x1, y1] = nodePos[ln.u];
        const [x2, y2] = nodePos[ln.v];
        // base
        ctx.strokeStyle = laneBaseColor(ln);
        ctx.lineWidth = ln.lane_type === 'narrow' ? 1 : 2;
        ctx.beginPath();
        ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
        ctx.stroke();
      }

      // draw lanes - second pass: heatmap overlay (if mode=heat) OR congestion overlay
      for (const ln of snapshot.graph.lanes) {
        const [x1, y1] = nodePos[ln.u];
        const [x2, y2] = nodePos[ln.v];
        if (mode === 'heat') {
          const ratio = ln.usage / maxUsage;
          if (ratio > 0) {
            ctx.strokeStyle = heatColor(ratio);
            ctx.lineWidth = 2 + ratio * 8;
            ctx.globalAlpha = 0.55 + ratio * 0.45;
            ctx.beginPath();
            ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
            ctx.stroke();
            ctx.globalAlpha = 1;
          }
        } else {
          if (ln.congestion > 0.1) {
            ctx.strokeStyle = heatColor(ln.congestion);
            ctx.lineWidth = 2 + ln.congestion * 5;
            ctx.globalAlpha = 0.55;
            ctx.beginPath();
            ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
            ctx.stroke();
            ctx.globalAlpha = 1;
          }
        }
        // critical lane hatch
        if (ln.critical) {
          ctx.strokeStyle = '#7e2e1c';
          ctx.setLineDash([3, 4]);
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
          ctx.stroke();
          ctx.setLineDash([]);
        }
        // directed chevron
        if (ln.directed) {
          drawChevron(ctx, x1, y1, x2, y2, '#8a867a');
        }
      }

      // draw nodes
      for (const n of nodes) {
        const [px, py] = nodePos[n.id];
        drawNode(ctx, px, py, n.id);
      }

      // draw goal markers (dim)
      for (const r of snapshot.robots) {
        if (r.state === 'done') continue;
        const [gx, gy] = nodePos[r.goal] || [0, 0];
        const col = robotColor(r.id);
        drawGoalMarker(ctx, gx, gy, col);
      }

      // draw trails
      const trails = trailsRef.current;
      for (const r of snapshot.robots) {
        const col = robotColor(r.id);
        const pts = trails[r.id] || [];
        if (pts.length < 2) continue;
        ctx.strokeStyle = col;
        ctx.lineWidth = 1;
        for (let i = 1; i < pts.length; i++) {
          const a = pts[i - 1], b = pts[i];
          const alpha = i / pts.length * 0.5;
          ctx.globalAlpha = alpha;
          const [ax, ay] = toPx(a.x, a.y);
          const [bx, by] = toPx(b.x, b.y);
          ctx.beginPath();
          ctx.moveTo(ax, ay); ctx.lineTo(bx, by);
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
      }

      // draw robots
      for (const r of snapshot.robots) {
        const [rx, ry] = toPx(r.x, r.y);
        drawRobot(ctx, rx, ry, r);
      }

      animationRef.current = requestAnimationFrame(draw);
    };

    animationRef.current = requestAnimationFrame(draw);
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [snapshot, mode, maxUsage]);

  return <canvas ref={canvasRef} />;
}

function drawGrid(ctx, rect) {
  ctx.strokeStyle = 'rgba(255,255,255,0.025)';
  ctx.lineWidth = 1;
  const step = 40;
  for (let x = 0; x <= rect.width; x += step) {
    ctx.beginPath();
    ctx.moveTo(x + 0.5, 0);
    ctx.lineTo(x + 0.5, rect.height);
    ctx.stroke();
  }
  for (let y = 0; y <= rect.height; y += step) {
    ctx.beginPath();
    ctx.moveTo(0, y + 0.5);
    ctx.lineTo(rect.width, y + 0.5);
    ctx.stroke();
  }
  // crosshair dots at intersections every 80px
  ctx.fillStyle = 'rgba(255,255,255,0.04)';
  for (let x = 0; x <= rect.width; x += step * 2) {
    for (let y = 0; y <= rect.height; y += step * 2) {
      ctx.fillRect(x - 1, y - 1, 2, 2);
    }
  }
}

function drawChevron(ctx, x1, y1, x2, y2, color) {
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const dx = x2 - x1, dy = y2 - y1;
  const len = Math.hypot(dx, dy);
  if (len < 1) return;
  const ux = dx / len, uy = dy / len;
  const nx = -uy, ny = ux;
  const L = 6;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(mx - ux * L + nx * L * 0.6, my - uy * L + ny * L * 0.6);
  ctx.lineTo(mx + ux * L, my + uy * L);
  ctx.lineTo(mx - ux * L - nx * L * 0.6, my - uy * L - ny * L * 0.6);
  ctx.stroke();
}

function drawNode(ctx, x, y, label) {
  const s = 6;
  ctx.fillStyle = '#0b0d0c';
  ctx.fillRect(x - s, y - s, s * 2, s * 2);
  ctx.strokeStyle = '#d6d3c7';
  ctx.lineWidth = 1;
  ctx.strokeRect(x - s + 0.5, y - s + 0.5, s * 2 - 1, s * 2 - 1);
  // tick marks
  ctx.strokeStyle = '#55544d';
  ctx.beginPath();
  ctx.moveTo(x - s - 3, y); ctx.lineTo(x - s, y);
  ctx.moveTo(x + s, y); ctx.lineTo(x + s + 3, y);
  ctx.moveTo(x, y - s - 3); ctx.lineTo(x, y - s);
  ctx.moveTo(x, y + s); ctx.lineTo(x, y + s + 3);
  ctx.stroke();
  // label
  ctx.fillStyle = '#8a867a';
  ctx.font = '10px "JetBrains Mono", monospace';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText(label, x + s + 5, y - s - 2);
}

function drawGoalMarker(ctx, x, y, color) {
  ctx.strokeStyle = color;
  ctx.globalAlpha = 0.35;
  ctx.lineWidth = 1;
  const r = 10;
  ctx.beginPath();
  ctx.moveTo(x - r, y); ctx.lineTo(x + r, y);
  ctx.moveTo(x, y - r); ctx.lineTo(x, y + r);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.stroke();
  ctx.globalAlpha = 1;
}

function drawRobot(ctx, x, y, r) {
  const col = robotColor(r.id);
  const size = 7;
  // body
  ctx.fillStyle = col;
  ctx.fillRect(x - size, y - size, size * 2, size * 2);
  // inner mark
  ctx.fillStyle = '#0b0d0c';
  ctx.fillRect(x - 2, y - 2, 4, 4);

  // e-stop ring
  if (r.state === 'estop') {
    ctx.strokeStyle = '#e25c3f';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, size + 6, 0, Math.PI * 2);
    ctx.stroke();
  } else if (r.state === 'waiting') {
    ctx.strokeStyle = '#d9a441';
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 3]);
    ctx.beginPath();
    ctx.arc(x, y, size + 5, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
  } else if (r.state === 'done') {
    ctx.globalAlpha = 0.4;
    ctx.strokeStyle = '#8a867a';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(x, y, size + 4, 0, Math.PI * 2);
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  // label
  ctx.fillStyle = '#d6d3c7';
  ctx.font = '700 10px "JetBrains Mono", monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  ctx.fillText(r.id, x, y - size - 4);
}

function drawWaiting(ctx, rect) {
  ctx.fillStyle = '#8a867a';
  ctx.font = '12px "JetBrains Mono", monospace';
  ctx.textAlign = 'center';
  ctx.fillText('AWAITING TELEMETRY...', rect.width / 2, rect.height / 2);
}
