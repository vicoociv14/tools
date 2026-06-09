import { useCallback, useState } from "react";

/** Q&A against one past meeting: POST /api/meetings/{id}/ask, streamed. */
export function useArchiveAsk(meetingId: string | null) {
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);

  const ask = useCallback(
    async (question: string) => {
      if (!meetingId) return;
      setBusy(true);
      setAnswer("");
      try {
        const res = await fetch(`/api/meetings/${encodeURIComponent(meetingId)}/ask`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        });
        if (!res.body) {
          setAnswer("(no response body)");
          return;
        }
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let acc = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          acc += dec.decode(value, { stream: true });
          setAnswer(acc);
        }
      } catch (e) {
        setAnswer("Error: " + String(e));
      } finally {
        setBusy(false);
      }
    },
    [meetingId],
  );

  return { answer, busy, ask };
}
