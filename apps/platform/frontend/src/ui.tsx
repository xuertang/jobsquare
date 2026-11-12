import { useQueryClient } from '@tanstack/react-query';
import {
  createContext, useCallback, useContext, useEffect, useRef, useState,
  type ButtonHTMLAttributes, type ReactNode,
} from 'react';

// ------------------------------------------------------------------ toasts ---
type Toast = { id: number; text: string; tone: 'ok' | 'bad' };
const ToastCtx = createContext<(text: string, tone?: 'ok' | 'bad') => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: 'ok' | 'bad' = 'ok') => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'bad' ? 7000 : 3000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`toast ${t.tone}`}>{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

/** Run an API call, refresh the queries it affects, and surface failures. */
export function useAct(...keys: string[]) {
  const qc = useQueryClient();
  const toast = useToast();
  return useCallback(async <T,>(fn: () => Promise<T>, done?: string): Promise<T | undefined> => {
    try {
      const out = await fn();
      await Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: [k] })));
      if (done) toast(done);
      return out;
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'bad');
      return undefined;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qc, toast, keys.join('|')]);
}

// ----------------------------------------------------------------- buttons ---
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  kind?: 'primary' | 'ghost' | 'danger' | 'plain';
  small?: boolean;
  onAct?: () => Promise<unknown> | void;
};

/** A button that disables itself while its async action runs. */
export function Btn({ kind = 'plain', small, onAct, children, className = '', ...rest }: BtnProps) {
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);
  return (
    <button
      type="button"
      {...rest}
      className={`btn ${kind} ${small ? 'small' : ''} ${className}`}
      disabled={rest.disabled || busy}
      onClick={async (e) => {
        rest.onClick?.(e);
        if (!onAct) return;
        setBusy(true);
        try { await onAct(); } finally { if (alive.current) setBusy(false); }
      }}
    >
      {children}
    </button>
  );
}

export function Copy({ text, label = 'Copy', kind = 'plain' }: { text: string; label?: string; kind?: BtnProps['kind'] }) {
  const [done, setDone] = useState(false);
  return (
    <Btn
      small
      kind={kind}
      onAct={async () => {
        await navigator.clipboard.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
    >
      {done ? 'Copied' : label}
    </Btn>
  );
}

// ------------------------------------------------------------- small parts ---
export function Pill({ tone = 'muted', children, title }: { tone?: string; children: ReactNode; title?: string }) {
  return <span className={`pill ${tone}`} title={title}>{children}</span>;
}

export function Score({ value, error }: { value: number | null; error?: string | null }) {
  if (value === null) {
    return <span className="score none" title={error || 'Not scored yet'}>{error ? '!' : 'n/a'}</span>;
  }
  const band = value >= 85 ? 'top' : value >= 70 ? 'good' : value >= 50 ? 'mid' : 'low';
  return <span className={`score ${band}`} title={`Fit score ${value} of 100`}>{value}</span>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}

export function PageHead({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p className="sub">{sub}</p>}
      </div>
      {children && <div className="row">{children}</div>}
    </header>
  );
}

export function Field({ label, hint, children, wide }: { label: string; hint?: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <label className={`field ${wide ? 'wide' : ''}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </label>
  );
}

/** A list of short strings edited as removable chips. */
export function Chips({ value, onChange, placeholder }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const parts = draft.split(',').map((s) => s.trim()).filter(Boolean);
    if (parts.length) onChange([...value, ...parts.filter((p) => !value.includes(p))]);
    setDraft('');
  };
  return (
    <div className="chips">
      {value.map((v) => (
        <span key={v} className="chip">
          {v}
          <button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(value.filter((x) => x !== v))}>×</button>
        </span>
      ))}
      <input
        value={draft}
        placeholder={placeholder ?? 'Add…'}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(); } }}
        onBlur={add}
      />
    </div>
  );
}

/** Local editable copy of server data; resets when the server value changes. */
export function useDraft<T>(server: T | undefined): [T | undefined, (v: T) => void, boolean] {
  const key = JSON.stringify(server);
  const [draft, setDraft] = useState<T | undefined>(server);
  const [base, setBase] = useState(key);
  if (key !== base) {
    setBase(key);
    setDraft(server);
  }
  return [draft, setDraft, JSON.stringify(draft) !== key];
}

// -------------------------------------------------------------------- time ---
export function ago(iso: string | null | undefined): string {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 31) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function day(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' });
}

export const STATE_LABEL: Record<string, string> = {
  waiting: 'Waiting', filling: 'Filling', paused: 'Filled, paused for review',
  submitted: 'Submitted', needs_manual: 'Needs manual',
};
export const STATE_TONE: Record<string, string> = {
  waiting: 'muted', filling: 'info', paused: 'warn', submitted: 'good', needs_manual: 'bad',
};
export const RELATIONSHIPS: [string, string][] = [
  ['former_colleague', 'Former colleague'], ['alumni', 'Alumni'],
  ['connection', 'Connection'], ['hiring_team', 'Hiring team (2nd degree)'],
];
