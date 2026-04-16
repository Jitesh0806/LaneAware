import React, { useEffect, useRef } from 'react';

export default function EventLog({ snapshot }) {
  const logRef = useRef(null);
  const events = snapshot?.coord?.recent_events ?? [];
  const tick = snapshot?.tick ?? 0;

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  return (
    <div className="footer">
      <div className="bar">
        <span>EVENT STREAM <span className="tag">· coord.log</span></span>
        <span style={{ color: 'var(--ink-mute)' }}>T={String(tick).padStart(5, '0')}</span>
      </div>
      <div className="log" ref={logRef}>
        {events.length === 0 ? (
          <div style={{ color: 'var(--ink-mute)', fontSize: 11 }}>— awaiting coordinator events —</div>
        ) : (
          events.map((e, i) => (
            <div key={i} className="line">
              <span className="t">#{String(tick - (events.length - i - 1)).padStart(4, '0')}</span>
              <span className={`type ${e.type === 'deadlock_resolved' ? 'deadlock' : e.type === 'released' ? 'released' : ''}`}>
                {e.type.replace('_', ' ')}
              </span>
              <span className="msg">
                {e.type === 'deadlock_resolved'
                  ? <>cycle [{e.cycle?.join(' → ')}] · victim <b>{e.victim}</b></>
                  : <>lane <b>{e.lane}</b> · robot <b>{e.robot}</b></>}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
