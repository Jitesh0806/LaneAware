import { useEffect, useRef, useState, useCallback } from 'react';

export function useSimSocket(url) {
  const [snapshot, setSnapshot] = useState(null);
  const [status, setStatus] = useState('connecting'); // connecting | open | closed
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);

  const connect = useCallback(() => {
    setStatus('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setStatus('open');
    ws.onclose = () => {
      setStatus('closed');
      // auto-reconnect after short delay
      reconnectTimerRef.current = setTimeout(connect, 1200);
    };
    ws.onerror = () => {
      try { ws.close(); } catch {}
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'snapshot' || msg.type === 'done') {
          setSnapshot(msg.data);
        }
      } catch {
        /* ignore */
      }
    };
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  const send = useCallback((payload) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }, []);

  return { snapshot, status, send };
}
