import React from 'react';
import { robotColor } from '../lib/colors';

export default function FleetPanel({ snapshot }) {
  const robots = snapshot?.robots ?? [];
  const reservations = snapshot?.coord?.reservations ?? [];
  const waitFor = snapshot?.coord?.wait_for ?? {};

  const topLanes = (snapshot?.graph?.lanes ?? [])
    .slice()
    .sort((a, b) => b.usage - a.usage)
    .slice(0, 6);

  return (
    <div className="sider">
      <div className="section">
        <h3>
          <span>FLEET // {robots.length}</span>
          <span className="tag">A</span>
        </h3>
        <div>
          {robots.map(r => {
            const col = robotColor(r.id);
            const stateCls = r.state;
            const waitTgt = waitFor[r.id];
            return (
              <div key={r.id} className="robot-row">
                <span className="dot" style={{ background: col }} />
                <span className="id">{r.id}</span>
                <span className="path">
                  {r.at}{r.next ? ` → ${r.next}` : ''} · {r.goal}
                  {waitTgt ? <span style={{ color: 'var(--amber)', marginLeft: 6 }}>⇢{waitTgt}</span> : null}
                </span>
                <span className={`state ${stateCls}`}>{r.state}</span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="section">
        <h3>
          <span>RESERVATIONS</span>
          <span className="tag">B</span>
        </h3>
        {reservations.length === 0 ? (
          <div style={{ color: 'var(--ink-mute)', fontSize: 11 }}>no critical lanes held</div>
        ) : (
          reservations.map(r => (
            <div key={r.lane} className="kv">
              <span className="k">{r.lane}</span>
              <span className="v accent">{r.owner}</span>
            </div>
          ))
        )}
      </div>

      <div className="section">
        <h3>
          <span>LANE USAGE · TOP 6</span>
          <span className="tag">C</span>
        </h3>
        {topLanes.map(l => (
          <div key={`${l.u}-${l.v}`} className="kv">
            <span className="k">
              {l.u}-{l.v}
              <span style={{ color: 'var(--ink-mute)', marginLeft: 6 }}>
                {l.lane_type.slice(0, 4)}
              </span>
            </span>
            <span className="v">
              {l.usage}
              <span style={{ color: 'var(--ink-mute)', marginLeft: 6 }}>
                {(l.congestion * 100).toFixed(0)}%
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
