import { useQuery } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api';
import type { BankEntry, Company, Criteria, Profile, Resume } from '../types';
import { Btn, Chips, Empty, Field, PageHead, Pill, ago, useAct, useDraft, useToast } from '../ui';
import { ImportContacts } from './Outreach';

const TABS: [string, string][] = [
  ['criteria', 'Search criteria'], ['profile', 'Profile'], ['resumes', 'Resumes'],
  ['answers', 'Answer bank'], ['companies', 'Companies'], ['app', 'Schedule and limits'],
  ['data', 'Import and export'],
];

export default function Settings() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'criteria';
  return (
    <>
      <PageHead title="Settings" sub="Everything here stays on this machine." />
      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'on' : ''}
                  onClick={() => setParams({ tab: key })}>{label}</button>
        ))}
      </div>
      {tab === 'criteria' && <CriteriaTab />}
      {tab === 'profile' && <ProfileTab />}
      {tab === 'resumes' && <ResumesTab />}
      {tab === 'answers' && <BankTab />}
      {tab === 'companies' && <CompaniesTab />}
      {tab === 'app' && <AppTab />}
      {tab === 'data' && <DataTab />}
    </>
  );
}

function useCriteria() {
  return useQuery({ queryKey: ['criteria'], queryFn: () => api.get<Criteria>('/settings/criteria') });
}

function SaveBar({ dirty, onSave, note }: { dirty: boolean; onSave: () => Promise<unknown>; note?: string }) {
  return (
    <div className="row" style={{ marginTop: 14 }}>
      <Btn kind="primary" disabled={!dirty} onAct={onSave}>Save changes</Btn>
      {dirty ? <span className="dim">Unsaved changes</span> : note && <span className="dim">{note}</span>}
    </div>
  );
}

// ---------------------------------------------------------------- criteria ---
function CriteriaTab() {
  const { data } = useCriteria();
  const act = useAct('criteria', 'matches', 'status');
  const [s, setS, dirty] = useDraft(data?.search);
  if (!s || !data) return <p className="dim">Loading…</p>;
  const set = (key: string, value: unknown) => setS({ ...s, [key]: value });
  return (
    <div className="card stack">
      <p className="dim">
        Cheap rules that run before any scoring, so the model only sees plausible matches.
        Saving re-filters every open posting.
      </p>
      <div className="form-grid">
        <Field label="Title must include one of" wide hint="Whole words or phrases, not case sensitive.">
          <Chips value={s.title_include} onChange={(v) => set('title_include', v)} />
        </Field>
        <Field label="Title must not include" wide>
          <Chips value={s.title_exclude} onChange={(v) => set('title_exclude', v)} />
        </Field>
        <Field label="Levels" wide hint="Read from the title. A title with no level word counts as mid.">
          <div className="row">
            {data.levels.map((level) => (
              <label key={level} className="row" style={{ gap: 4 }}>
                <input type="checkbox" checked={s.levels.includes(level)}
                       onChange={(e) => set('levels', e.target.checked
                         ? [...s.levels, level] : s.levels.filter((l: string) => l !== level))} />
                {level}
              </label>
            ))}
          </div>
        </Field>
        <Field label="Locations" wide hint="A posting passes if its location names any of these.">
          <Chips value={s.locations} onChange={(v) => set('locations', v)} />
        </Field>
        <Field label="Remote roles">
          <label className="row" style={{ gap: 6 }}>
            <input type="checkbox" checked={s.remote_ok} onChange={(e) => set('remote_ok', e.target.checked)} />
            Include remote postings
          </label>
        </Field>
        <Field label="Maximum age (days)" hint="Postings with no date are kept.">
          <input type="number" min={0} value={s.max_age_days ?? ''} onChange={(e) => set('max_age_days', Number(e.target.value) || 0)} />
        </Field>
        <Field label="Remote regions" wide hint="A remote posting must be unqualified (“Remote”) or name one of these.">
          <Chips value={s.remote_regions} onChange={(v) => set('remote_regions', v)} />
        </Field>
        <Field label="Excluded companies" wide>
          <Chips value={s.excluded_companies} onChange={(v) => set('excluded_companies', v)} placeholder="Add a company…" />
        </Field>
        <Field label="Preferences for scoring" wide hint="Free text the model reads next to your resume when it scores fit.">
          <textarea rows={4} value={s.preferences} onChange={(e) => set('preferences', e.target.value)} />
        </Field>
      </div>
      <SaveBar dirty={dirty} onSave={() => act(() => api.put('/settings/criteria', { search: s }), 'Saved. Re-filtering matches.')} />
    </div>
  );
}

