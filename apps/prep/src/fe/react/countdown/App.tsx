import { useState } from "react";

function format(ms: number) {
  const total = Math.ceil(ms / 1000);
  const m = String(Math.floor(total / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return `${m}:${s}`;
}

export default function App() {
  const [durationMs, setDurationMs] = useState(60_000);
  const [remaining, setRemaining] = useState(60_000);
  const [deadline, setDeadline] = useState(null);

  const running = deadline != null;
  const done = remaining == 0;

  function handleDuration(e: any) {
    const secs = Number(e.target.value);
    const ms = Number.isFinite(secs) && secs > 0 ? Math.floor(secs) * 1000 : 0;
    setDurationMs(ms);
    if (!running) setRemaining(ms);
  }
  return (
    <main>
      <label htmlFor="secs">Duration (seconds)</label>
      <input
        id="secs"
        type="number"
        min="1"
        value={durationMs / 1000}
        onChange={handleDuration}
        disabled={running}
      />
    </main>
  );
}
