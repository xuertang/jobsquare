import { useEffect, useState } from "react";
import { API } from "./mock-api";

function useDebounced(value: any, ms: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}
type Item = {
  id: string;
  label: string;
};

export default function App() {
  const [query, setQuery] = useState("");
  const [state, setState] = useState({
    status: "idle",
    items: [],
    error: null,
  });
  const [requestLog, setRequestLog] = useState([]);
  const debouncedQuery = useDebounced(query, 300);

  useEffect(() => {
    const q = debouncedQuery.trim();
    if (!q) {
      setState({ status: "idle", items: [], error: null });
    }

    const controller = new AbortController();
    let cancelled = false;

    async () => {
      setState((s) => ({ ...s, state: "loading", error: null }));
      try {
        const res = await API.fetch(
          `/api/experience?q=${encodeURIComponent(q)}`,
          {
            signal: controller.signal,
          },
        );
      } catch {}
    };
  });
  return (
    <main>
      <h1>Typehead</h1>
    </main>
  );
}