// ----------------------------------------------------------------- profile ---
const CONTACT: [string, string][] = [
  ['first_name', 'First name'], ['last_name', 'Last name'], ['preferred_name', 'Preferred name'],
  ['email', 'Email'], ['phone', 'Phone'], ['address_line1', 'Street address'], ['city', 'City'],
  ['state', 'State'], ['zip', 'Postal code'], ['country', 'Country'],
];
const EXTRAS: [string, string][] = [
  ['current_company', 'Current company'], ['current_title', 'Current title'],
  ['years_experience', 'Years of experience'], ['notice_period', 'Notice period'],
  ['earliest_start', 'Earliest start'], ['how_heard', 'How did you hear about us'],
  ['willing_to_relocate', 'Willing to relocate (yes/no)'],
];
const DEMOGRAPHICS: [string, string][] = [
  ['gender', 'Gender'], ['race_ethnicity', 'Race or ethnicity'], ['hispanic_latino', 'Hispanic or Latino'],
  ['veteran_status', 'Veteran status'], ['disability_status', 'Disability status'], ['pronouns', 'Pronouns'],
];

function ProfileTab() {
  const { data } = useQuery({ queryKey: ['profile'], queryFn: () => api.get<Profile>('/settings/profile') });
  const act = useAct('profile');
  const [p, setP, dirty] = useDraft(data);
  if (!p) return <p className="dim">Loading…</p>;
  const set = (section: string, key: string, value: string) => setP({ ...p, [section]: { ...p[section], [key]: value } });
  const inputs = (section: string, fields: [string, string][]) => fields.map(([key, label]) => (
    <Field key={key} label={label}>
      <input value={p[section][key] ?? ''} onChange={(e) => set(section, key, e.target.value)} />
    </Field>
  ));
  const yesNo = (key: string, label: string) => (
    <Field label={label}>
      <select value={p.work_auth[key] ?? ''} onChange={(e) => set('work_auth', key, e.target.value)}>
        <option value="">Not set (leave the question for me)</option>
        <option value="yes">Yes</option><option value="no">No</option>
      </select>
    </Field>
  );
  return (
    <div className="stack">
      <div className="row">
        <Btn onAct={() => act(() => api.post('/settings/profile/import-job-ops'), 'Imported from the job-ops apply profile')}>
          Import from job-ops apply profile
        </Btn>
        <span className="dim">Copies the details you already entered for the job-ops plugin.</span>
      </div>
      <section className="card"><h2>Contact</h2><div className="form-grid">{inputs('contact', CONTACT)}</div></section>
      <section className="card">
        <h2>Links</h2>
        <div className="form-grid">
          {inputs('links', [['linkedin', 'LinkedIn'], ['github', 'GitHub'], ['website', 'Website'], ['portfolio', 'Portfolio']])}
        </div>
      </section>
      <section className="card">
        <h2>Work authorization</h2>
        <div className="form-grid">
          {yesNo('authorized', 'Authorized to work in the US')}
          {yesNo('requires_sponsorship', 'Requires visa sponsorship')}
          <Field label="Salary expectation" hint="Used for free-text salary questions only.">
            <input value={p.salary.expectation ?? ''} onChange={(e) => set('salary', 'expectation', e.target.value)} />
          </Field>
        </div>
      </section>
      <section className="card"><h2>Common answers</h2><div className="form-grid">{inputs('extras', EXTRAS)}</div></section>
      <Rows title="Work history" hint="Newest first. Feeds scoring, drafts, and the former-colleague hint on contacts."
            rows={p.work_history} onChange={(rows) => setP({ ...p, work_history: rows })}
            cols={[['company', 'Company'], ['title', 'Title'], ['start', 'Start (YYYY-MM)'], ['end', 'End or Present'], ['description', 'What you did']]} />
      <Rows title="Education" hint="Schools drive the alumni search links."
            rows={p.education} onChange={(rows) => setP({ ...p, education: rows })}
            cols={[['school', 'School'], ['degree', 'Degree'], ['field', 'Field'], ['start', 'Start'], ['end', 'End']]} />
      <section className="card">
        <h2>Self-identification defaults</h2>
        <p className="dim" style={{ marginBottom: 10 }}>
          Leave a field blank and that question is always left for you. Fill one in and it is used
          only when it matches an option on the form.
        </p>
        <div className="form-grid">{inputs('demographics', DEMOGRAPHICS)}</div>
      </section>
      <section className="card">
        <h2>Writing</h2>
        <div className="form-grid">
          <Field label="Summary" wide hint="Two or three sentences on who you are. Used in drafts and scoring.">
            <textarea rows={3} value={p.writing.summary ?? ''} onChange={(e) => set('writing', 'summary', e.target.value)} />
          </Field>
          <Field label="Writing style" wide hint="How you write. Drafted messages and answers follow it.">
            <textarea rows={5} value={p.writing.style ?? ''} onChange={(e) => set('writing', 'style', e.target.value)} />
          </Field>
        </div>
      </section>
      <SaveBar dirty={dirty} onSave={() => act(() => api.put('/settings/profile', p), 'Profile saved')} />
    </div>
  );
}

