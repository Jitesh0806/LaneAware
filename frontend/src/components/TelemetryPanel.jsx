import React from 'react';

export default function TelemetryPanel({ snapshot, status, onCmd, speed, setSpeed, mode, setMode }) {
  const m = snapshot?.metrics || {};
  const done = snapshot?.done;

  return (
    <div className="sidel">
      <div className="section">
        <h3>
          <span>TELEMETRY</span>
          <span className="tag">01</span>
        </h3>
        <Kv k="tick"             v={m.tick ?? '—'} />
        <Kv k="finished"         v={`${m.finished ?? 0}/${snapshot?.robots?.length ?? '—'}`} cls="pos" />
        <Kv k="failed"           v={m.failed ?? 0} cls={m.failed ? 'neg' : ''} />
        <Kv k="distance"         v={`${m.total_distance ?? 0} u`} />
        <Kv k="wait ticks"       v={m.total_wait_ticks ?? 0} />
        <Kv k="replans"          v={m.total_replans ?? 0} cls="accent" />
        <Kv k="e-stops"          v={m.estop_events ?? 0} cls={m.estop_events ? 'neg' : ''} />
        <Kv k="deadlocks rsv'd"  v={m.deadlocks_resolved ?? 0} cls="accent" />
        <Kv k="throughput"       v={(m.avg_throughput ?? 0).toFixed(3)} />
      </div>

      <div className="section">
        <h3>
          <span>OVERLAY</span>
          <span className="tag">02</span>
        </h3>
        <div className="controls">
          <button
            className={mode === 'congestion' ? 'primary' : ''}
            onClick={() => setMode('congestion')}
          >Congestion</button>
          <button
            className={mode === 'heat' ? 'primary' : ''}
            onClick={() => setMode('heat')}
          >Heatmap</button>
        </div>
      </div>

      <div className="section">
        <h3>
          <span>CONTROL</span>
          <span className="tag">03</span>
        </h3>
        <div className="controls">
          <button onClick={() => onCmd({ cmd: 'resume' })} className="primary">Resume</button>
          <button onClick={() => onCmd({ cmd: 'pause' })}>Pause</button>
          <button onClick={() => onCmd({ cmd: 'reset' })} className="danger">Reset</button>
        </div>
        <div className="speed-row">
          <span style={{ color: 'var(--ink-mute)', fontSize: 10, letterSpacing: '0.18em' }}>SPD</span>
          <input
            type="range"
            min="0.25"
            max="4"
            step="0.25"
            value={speed}
            onChange={(e) => {
              const v = parseFloat(e.target.value);
              setSpeed(v);
              onCmd({ cmd: 'speed', value: v });
            }}
          />
          <span className="val">{speed.toFixed(2)}×</span>
        </div>
      </div>

      <div className="section">
        <h3>
          <span>STATUS</span>
          <span className="tag">04</span>
        </h3>
        <Kv k="socket" v={status.toUpperCase()} cls={status === 'open' ? 'pos' : 'neg'} />
        <Kv k="run"    v={done ? 'COMPLETE' : snapshot ? 'ACTIVE' : 'IDLE'} cls={done ? 'accent' : 'pos'} />
        <div style={{ marginTop: 14, fontSize: 10, color: 'var(--ink-mute)', lineHeight: 1.5 }}>
          STREAM := /ws/sim<br/>
          DT := 0.25s/tick<br/>
          COORD := reservation + wait-for<br/>
          PLAN := lane-aware A*
        </div>
      </div>
    </div>
  );
}

function Kv({ k, v, cls = '' }) {
  return (
    <div className="kv">
      <span className="k">{k}</span>
      <span className={`v ${cls}`}>{v}</span>
    </div>
  );
}
