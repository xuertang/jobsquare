import { useQuery } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { AddContact, Composer, ContactCard } from '../parts';
import type { OutreachBoard } from '../types';
import { Btn, Empty, PageHead, Pill, ago, useAct, useToast } from '../ui';

type Tab = 'companies' | 'followups' | 'log';

export function ImportContacts() {
  const act = useAct('outreach', 'matches', 'status');
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input ref={input} type="file" accept=".csv,text/csv" hidden onChange={async (e) => {
        const file = e.target.files?.[0];
        e.target.value = '';
        if (!file) return;
        const form = new FormData();
        form.append('file', file);
        const out = await act(() => api.post<{ rows: number; created: number; updated: number }>('/contacts/import', form));
        if (out) toast(`Imported ${out.rows} contacts: ${out.created} new, ${out.updated} updated`);
      }} />
      <Btn onClick={() => input.current?.click()}>Import LinkedIn connections CSV</Btn>
    </>
  );
}

export default function Outreach() {
  const [tab, setTab] = useState<Tab>('companies');
  const [adding, setAdding] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ['outreach'], queryFn: () => api.get<OutreachBoard>('/outreach'),
  });
  const due = data?.followups.length ?? 0;
  return (
    <>
      <PageHead title="Outreach" sub="Who you know at companies with open matches. You send every message yourself.">
        <Btn onClick={() => setAdding(!adding)}>Add contact</Btn>
        <ImportContacts />
      </PageHead>
      {adding && <div className="card" style={{ marginBottom: 14 }}><AddContact /></div>}
      <div className="tabs" role="tablist">
        {([['companies', 'By company', data?.companies.length], ['followups', 'Follow-ups due', due],
           ['log', 'Sent log', data?.log.length]] as [Tab, string, number | undefined][]).map(([key, label, n]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'on' : ''}
                  onClick={() => setTab(key)}>{label}<em className="num">{n ?? 0}</em></button>
        ))}
      </div>
      {isLoading || !data ? <p className="dim">Loading…</p> : tab === 'companies' ? (
        !data.companies.length ? (
          <Empty title={data.contact_total ? 'No contacts at companies with open matches' : 'No contacts yet'}>
            {data.contact_total
              ? `${data.contact_total} contacts imported. They appear here when their company has a match.`
              : 'On LinkedIn: Settings, Data privacy, Get a copy of your data, Connections. Import the CSV it gives you.'}
          </Empty>
        ) : (
          <div className="list">
            {data.companies.map((g) => (
              <section key={g.company_id} className="card stack">
                <div className="spread">
                  <h2 style={{ margin: 0 }}>{g.company}</h2>
                  <span className="dim">{g.contacts.length} contact{g.contacts.length === 1 ? '' : 's'}</span>
                </div>
                <RoleList postings={g.postings} />
                <div>{g.contacts.map((c) => <ContactCard key={c.id} contact={c} postings={g.postings} />)}</div>
              </section>
            ))}
          </div>
        )
      ) : tab === 'followups' ? (
        !due ? <Empty title="No follow-ups due">Contacts appear here when a sent message has had no reply for the wait you set.</Empty> : (
          <div className="list">
            {data.followups.map((f) => (
              <section key={f.id} className="card stack">
                <div className="spread">
                  <div>
                    <strong>{f.profile_url ? <a href={f.profile_url} target="_blank" rel="noreferrer">{f.name}</a> : f.name}</strong>
                    <div className="dim">
                      {[f.title, f.company].filter(Boolean).join(' · ')}
                      {f.posting_title ? ` · about ${f.posting_title}` : ''}
                    </div>
                  </div>
                  <Pill tone="warn">{f.days_waiting} days, no reply</Pill>
                </div>
                {f.draft && <Composer message={f.draft} profileUrl={f.profile_url} />}
                <FollowupClose contactId={f.id} postingId={f.posting_id} />
              </section>
            ))}
          </div>
        )
      ) : (
        !data.log.length ? <Empty title="Nothing sent yet" /> : (
          <div className="card scroll-x" style={{ padding: 0 }}>
            <table className="data">
              <thead><tr><th>When</th><th>Contact</th><th>About</th><th>Message</th></tr></thead>
              <tbody>
                {data.log.map((m) => (
                  <tr key={m.id}>
                    <td className="num" style={{ whiteSpace: 'nowrap' }}>{ago(m.sent_at ?? m.drafted_at)}</td>
                    <td>
                      {m.profile_url ? <a href={m.profile_url} target="_blank" rel="noreferrer">{m.contact_name}</a> : m.contact_name}
                      <div className="dim">{m.contact_company}</div>
                    </td>
                    <td>{m.posting_id ? <Link to={`/postings/${m.posting_id}`}>{m.posting_title}</Link> : <span className="dim">general</span>}</td>
                    <td>
                      <div className="row">
                        <Pill tone={m.direction === 'in' ? 'good' : m.sent_at ? 'info' : 'muted'}>
                          {m.direction === 'in' ? (m.outcome ?? 'reply').replace('_', ' ') : m.sent_at ? (m.kind === 'followup' ? 'follow-up sent' : 'sent') : 'draft'}
                        </Pill>
                      </div>
                      <div className="pre dim" style={{ maxWidth: 460 }}>{m.body.length > 220 ? `${m.body.slice(0, 220)}…` : m.body}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </>
  );
}

/** Open roles at a company, best fit first. Long lists fold away. */
function RoleList({ postings }: { postings: OutreachBoard['companies'][number]['postings'] }) {
  const [all, setAll] = useState(false);
  const shown = all ? postings : postings.slice(0, 4);
  return (
    <div className="roles">
      {shown.map((p) => (
        <Link key={p.id} to={`/postings/${p.id}#referral`} className="role">
          <span className={`num ${p.score === null ? 'dim' : ''}`}>{p.score ?? 'n/a'}</span>
          {p.title}
          {p.state === 'approved' && <Pill tone="accent">in apply queue</Pill>}
        </Link>
      ))}
      {postings.length > 4 && (
        <button type="button" className="btn small ghost" onClick={() => setAll(!all)}>
          {all ? 'Show fewer' : `+${postings.length - 4} more roles`}
        </button>
      )}
    </div>
  );
}

function FollowupClose({ contactId, postingId }: { contactId: number; postingId: number | null }) {
  const act = useAct('outreach', 'status');
  const log = (outcome: string, done: string) => act(
    () => api.post(`/contacts/${contactId}/reply`, { outcome, posting_id: postingId, body: '' }), done);
  return (
    <div className="row dim">
      <span>Or close it out:</span>
      <Btn small kind="ghost" onAct={() => log('replied', 'Logged a reply')}>They replied</Btn>
      <Btn small kind="ghost" onAct={() => log('no_response', 'Closed as no response')}>Stop following up</Btn>
    </div>
  );
}
