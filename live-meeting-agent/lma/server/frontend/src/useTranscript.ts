import { useEffect, useRef, useState } from "react";

export type Segment = {
  start: number;
  end: number;
  text: string;
  speaker: string;
  channel: string;
};

export function useTranscript() {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${location.host}/ws/transcript`;
    let stop = false;

    function connect() {
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!stop) setTimeout(connect, 1000); // auto-reconnect
      };
      ws.onmessage = (ev) => {
        const seg: Segment = JSON.parse(ev.data);
        setSegments((prev) => [...prev, seg].sort((a, b) => a.start - b.start));
      };
    }
    connect();
    return () => {
      stop = true;
      wsRef.current?.close();
    };
  }, []);

  return { segments, connected };
}