function Rows({ title, hint, rows, cols, onChange }: {
  title: string; hint: string; rows: Record<string, string>[]; cols: [string, string][];
  onChange: (rows: Record<string, string>[]) => void;
}) {
  return (
    <section className="card stack">
      <div><h2 style={{ marginBottom: 2 }}>{title}</h2><p className="dim">{hint}</p></div>
      {rows.map((row, i) => (
        <div key={i} className="form-grid" style={{ alignItems: 'end' }}>
          {cols.map(([key, label]) => (
            <Field key={key} label={label} wide={key === 'description'}>
              <input value={row[key] ?? ''} onChange={(e) => onChange(rows.map((r, j) => (j === i ? { ...r, [key]: e.target.value } : r)))} />
            </Field>
          ))}
          <Btn small kind="ghost" onClick={() => onChange(rows.filter((_, j) => j !== i))}>Remove</Btn>
        </div>
      ))}
      <div><Btn small onClick={() => onChange([...rows, Object.fromEntries(cols.map(([k]) => [k, '']))])}>Add row</Btn></div>
    </section>
  );
}

// ----------------------------------------------------------------- resumes ---
function ResumesTab() {
  const { data } = useQuery({ queryKey: ['resumes'], queryFn: () => api.get<Resume[]>('/settings/resumes') });
  const act = useAct('resumes');
  const file = useRef<HTMLInputElement>(null);
  const [label, setLabel] = useState('');
  const [keywords, setKeywords] = useState('');
  return (
    <div className="stack">
      <section className="card stack">
        <h2 style={{ margin: 0 }}>Add a resume variant</h2>
        <div className="form-grid" style={{ alignItems: 'end' }}>
          <Field label="Label"><input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="General, Backend, Payments…" /></Field>
          <Field label="Use when the title mentions" hint="Comma separated. Blank for the default.">
            <input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="payments, fintech" />
          </Field>
          <Field label="File" hint="PDF, DOC, DOCX, TXT or MD. Uploaded to the form as is.">
            <input ref={file} type="file" accept=".pdf,.doc,.docx,.txt,.md,.rtf" />
          </Field>
          <Btn kind="primary" disabled={!label.trim()} onAct={async () => {
            const form = new FormData();
            form.append('label', label);
            form.append('keywords', keywords);
            if (file.current?.files?.[0]) form.append('file', file.current.files[0]);
            const out = await act(() => api.post('/settings/resumes', form), 'Resume added');
            if (out) { setLabel(''); setKeywords(''); if (file.current) file.current.value = ''; }
          }}>Add</Btn>
        </div>
      </section>
      {!data?.length ? <Empty title="No resumes yet">Add one so forms can attach it and scoring can read it.</Empty>
        : data.map((r) => <ResumeCard key={r.id} resume={r} />)}
    </div>
  );
}

