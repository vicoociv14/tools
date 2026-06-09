import { useEffect, useState } from "react";
import { useArchiveAsk } from "./useArchiveAsk";
import "./App.css";
import "./Archive.css";

type Meeting = {
  id: string;
  started_at: string;
  duration_s: number;
  speakers: string[];
  segments: number;
  title: string;
  summary: string;
  topics: string[];
  titled: boolean;
};

type Seg = { start: number; end: number; text: string; speaker: string; channel: string };

const PRESETS: { label: string; key: string }[] = [
  { label: "Summary", key: "summary" },
  { label: "Decisions", key: "decisions" },
  { label: "Action items", key: "actions" },
  { label: "Open questions", key: "questions" },
  { label: "Draw drawio", key: "draw" },
];

function fmtClock(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
function fmtDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}
function fmtDur(s: number): string {
  const m = Math.round(s / 60);
  return m >= 1 ? `${m} min` : `${Math.round(s)} s`;
}
function speakerClass(sp: string): string {
  if (sp === "You") return "you";
  if (sp === "Remote") return "remote";
  return "other";
}

function sanitizeName(name: string): string {
  const cleaned = name.replace(/[\\/:*?"<>|]+/g, "_").replace(/\s+/g, " ").trim().slice(0, 80);
  return cleaned || "transcript";
}

function buildExport(meta: Meeting | null, segs: Seg[]): string {
  const lines: string[] = [];
  lines.push(meta?.title || "Meeting");
  if (meta?.started_at) lines.push(fmtDate(meta.started_at));
  if (meta?.summary) lines.push("", meta.summary);
  lines.push("", "–".repeat(40), "");
  for (const s of segs) lines.push(`[${fmtClock(s.start)}] ${s.speaker}: ${s.text}`);
  lines.push("");
  return lines.join("\n");
}

type PyWebview = { api?: { save_text_file?: (name: string, content: string) => Promise<string | null> } };

export default function Archive() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [meta, setMeta] = useState<Meeting | null>(null);
  const [segs, setSegs] = useState<Seg[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const { answer, busy, ask } = useArchiveAsk(selected);
  const [input, setInput] = useState("");

  async function loadList(q = "") {
    setLoadingList(true);
    try {
      const url = q.trim() ? `/api/search?q=${encodeURIComponent(q)}` : "/api/meetings";
      const res = await fetch(url);
      setMeetings(await res.json());
    } catch {
      /* ignore */
    } finally {
      setLoadingList(false);
    }
  }

  useEffect(() => {
    loadList();
  }, []);

  async function open(id: string) {
    setSelected(id);
    setMeta(null);
    setSegs([]);
    try {
      const res = await fetch(`/api/meetings/${encodeURIComponent(id)}`);
      const data = await res.json();
      setMeta(data.meta);
      setSegs(data.segments || []);
    } catch {
      /* ignore */
    }
  }

  function submit(q: string) {
    if (!q.trim() || busy || !selected) return;
    ask(q);
  }

  async function exportTranscript() {
    if (!meta || segs.length === 0) return;
    const content = buildExport(meta, segs);
    const fname = `${sanitizeName(meta.title || selected || "transcript")}.txt`;
    const api = (window as unknown as { pywebview?: PyWebview }).pywebview?.api;
    if (api?.save_text_file) {
      try {
        await api.save_text_file(fname, content); // native Save As dialog
      } catch {
        /* user cancelled */
      }
    } else {
      const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fname;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }
  }

  return (
    <div className="archive">
      <aside className="sidebar">
        <div className="sbar">
          <input
            value={query}
            placeholder="Search meetings…"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") loadList(query);
            }}
          />
          <button onClick={() => loadList(query)}>Search</button>
          {query && (
            <button
              onClick={() => {
                setQuery("");
                loadList("");
              }}
            >
              ×
            </button>
          )}
        </div>
        {loadingList && <p className="empty pad">Loading…</p>}
        {!loadingList && meetings.length === 0 && <p className="empty pad">No meetings found.</p>}
        {meetings.map((m) => (
          <div
            key={m.id}
            className={`mcard ${selected === m.id ? "sel" : ""}`}
            onClick={() => open(m.id)}
          >
            <div className="mtitle">{m.title}</div>
            <div className="mmeta">
              {fmtDate(m.started_at)} · {fmtDur(m.duration_s)}
              {m.speakers.length > 0 && <> · {m.speakers.join(", ")}</>}
            </div>
            {m.topics && m.topics.length > 0 && (
              <div className="mtopics">
                {m.topics.map((t) => (
                  <span key={t} className="tag">
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </aside>

      <main className="main">
        {!selected && (
          <div className="placeholder">Select a meeting to read its transcript and ask questions.</div>
        )}
        {selected && (
          <>
            <header className="mhead">
              <h1>{meta?.title || "…"}</h1>
              {meta?.summary && <p className="msummary">{meta.summary}</p>}
              <div className="mhead-row">
                <span className="count">
                  {meta?.started_at ? fmtDate(meta.started_at) : ""} · {segs.length} segments
                </span>
                <button className="export-btn" onClick={exportTranscript} disabled={segs.length === 0}>
                  Export transcript
                </button>
              </div>
            </header>
            <div className="transcript">
              {segs.length === 0 && <p className="empty">No transcript.</p>}
              {segs.map((s, i) => (
                <div key={i} className={`seg ${speakerClass(s.speaker)}`}>
                  <span className="meta">
                    {fmtClock(s.start)} · {s.speaker}
                  </span>
                  <span className="text">{s.text}</span>
                </div>
              ))}
            </div>
            <div className="chat">
              <div className="presets">
                {PRESETS.map((p) => (
                  <button key={p.key} disabled={busy} onClick={() => submit(p.key)}>
                    {p.label}
                  </button>
                ))}
              </div>
              <form
                className="ask"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit(input);
                  setInput("");
                }}
              >
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask about this meeting…"
                  disabled={busy}
                />
                <button type="submit" disabled={busy || !input.trim()}>
                  Ask
                </button>
              </form>
              <div className="answer">
                {busy && !answer && <span className="thinking">thinking…</span>}
                {answer && <pre>{answer}</pre>}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
