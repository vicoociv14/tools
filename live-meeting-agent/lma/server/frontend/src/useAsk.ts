import { useCallback, useState } from "react";

export function useAsk() {
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);

  const ask = useCallback(async (question: string) => {
    setBusy(true);
    setAnswer("");
    try {
      const res = await fetch("/api/ask", {
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
  }, []);

  return { answer, busy, ask };
}