function ResumeCard({ resume }: { resume: Resume }) {
  const act = useAct('resumes');
  const [r, setR, dirty] = useDraft(resume);
  if (!r) return null;
  return (
    <section className="card stack">
      <div className="spread">
        <div className="row">
          <strong>{resume.label}</strong>
          {resume.is_default && <Pill tone="accent">Default</Pill>}
          {resume.has_file ? <span className="dim">{resume.filename}</span> : <Pill tone="warn">No file: cannot be attached</Pill>}
        </div>
        <div className="row">
          {!resume.is_default && <Btn small onAct={() => act(() => api.patch(`/settings/resumes/${resume.id}`, { is_default: true }))}>Make default</Btn>}
          <Btn small kind="danger" onAct={async () => {
            if (confirm(`Delete the resume “${resume.label}”?`)) await act(() => api.del(`/settings/resumes/${resume.id}`));
          }}>Delete</Btn>
        </div>
      </div>
      <div className="form-grid">
        <Field label="Label"><input value={r.label} onChange={(e) => setR({ ...r, label: e.target.value })} /></Field>
        <Field label="Use when the title mentions"><input value={r.keywords} onChange={(e) => setR({ ...r, keywords: e.target.value })} /></Field>
        <Field label="Text used for scoring and drafts" wide
               hint="Read from the file where possible. Email addresses and phone numbers are stripped before any of it is sent to the model.">
          <textarea rows={6} value={r.text} onChange={(e) => setR({ ...r, text: e.target.value })} />
        </Field>
      </div>
      {dirty && <SaveBar dirty onSave={() => act(() => api.patch(`/settings/resumes/${resume.id}`, {
        label: r.label, keywords: r.keywords, text: r.text }), 'Saved')} />}
    </section>
  );
}

// ------------------------------------------------------------- answer bank ---
function BankTab() {
  const { data } = useQuery({ queryKey: ['bank'], queryFn: () => api.get<BankEntry[]>('/settings/answers') });
  const act = useAct('bank');
  const [q, setQ] = useState({ question: '', answer: '' });
  return (
    <div className="stack">
      <p className="dim">
        Saved answers to custom application questions. A new form reuses one when its question is
        close enough; answers you edit or type before submitting are saved back here.
      </p>
      <section className="card stack">
        <Field label="Question"><input value={q.question} onChange={(e) => setQ({ ...q, question: e.target.value })} placeholder="Why do you want to work here?" /></Field>
        <Field label="Answer"><textarea rows={3} value={q.answer} onChange={(e) => setQ({ ...q, answer: e.target.value })} /></Field>
        <div><Btn kind="primary" disabled={!q.question.trim() || !q.answer.trim()} onAct={async () => {
          const out = await act(() => api.post('/settings/answers', q), 'Answer saved');
          if (out) setQ({ question: '', answer: '' });
        }}>Add answer</Btn></div>
      </section>
      {!data?.length ? <Empty title="The answer bank is empty" /> : data.map((e) => <BankCard key={e.id} entry={e} />)}
    </div>
  );
}

