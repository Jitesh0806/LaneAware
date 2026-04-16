import React, { useState } from 'react';
import { useSimSocket } from './hooks/useSimSocket';
import MapCanvas from './components/MapCanvas';
import TelemetryPanel from './components/TelemetryPanel';
import FleetPanel from './components/FleetPanel';
import EventLog from './components/EventLog';

export default function App() {
  // Build WS URL from current host (works with Vite proxy or standalone)
  const wsUrl =
    (window.location.protocol === 'https:' ? 'wss://' : 'ws://') +
    window.location.host +
    '/ws/sim';

  const { snapshot, status, send } = useSimSocket(wsUrl);
  const [speed, setSpeed] = useState(1.0);
  const [mode, setMode] = useState('congestion'); // 'congestion' | 'heat'

  const tick = snapshot?.tick ?? 0;
  const totalRobots = snapshot?.robots?.length ?? 0;
  const done = snapshot?.done;

  return (
    <div className="shell">
      <header className="header">
        <div className="brand">
          LANE_OPS<span className="slash">//</span>
          <span className="sub">TRAFFIC CONSOLE</span>
        </div>

        <div className="crumbs">
          <span><span className="k">SITE</span><span className="v">WAREHOUSE·ALPHA</span></span>
          <span><span className="k">FLEET</span><span className="v">{totalRobots.toString().padStart(2,'0')}</span></span>
          <span><span className="k">TICK</span><span className="v">{String(tick).padStart(5,'0')}</span></span>
          <span className={`live ${status === 'open' ? '' : 'off'}`}>
            {status === 'open' ? (done ? 'COMPLETE' : 'LIVE') : 'OFFLINE'}
          </span>
        </div>
      </header>

      <TelemetryPanel
        snapshot={snapshot}
        status={status}
        onCmd={send}
        speed={speed}
        setSpeed={setSpeed}
        mode={mode}
        setMode={setMode}
      />

      <main className="map">
        <div className="map-ornament-tl">
          <span className="k">SCAN</span><span className="v">{String(tick).padStart(5,'0')}</span>
        </div>
        <div className="map-ornament-tr">
          <span className="k">MODE</span><span className="v">{mode === 'heat' ? 'HEATMAP' : 'CONGESTION'}</span>
        </div>
        <div className="map-ornament-bl">
          LANE_OPS · WAREHOUSE·ALPHA · GRID 14×10
        </div>
        <div className="map-ornament-br">
          {done ? '◾ RUN COMPLETE' : status === 'open' ? '◦ TELEMETRY ACTIVE' : '◦ AWAIT LINK'}
        </div>

        <MapCanvas snapshot={snapshot} mode={mode} />

        <div className="legend">
          <span><span className="sw" style={{ background: '#24271f' }} /><span className="k">normal</span></span>
          <span><span className="sw" style={{ background: '#55544d' }} /><span className="k">narrow</span></span>
          <span><span className="sw" style={{ background: '#3d5566' }} /><span className="k">intersection</span></span>
          <span><span className="sw" style={{ background: '#8a6523' }} /><span className="k">human zone</span></span>
          <span><span className="sw" style={{ background: '#7e2e1c' }} /><span className="k">critical (rsvn)</span></span>
          <span><span className="dot" style={{ background: '#bfe847' }} /><span className="k">moving</span></span>
          <span><span className="dot" style={{ background: '#d9a441' }} /><span className="k">waiting</span></span>
          <span><span className="dot" style={{ background: '#e25c3f' }} /><span className="k">e-stop</span></span>
        </div>
      </main>

      <FleetPanel snapshot={snapshot} />

      <EventLog snapshot={snapshot} />
    </div>
  );
}
