import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { useStatus } from '../App';
import { AnswerTable } from '../parts';
import type { Application } from '../types';
import { Btn, Empty, PageHead, Pill, STATE_LABEL, STATE_TONE, Score, useAct } from '../ui';

export default function ApplyQueue() {
  const { data: status } = useStatus();
  const { data: apps, isLoading } = useQuery({
    queryKey: ['applications', 'queue'],
    queryFn: () => api.get<Application[]>('/applications?scope=queue'),
    refetchInterval: 3000,
  });
  const automatable = apps?.some((a) => a.state !== 'needs_manual');
  return (
    <>
      <PageHead title="Apply queue"
                sub="Approved postings. The worker fills each form and stops; you review and submit." />
      {status && !status.worker.running && automatable && (
        <p className="notice warn" style={{ marginBottom: 14 }}>
          The apply worker is not running, so fills will wait. Start it on this machine
          with <code>python -m worker</code> from <code>apps/platform/backend</code>.
        </p>
      )}
      {isLoading ? <p className="dim">Loading…</p> : !apps?.length ? (
        <Empty title="The queue is empty">Approve a match and it shows up here.</Empty>
      ) : (
        <div className="list">{apps.map((a) => <QueueItem key={a.id} app={a} />)}</div>
      )}
    </>
  );
}

function QueueItem({ app }: { app: Application }) {
  const act = useAct('applications', 'status', 'matches');
  const [open, setOpen] = useState(app.state === 'paused' || app.state === 'needs_manual');
  const queued = app.fill_task?.state === 'queued';
  return (
    <article className="card stack">
      <div className="spread">
        <div className="row grow" style={{ alignItems: 'flex-start' }}>
          <Score value={app.score} />
          <div className="grow">
            <h3><Link to={`/postings/${app.posting_id}`}>{app.title}</Link></h3>
            <div className="row dim">
              <strong>{app.company}</strong>
              <span>{app.ats_type}</span>
              <Pill tone={STATE_TONE[app.state]}>{queued ? 'Waiting for the worker' : STATE_LABEL[app.state]}</Pill>
              {app.closed && <Pill tone="bad">Posting closed</Pill>}
              {app.resume_variant && <span>Resume: {app.resume_variant}</span>}
              {(app.answer_count ?? 0) > 0 && (
                <span className="num">
                  {app.answer_count} fields
                  {app.flagged_count ? `, ${app.flagged_count} to review` : ''}
                  {app.unfilled_count ? `, ${app.unfilled_count} left for you` : ''}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="row">
          {(app.state === 'waiting' && !queued) && (
            <Btn small kind="primary" onAct={() => act(() => api.post(`/applications/${app.id}/launch`), 'Fill queued')}>
              Launch fill
            </Btn>
          )}
          {(queued || app.state === 'filling') && (
            <Btn small onAct={() => act(() => api.post(`/applications/${app.id}/cancel-fill`))}>Cancel fill</Btn>
          )}
          {app.state === 'paused' && (
            <Btn small onAct={() => act(() => api.post(`/applications/${app.id}/launch`), 'Fill queued')}>Fill again</Btn>
          )}
          {app.state === 'needs_manual' && (
            <a className="btn small primary" href={app.apply_url} target="_blank" rel="noreferrer">Open form</a>
          )}
          <Btn small onClick={() => setOpen(!open)}>{open ? 'Hide answers' : 'Review answers'}</Btn>
          <Btn small onAct={async () => {
            if (confirm('Record this application as submitted? Only do this after you submitted the form yourself.')) {
              await act(() => api.post(`/applications/${app.id}/submitted`), 'Recorded as submitted');
            }
          }}>Mark submitted</Btn>
        </div>
      </div>
      {app.manual_reason && <p className={`notice ${app.state === 'needs_manual' ? 'warn' : ''}`}>{app.manual_reason}</p>}
      {app.state === 'paused' && (
        <p className="notice">
          The form is filled and waiting in the worker's browser window. Check the highlighted answers,
          fill what was left for you, then press submit there yourself.
          {app.fill_report.captcha && ' There is a CAPTCHA on the form: solve it before submitting.'}
          {app.fill_report.multi_step && ' This form has several steps: later steps are filled as you reach them.'}
        </p>
      )}
      {open && <QueueDetail app={app} />}
    </article>
  );
}

function QueueDetail({ app }: { app: Application }) {
  const act = useAct('applications', 'application', 'status', 'matches');
  const [question, setQuestion] = useState('');
  const { data } = useQuery({
    queryKey: ['application', app.id],
    queryFn: () => api.get<Application>(`/applications/${app.id}`),
    refetchInterval: app.state === 'paused' || app.state === 'filling' ? 3000 : false,
  });
  return (
    <div className="stack">
      <AnswerTable applicationId={app.id} answers={data?.answers ?? []} />
      {app.state === 'needs_manual' && (
        <div className="row">
          <input className="grow" placeholder="Paste a question from the form to get a saved or drafted answer"
                 value={question} onChange={(e) => setQuestion(e.target.value)} aria-label="Question from the form" />
          <Btn kind="primary" disabled={!question.trim()} onAct={async () => {
            const out = await act(() => api.post(`/applications/${app.id}/answers`, { question }));
            if (out) setQuestion('');
          }}>Get answer</Btn>
        </div>
      )}
      <div className="row">
        {app.state !== 'needs_manual' && (
          <Btn small kind="ghost" onAct={() => act(() => api.post(`/applications/${app.id}/manual`, {
            reason: 'Moved to the manual queue by you.',
          }))}>Move to manual queue</Btn>
        )}
        <Btn small kind="danger" onAct={async () => {
          if (confirm('Remove this posting from the apply queue? Its match goes back to New.')) {
            await act(() => api.del(`/applications/${app.id}`));
          }
        }}>Remove from queue</Btn>
      </div>
    </div>
  );
}
