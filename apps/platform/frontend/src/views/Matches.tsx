import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useStatus } from '../App';
import type { Match, MatchState } from '../types';
import { Btn, Empty, PageHead, Pill, STATE_LABEL, STATE_TONE, Score, ago, day, useAct } from '../ui';

const TABS: [MatchState, string][] = [
  ['new', 'New'], ['approved', 'Approved'], ['snoozed', 'Snoozed'], ['dismissed', 'Dismissed'],
];

export default function Matches() {
  const [state, setState] = useState<MatchState>('new');
  const [q, setQ] = useState('');
  const { data: status } = useStatus();
  const act = useAct('matches', 'status');
  const { data, isLoading } = useQuery({
    queryKey: ['matches', state, q],
    queryFn: () => api.get<{ matches: Match[]; counts: Record<string, number> }>(
      `/matches?state=${state}&q=${encodeURIComponent(q)}`),
    refetchInterval: status?.running.length ? 4000 : false,
  });
  const counts = data?.counts ?? {};
  const unscored = counts.unscored ?? 0;
  return (
    <>
      <PageHead title="Matches" sub="New postings that passed your filters, best fit first.">
        <input placeholder="Filter by title, company, location" value={q} style={{ width: 260 }}
               onChange={(e) => setQ(e.target.value)} aria-label="Filter matches" />
        {unscored > 0 && status?.llm.available && (
          <Btn onAct={() => act(() => api.post('/run/score'), 'Scoring started')}>Score {unscored} unscored</Btn>
        )}
      </PageHead>
      {unscored > 0 && status && !status.llm.available && (
        <p className="notice" style={{ marginBottom: 14 }}>
          {unscored} match{unscored === 1 ? ' is' : 'es are'} unscored. Set ANTHROPIC_API_KEY in the API's
          environment and restart it to get fit scores and rationales.
        </p>
      )}
      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={state === key} className={state === key ? 'on' : ''}
                  onClick={() => setState(key)}>
            {label}<em className="num">{counts[key] ?? 0}</em>
          </button>
        ))}
      </div>
      {isLoading ? <p className="dim">Loading…</p> : !data?.matches.length ? (
        <Empty title={q ? 'Nothing matches that filter' : state === 'new' ? 'No new matches' : 'Nothing here'}>
          {state === 'new' && !q && 'The daily fetch adds postings that pass your criteria. Use “Fetch now” in the sidebar to run it.'}
        </Empty>
      ) : (
        <div className="list">{data.matches.map((m) => <MatchCard key={m.id} m={m} />)}</div>
      )}
    </>
  );
}

function MatchCard({ m }: { m: Match }) {
  const act = useAct('matches', 'status', 'applications');
  const navigate = useNavigate();
  const post = (path: string, body?: unknown, done?: string) => act(() => api.post(`/matches/${m.id}/${path}`, body), done);
  return (
    <article className="card match">
      <Score value={m.score} error={m.score_error} />
      <div className="grow">
        <h3><Link to={`/postings/${m.posting_id}`}>{m.title}</Link></h3>
        <div className="meta">
          <strong>{m.company}</strong>
          <span>{m.location || 'Location not stated'}</span>
          {m.remote && <Pill tone="accent">Remote</Pill>}
          {m.salary_range && <span>{m.salary_range}</span>}
          <span title={day(m.posted_at ?? m.first_seen)}>
            {m.posted_at ? `posted ${ago(m.posted_at)}` : `seen ${ago(m.first_seen)}`}
          </span>
          {m.contacts > 0 && (
            <Link to={`/postings/${m.posting_id}#referral`}>
              <Pill tone="good">{m.contacts} contact{m.contacts === 1 ? '' : 's'}</Pill>
            </Link>
          )}
          {m.application_state && <Pill tone={STATE_TONE[m.application_state]}>{STATE_LABEL[m.application_state]}</Pill>}
          {m.state === 'snoozed' && m.snoozed_until && <Pill>until {day(m.snoozed_until)}</Pill>}
        </div>
        {m.rationale && <p className="why pre">{m.rationale}</p>}
        {!m.rationale && m.score_error && <p className="why bad-text">Scoring failed: {m.score_error}</p>}
      </div>
      <div className="actions">
        {m.state === 'new' ? (
          <>
            <Btn small kind="primary" onAct={() => post('approve', undefined, 'Added to the apply queue')}>Approve for apply</Btn>
            <Btn small onClick={() => navigate(`/postings/${m.posting_id}#referral`)}>Start referral</Btn>
            <Btn small kind="ghost" onAct={() => post('snooze', { days: 7 })}>Snooze 7 days</Btn>
            <Btn small kind="ghost" onAct={() => post('dismiss')}>Dismiss</Btn>
          </>
        ) : m.state === 'approved' ? (
          <Btn small onClick={() => navigate('/queue')}>Open apply queue</Btn>
        ) : (
          <Btn small onAct={() => post('restore')}>Move back to New</Btn>
        )}
      </div>
    </article>
  );
}