function BankCard({ entry }: { entry: BankEntry }) {
  const act = useAct('bank');
  const [e, setE, dirty] = useDraft(entry);
  if (!e) return null;
  return (
    <section className="card stack">
      <input value={e.question} onChange={(ev) => setE({ ...e, question: ev.target.value })} aria-label="Question" style={{ fontWeight: 600 }} />
      <textarea rows={3} value={e.answer} onChange={(ev) => setE({ ...e, answer: ev.target.value })} aria-label="Answer" />
      <div className="row">
        <span className="dim">{entry.uses ? `Used ${entry.uses} time${entry.uses === 1 ? '' : 's'}, last ${ago(entry.last_used)}` : 'Not used yet'}</span>
        <span className="grow" />
        {dirty && <Btn small kind="primary" onAct={() => act(() => api.patch(`/settings/answers/${entry.id}`, {
          question: e.question, answer: e.answer }), 'Saved')}>Save</Btn>}
        <Btn small kind="danger" onAct={() => act(() => api.del(`/settings/answers/${entry.id}`))}>Delete</Btn>
      </div>
    </section>
  );
}

// --------------------------------------------------------------- companies ---
const ATS = ['greenhouse', 'lever', 'ashby', 'smartrecruiters', 'workday'];
const FETCH_TONE: Record<string, string> = { ok: 'good', failed: 'bad', empty: 'warn', suspect: 'warn' };

