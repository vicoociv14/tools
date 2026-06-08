import { useEffect, useRef } from "react";
import { useTranscript, type Segment } from "./useTranscript";
import Chat from "./Chat";
import "./App.css";

function fmt(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function speakerClass(sp: string): string {
  if (sp === "You") return "you";
  if (sp === "Remote") return "remote";
  return "other";
}

export default function App() {
  const { segments, connected } = useTranscript();
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [segments.length]);

  return (
    <div className="app">
      <header>
        <h1>Live Meeting Agent</h1>
        <span className={connected ? "dot on" : "dot off"} />
        <span className="status">{connected ? "live" : "reconnecting…"}</span>
        <span className="count">{segments.length} segments</span>
      </header>
      <main className="transcript">
        {segments.length === 0 && <p className="empty">Waiting for speech…</p>}
        {segments.map((s: Segment, i: number) => (
          <div key={i} className={`seg ${speakerClass(s.speaker)}`}>
            <span className="meta">
              {fmt(s.start)} · {s.speaker}
            </span>
            <span className="text">{s.text}</span>
          </div>
        ))}
        <div ref={endRef} />
      </main>
      <Chat />
    </div>
  );
}
