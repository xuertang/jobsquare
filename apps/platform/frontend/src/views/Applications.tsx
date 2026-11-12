import { useQuery } from '@tanstack/react-query';
import { Fragment, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { AnswerTable } from '../parts';
import type { Application } from '../types';
import { Empty, PageHead, day, useAct } from '../ui';

const STATUSES = ['applied', 'screen', 'onsite', 'offer', 'rejected', 'withdrawn'];

export default function Applications() {
  const [open, setOpen] = useState<number | null>(null);
  const { data: apps, isLoading } = useQuery({
    queryKey: ['applications', 'submitted'],
    queryFn: () => api.get<Application[]>('/applications?scope=submitted'),
  });
  return (
    <>
      <PageHead title="Applications" sub="Everything you have submitted, with the answers that went in." />
      {isLoading ? <p className="dim">Loading…</p> : !apps?.length ? (
        <Empty title="No applications yet">Submitted applications are recorded here with their answers.</Empty>
      ) : (
        <div className="card scroll-x" style={{ padding: 0 }}>
          <table className="data">
            <thead>
              <tr><th>Role</th><th>Submitted</th><th>Resume</th><th>Status</th><th>Notes</th><th /></tr>
            </thead>
            <tbody>
              {apps.map((a) => (
                <Fragment key={a.id}>
                  <Row app={a} open={open === a.id} toggle={() => setOpen(open === a.id ? null : a.id)} />
                  {open === a.id && <tr><td colSpan={6}><Detail app={a} /></td></tr>}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function Row({ app, open, toggle }: { app: Application; open: boolean; toggle: () => void }) {
  const act = useAct('applications');
  const [notes, setNotes] = useState(app.notes);
  return (
    <tr>
      <td>
        <Link to={`/postings/${app.posting_id}`}><strong>{app.title}</strong></Link>
        <div className="dim">{app.company}</div>
      </td>
      <td className="num">{day(app.submitted_at)}</td>
      <td>{app.resume_variant || <span className="dim">not recorded</span>}</td>
      <td>
        <select value={app.status} aria-label="Status"
                onChange={(e) => act(() => api.patch(`/applications/${app.id}`, { status: e.target.value }))}>
          {STATUSES.map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
        </select>
      </td>
      <td style={{ minWidth: 200 }}>
        <input value={notes} placeholder="Add a note" aria-label="Notes" onChange={(e) => setNotes(e.target.value)}
               onBlur={() => notes !== app.notes && act(() => api.patch(`/applications/${app.id}`, { notes }))} />
      </td>
      <td><button type="button" className="btn small" onClick={toggle}>{open ? 'Hide' : 'Answers'}</button></td>
    </tr>
  );
}

function Detail({ app }: { app: Application }) {
  const { data } = useQuery({
    queryKey: ['application', app.id],
    queryFn: () => api.get<Application>(`/applications/${app.id}`),
  });
  return (
    <div className="stack" style={{ padding: '6px 0 10px' }}>
      <AnswerTable applicationId={app.id} answers={data?.answers ?? []} editable={false} />
      {app.screenshot_path ? (
        <details>
          <summary>Confirmation screenshot</summary>
          <img className="shot" src={`/api/applications/${app.id}/screenshot`} alt="Confirmation page" />
        </details>
      ) : <p className="dim">No confirmation screenshot (marked submitted by hand).</p>}
    </div>
  );
}
