import { type QueryClient, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import { api } from './api';
import type { Status } from './types';
import { Btn, clock, useAct } from './ui';
import Applications from './views/Applications';
import ApplyQueue from './views/ApplyQueue';
import Matches from './views/Matches';
import Outreach from './views/Outreach';
import PostingPage from './views/PostingDetail';
import Settings from './views/Settings';

export function useStatus() {
  return useQuery({ queryKey: ['status'], queryFn: () => api.get<Status>('/status'), refetchInterval: 5000 });
}

type AuthStatus = { required: boolean; configured: boolean; authenticated: boolean };

function signedOut(qc: QueryClient) {
  qc.setQueryData<AuthStatus>(['auth'], (old) => (old ? { ...old, authenticated: false } : old));
  qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'auth' });
}

/** A deployed copy asks for the password first. A local one has no login. */
export default function App() {
  const qc = useQueryClient();
  const { data: auth, error } = useQuery({
    queryKey: ['auth'], queryFn: () => api.get<AuthStatus>('/auth/status'), staleTime: 60_000,
  });
  useEffect(() => {
    // Any request refused with 401 means the session is gone: show the
    // sign-in screen now, and drop everything that was loaded under it.
    const onSignedOut = () => signedOut(qc);
    window.addEventListener('copilot:signed-out', onSignedOut);
    return () => window.removeEventListener('copilot:signed-out', onSignedOut);
  }, [qc]);
  if (error) return <div className="gate"><div className="card"><h1>Copilot</h1><p className="bad-text">{error.message}</p></div></div>;
  if (!auth) return null;
  if (!auth.authenticated) return <SignIn configured={auth.configured} />;
  return <Dashboard canSignOut={auth.required} />;
}

function SignIn({ configured }: { configured: boolean }) {
  const qc = useQueryClient();
  const [password, setPassword] = useState('');
  const [problem, setProblem] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <div className="gate">
      <form className="card stack" onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setProblem('');
        try {
          await api.post('/auth/login', { password });
          await qc.invalidateQueries();
        } catch (err) {
          setProblem(err instanceof Error ? err.message : String(err));
        } finally {
          setBusy(false);
        }
      }}>
        <div className="brand">
          <span className="mark" aria-hidden>✓</span>
          <div><strong>Copilot</strong><small>job search</small></div>
        </div>
        {configured ? (
          <>
            <label className="field">
              <span className="field-label">Password</span>
              <input type="password" value={password} autoFocus autoComplete="current-password"
                     onChange={(e) => setPassword(e.target.value)} />
            </label>
            {problem && <p className="bad-text">{problem}</p>}
            <button type="submit" className="btn primary" disabled={busy || !password}>Sign in</button>
          </>
        ) : (
          <p className="notice warn">
            No password is set on this server yet, so everything is locked.
            Run <code>deploy/set-password.sh</code> from your machine.
          </p>
        )}
      </form>
    </div>
  );
}

function Dashboard({ canSignOut }: { canSignOut: boolean }) {
  const qc = useQueryClient();
  const { data: status, error } = useStatus();
  const act = useAct('status', 'matches');
  const c = status?.counts;
  const running = status?.running ?? [];
  const nav: [string, string, number | undefined, boolean?][] = [
    ['/matches', 'Matches', c?.matches.new],
    ['/queue', 'Apply queue', c?.queue, (c?.paused ?? 0) > 0],
    ['/applications', 'Applications', c?.submitted],
    ['/outreach', 'Outreach', c?.followups, (c?.followups ?? 0) > 0],
    ['/settings', 'Settings', c?.companies_attention || undefined, (c?.companies_attention ?? 0) > 0],
  ];
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <span className="mark" aria-hidden>✓</span>
          <div>
            <strong>Copilot</strong>
            <small>job search</small>
          </div>
        </div>
        <nav>
          {nav.map(([to, label, count, hot]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'active' : '')}>
              <span>{label}</span>
              {count !== undefined && count > 0 && <em className={hot ? 'hot' : ''}>{count}</em>}
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          {error && <p className="bad-text">API unreachable</p>}
          {status && (
            <>
              <p>
                <i className={`dot ${running.length ? 'busy' : 'idle'}`} />
                {running.length ? `Running: ${running.map((t) => t.kind).join(', ')}` : 'Idle'}
              </p>
              <p title="Scoring, message drafts and custom answers use the Claude API">
                <i className={`dot ${status.llm.available ? 'on' : 'off'}`} />
                {status.llm.available ? 'Claude connected' : 'Claude not configured'}
              </p>
              <p title="The apply worker runs on your machine: python -m worker">
                <i className={`dot ${status.worker.running ? 'on' : 'off'}`} />
                {status.worker.running ? 'Apply worker running' : 'Apply worker stopped'}
              </p>
              {status.scheduler.next_run && <p className="dim">Next fetch {clock(status.scheduler.next_run)}</p>}
              <Btn small kind="ghost" disabled={running.some((t) => t.kind === 'daily')}
                   onAct={() => act(() => api.post('/run/daily'), 'Fetch started')}>
                Fetch now
              </Btn>
            </>
          )}
          {canSignOut && (
            <Btn small kind="ghost" onAct={async () => {
              await api.post('/auth/logout');
              signedOut(qc);
            }}>Sign out</Btn>
          )}
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/matches" replace />} />
          <Route path="/matches" element={<Matches />} />
          <Route path="/queue" element={<ApplyQueue />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="/outreach" element={<Outreach />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/postings/:id" element={<PostingPage />} />
          <Route path="*" element={<Navigate to="/matches" replace />} />
        </Routes>
      </main>
    </div>
  );
}