function CompaniesTab() {
  const { data } = useQuery({ queryKey: ['companies'], queryFn: () => api.get<Company[]>('/settings/companies'), refetchInterval: 8000 });
  const act = useAct('companies', 'status');
  const toast = useToast();
  const [filter, setFilter] = useState('');
  const [attention, setAttention] = useState(false);
  const [c, setC] = useState({ name: '', ats_type: 'greenhouse', board_token: '', host: '', tenant: '', site: '' });
  const troubled = (data ?? []).filter((x) => x.active && x.last_status && x.last_status !== 'ok');
  const shown = (attention ? troubled : data ?? []).filter((x) =>
    !filter || `${x.name} ${x.board_token} ${x.ats_type}`.toLowerCase().includes(filter.toLowerCase()));
  return (
    <div className="stack">
      {troubled.length > 0 && (
        <p className="notice warn">
          {troubled.length} board{troubled.length === 1 ? '' : 's'} failed or came back empty on the last fetch.
          An empty board usually means it moved to another ATS or changed its token.{' '}
          <button type="button" className="btn small" onClick={() => setAttention(!attention)}>
            {attention ? 'Show all' : 'Show them'}
          </button>
        </p>
      )}
      <section className="card stack">
        <h2 style={{ margin: 0 }}>Add a company</h2>
        <div className="form-grid" style={{ alignItems: 'end' }}>
          <Field label="Name"><input value={c.name} onChange={(e) => setC({ ...c, name: e.target.value })} /></Field>
          <Field label="ATS">
            <select value={c.ats_type} onChange={(e) => setC({ ...c, ats_type: e.target.value })}>
              {ATS.map((a) => <option key={a}>{a}</option>)}
            </select>
          </Field>
          {c.ats_type === 'workday' ? (
            <>
              <Field label="Host" hint="nvidia.wd5.myworkdayjobs.com"><input value={c.host} onChange={(e) => setC({ ...c, host: e.target.value })} /></Field>
              <Field label="Tenant"><input value={c.tenant} onChange={(e) => setC({ ...c, tenant: e.target.value })} /></Field>
              <Field label="Site"><input value={c.site} onChange={(e) => setC({ ...c, site: e.target.value })} /></Field>
            </>
          ) : (
            <Field label="Board token" hint="The slug in the board URL."><input value={c.board_token} onChange={(e) => setC({ ...c, board_token: e.target.value })} /></Field>
          )}
          <Btn kind="primary" onAct={async () => {
            const body = c.ats_type === 'workday'
              ? { name: c.name, ats_type: 'workday', board_token: `https://${c.host}/en-US/${c.site}`,
                  board_config: { host: c.host, tenant: c.tenant, site: c.site, company: c.name } }
              : { name: c.name || c.board_token, ats_type: c.ats_type, board_token: c.board_token };
            const out = await act(() => api.post('/settings/companies', body), 'Company added');
            if (out) setC({ ...c, name: '', board_token: '', host: '', tenant: '', site: '' });
          }}>Add</Btn>
        </div>
      </section>
      <div className="row">
        <input placeholder="Filter companies" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ maxWidth: 260 }} aria-label="Filter companies" />
        <span className="dim">{shown.length} of {data?.length ?? 0}</span>
        <span className="grow" />
        <Btn onAct={async () => {
          const out = await act(() => api.post<{ added: number; out_of_scope: number }>('/settings/companies/sync'));
          if (out) toast(`Added ${out.added} board(s) from sources.yaml. ${out.out_of_scope} source(s) are not on a supported ATS and were skipped.`);
        }}>Sync from job-ops sources.yaml</Btn>
      </div>
      <div className="card scroll-x" style={{ padding: 0 }}>
        <table className="data">
          <thead><tr><th>Company</th><th>ATS</th><th>Board</th><th>Last fetch</th><th>Open</th><th>Active</th><th /></tr></thead>
          <tbody>
            {shown.map((x) => (
              <tr key={x.id}>
                <td><CompanyName company={x} /></td>
                <td>{x.ats_type}{x.ats_type === 'workday' && <div className="hint">manual apply</div>}</td>
                <td className="dim" style={{ maxWidth: 220, overflowWrap: 'anywhere' }}>{x.board_token}</td>
                <td>
                  {x.last_status ? <Pill tone={FETCH_TONE[x.last_status] ?? 'muted'}>{x.last_status}</Pill> : <span className="dim">never</span>}
                  {x.last_fetch_at && <span className="dim"> {ago(x.last_fetch_at)}</span>}
                  {x.last_error && <div className="hint" style={{ maxWidth: 300 }}>{x.last_error}</div>}
                </td>
                <td className="num">{x.open_postings}</td>
                <td>
                  <input type="checkbox" checked={x.active} aria-label={`${x.name} active`}
                         onChange={(e) => act(() => api.patch(`/settings/companies/${x.id}`, { active: e.target.checked }))} />
                </td>
                <td>
                  <div className="row">
                    <Btn small onAct={() => act(() => api.post(`/settings/companies/${x.id}/fetch`), `Fetching ${x.name}`)}>Fetch</Btn>
                    <Btn small kind="ghost" onAct={async () => {
                      if (confirm(`Delete ${x.name} and its postings?`)) await act(() => api.del(`/settings/companies/${x.id}`));
                    }}>Delete</Btn>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CompanyName({ company }: { company: Company }) {
  const act = useAct('companies');
  const [name, setName] = useState(company.name);
  const [aliases, setAliases] = useState(company.aliases);
  return (
    <div className="stack" style={{ gap: 4, minWidth: 170 }}>
      <input value={name} aria-label="Company name" onChange={(e) => setName(e.target.value)}
             onBlur={() => name !== company.name && name.trim() && act(() => api.patch(`/settings/companies/${company.id}`, { name }))} />
      <input value={aliases} placeholder="Other names, comma separated" aria-label="Aliases" style={{ fontSize: 12 }}
             title="Other names this company goes by on LinkedIn, for matching your contacts to it"
             onChange={(e) => setAliases(e.target.value)}
             onBlur={() => aliases !== company.aliases && act(() => api.patch(`/settings/companies/${company.id}`, { aliases }))} />
    </div>
  );
}

// -------------------------------------------------------------------- app ---
const APP_FIELDS: [string, string, string][] = [
  ['max_scores_per_run', 'Postings scored per run', 'A cost guard. The rest are scored on the next run.'],
  ['description_chars', 'Description characters sent', 'How much of a posting the model reads.'],
  ['digest_min_score', 'Digest minimum score', 'Matches at or above this go in the daily digest.'],
  ['followup_days', 'Follow up after (days)', 'No reply logged for this long puts a contact in follow-ups.'],
  ['max_followups', 'Follow-ups per contact', ''],
  ['char_cap_message', 'Message character limit', 'For people you are connected to.'],
  ['char_cap_connection_note', 'Connection note limit', 'For second-degree targets. LinkedIn caps these.'],
  ['daily_apply_cap', 'Applications per day', '0 means no cap. Blocks new fills once reached.'],
];

function AppTab() {
  const { data } = useCriteria();
  const act = useAct('criteria', 'status');
  const [a, setA, dirty] = useDraft(data?.app);
  if (!a) return <p className="dim">Loading…</p>;
  const time = `${String(a.fetch_hour).padStart(2, '0')}:${String(a.fetch_minute).padStart(2, '0')}`;
  return (
    <div className="card stack">
      <div className="form-grid">
        <Field label="Daily fetch time" hint="Local time. Fetch, filter, score, then the digest.">
          <input type="time" value={time} onChange={(e) => {
            const [h, m] = e.target.value.split(':').map(Number);
            if (!Number.isNaN(h) && !Number.isNaN(m)) setA({ ...a, fetch_hour: h, fetch_minute: m });
          }} />
        </Field>
        {APP_FIELDS.map(([key, label, hint]) => (
          <Field key={key} label={label} hint={hint}>
            <input type="number" min={0} value={a[key]} onChange={(e) => setA({ ...a, [key]: Number(e.target.value) })} />
          </Field>
        ))}
      </div>
      <SaveBar dirty={dirty} onSave={() => act(() => api.put('/settings/criteria', { app: a }), 'Saved')} />
    </div>
  );
}

// ------------------------------------------------------------------- data ---
function DataTab() {
  const act = useAct('criteria', 'profile', 'bank', 'companies', 'outreach', 'status');
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="stack">
      <section className="card stack">
        <h2 style={{ margin: 0 }}>Contacts</h2>
        <p className="dim">Import the connections CSV from your LinkedIn data export. Re-import any time: existing contacts are updated, and what you set by hand is kept.</p>
        <div><ImportContacts /></div>
      </section>
      <section className="card stack">
        <h2 style={{ margin: 0 }}>Export</h2>
        <p className="dim">Criteria, profile, answer bank, company list and contacts as one JSON file. Resume files are not included.</p>
        <div><Btn onAct={async () => {
          const data = await api.get('/settings/export');
          const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
          const a = document.createElement('a');
          a.href = url;
          a.download = `copilot-settings-${new Date().toISOString().slice(0, 10)}.json`;
          a.click();
          URL.revokeObjectURL(url);
        }}>Download settings</Btn></div>
      </section>
      <section className="card stack">
        <h2 style={{ margin: 0 }}>Import</h2>
        <p className="dim">Merge a settings file back in. Criteria and profile are replaced; answers, companies and contacts are added to what is here.</p>
        <input ref={input} type="file" accept="application/json,.json" hidden onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = '';
          if (!file) return;
          let body: unknown;
          try { body = JSON.parse(await file.text()); } catch { toast('That file is not valid JSON.', 'bad'); return; }
          const out = await act(() => api.post<Record<string, number>>('/settings/import', body));
          if (out) toast(`Imported: ${Object.entries(out).map(([k, v]) => `${v} ${k.replace('_', ' ')}`).join(', ')}`);
        }} />
        <div><Btn onClick={() => input.current?.click()}>Choose a settings file</Btn></div>
      </section>
    </div>
  );
}
