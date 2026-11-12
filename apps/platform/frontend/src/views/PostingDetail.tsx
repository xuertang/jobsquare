import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { AddContact, AnswerTable, ContactCard } from '../parts';
import type { PostingDetail } from '../types';
import { Btn, Empty, Pill, STATE_LABEL, STATE_TONE, Score, ago, day, useAct } from '../ui';

export default function PostingPage() {
  const { id } = useParams();
  const { hash } = useLocation();
  const navigate = useNavigate();
  const act = useAct('posting', 'matches', 'status', 'applications');
  const { data, error, isLoading } = useQuery({
    queryKey: ['posting', id], queryFn: () => api.get<PostingDetail>(`/postings/${id}`),
  });
  useEffect(() => {
    if (data && hash) document.querySelector(hash)?.scrollIntoView({ behavior: 'smooth' });
  }, [data === undefined, hash]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading) return <p className="dim">Loading…</p>;
  if (error || !data) return <Empty title="Posting not found"><Link to="/matches">Back to matches</Link></Empty>;
  const { posting: p, match: m, application: app, contacts, search_links: links, duplicate } = data;
  const matchPost = (path: string, body?: unknown, done?: string) =>
    act(() => api.post(`/matches/${m!.id}/${path}`, body), done);

  return (
    <div className="stack" style={{ gap: 16 }}>
      <Link to="/matches" className="dim">← Matches</Link>
      <header className="card stack">
        <div className="spread">
          <div className="row grow" style={{ alignItems: 'flex-start' }}>
            <Score value={m?.score ?? null} error={m?.score_error} />
            <div className="grow">
              <h1>{p.title}</h1>
              <div className="row dim">
                <strong style={{ color: 'var(--ink)' }}>{p.company}</strong>
                <span>{p.location || 'Location not stated'}</span>
                {p.remote && <Pill tone="accent">Remote</Pill>}
                {p.salary_range && <span>{p.salary_range}</span>}
                <span>{p.posted_at ? `posted ${day(p.posted_at)}` : `first seen ${ago(p.first_seen)}`}</span>
                <span>{p.ats_type}</span>
                {p.closed && <Pill tone="bad">Closed</Pill>}
                {app && <Pill tone={STATE_TONE[app.state]}>{STATE_LABEL[app.state]}</Pill>}
              </div>
            </div>
          </div>
          <div className="row">
            <a className="btn small" href={p.url} target="_blank" rel="noreferrer">View posting</a>
            {m?.state === 'new' && (
              <>
                <Btn small kind="primary" onAct={() => matchPost('approve', undefined, 'Added to the apply queue')}>Approve for apply</Btn>
                <Btn small kind="ghost" onAct={() => matchPost('snooze', { days: 7 })}>Snooze</Btn>
                <Btn small kind="ghost" onAct={async () => { await matchPost('dismiss'); navigate('/matches'); }}>Dismiss</Btn>
              </>
            )}
            {m && (m.state === 'dismissed' || m.state === 'snoozed') && (
              <Btn small onAct={() => matchPost('restore')}>Move back to New</Btn>
            )}
            {m?.state === 'approved' && app?.state !== 'submitted' && <Link className="btn small" to="/queue">Open apply queue</Link>}
          </div>
        </div>
        {m?.rationale && <p className="pre">{m.rationale}</p>}
        {m && m.score === null && !m.score_error && <p className="dim">Not scored yet.</p>}
        {m?.score_error && <p className="bad-text">Scoring failed: {m.score_error}</p>}
        {m && (m.score !== null || m.score_error) && (
          <div><Btn small kind="ghost" onAct={() => matchPost('rescore', undefined, 'Rescoring')}>Rescore</Btn></div>
        )}
        {duplicate && (
          <p className="notice warn">
            Same requisition as <Link to={`/postings/${duplicate.posting_id}`}>{duplicate.title}</Link>,
            which is already in your pipeline ({STATE_LABEL[duplicate.state] ?? duplicate.state}).
          </p>
        )}
      </header>

      <section className="card" id="referral">
        <div className="spread" style={{ marginBottom: 10 }}>
          <h2 style={{ margin: 0 }}>Referral</h2>
          <span className="dim">{contacts.length ? `${contacts.length} contact${contacts.length === 1 ? '' : 's'} at ${p.company}, strongest first` : ''}</span>
        </div>
        {contacts.length ? (
          <div>{contacts.map((c) => <ContactCard key={c.id} contact={c} postings={[{ id: p.id, title: p.title }]} />)}</div>
        ) : (
          <p className="dim">No first-degree connections at {p.company} in your imported contacts.</p>
        )}
        <div className="card flat stack" style={{ marginTop: 14 }}>
          <div>
            <strong>Find a second-degree contact</strong>
            <p className="hint">These open a LinkedIn people search in your own browser. Found someone? Add them below and draft a note.</p>
          </div>
          <div className="row">
            {links.map((l) => <a key={l.url} className="btn small" href={l.url} target="_blank" rel="noreferrer">{l.label}</a>)}
          </div>
          <AddContact company={p.company} />
        </div>
      </section>

      {app && (
        <section className="card stack">
          <div className="spread">
            <h2 style={{ margin: 0 }}>Application</h2>
            <span className="dim">
              {app.state === 'submitted' ? `Submitted ${day(app.submitted_at)}` : STATE_LABEL[app.state]}
              {app.resume_variant ? ` · resume: ${app.resume_variant}` : ''}
            </span>
          </div>
          {app.manual_reason && <p className="notice warn">{app.manual_reason}</p>}
          <AnswerTable applicationId={app.id} answers={app.answers ?? []} editable={app.state !== 'submitted'} />
        </section>
      )}

      <section className="card">
        <h2>Description</h2>
        {p.description ? <div className="pre desc">{p.description}</div>
          : <p className="dim">The description has not been fetched yet. <a href={p.url} target="_blank" rel="noreferrer">Read it on the careers site.</a></p>}
      </section>
    </div>
  );
}
