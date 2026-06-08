import { useState } from "react";
import { useAsk } from "./useAsk";

const PRESETS: { label: string; key: string }[] = [
  { label: "Summary", key: "summary" },
  { label: "Decisions", key: "decisions" },
  { label: "Action items", key: "actions" },
  { label: "Open questions", key: "questions" },
  { label: "Draw drawio", key: "draw" },
];

export default function Chat() {
  const { answer, busy, ask } = useAsk();
  const [input, setInput] = useState("");

  function submit(q: string) {
    if (!q.trim() || busy) return;
    ask(q);
  }

  return (
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
          placeholder="Ask about the meeting…"
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
  );
}
