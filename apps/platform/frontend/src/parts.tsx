// Pieces shared by several views: the answer review table and the outreach
// contact card with its message composer.
import { useState } from 'react';
import { api } from './api';
import type { Answer, Contact, Message } from './types';
import { Btn, Copy, Pill, RELATIONSHIPS, ago, day, useAct } from './ui';

const SOURCE: Record<string, [string, string]> = {
  profile: ['Profile', 'muted'], bank: ['Answer bank', 'accent'],
  llm: ['Claude draft', 'warn'], manual: ['You', 'info'],
};

/** Every question on a form with what went into it, and why anything is
 *  blank. LLM-drafted and low-confidence answers are highlighted. */
export function AnswerTable({ applicationId, answers, editable = true }: {
  applicationId: number; answers: Answer[]; editable?: boolean;
}) {
  const act = useAct('applications', 'application', 'posting');
  const [editing, setEditing] = useState<number | null>(null);
  const [text, setText] = useState('');
  if (!answers.length) return <p className="dim">No answers recorded yet.</p>;
  return (
    <div className="scroll-x">
      <table className="answers">
        <thead><tr><th>Question</th><th>Answer</th><th>Source</th><th /></tr></thead>
        <tbody>
          {answers.map((a) => (
            <tr key={a.id} className={`${a.flagged ? 'flag' : ''} ${a.status !== 'filled' ? 'unfilled' : ''}`}>
              <td>
                {a.question}
                {a.category === 'demographic' && <> <Pill>self-ID</Pill></>}
                {a.category === 'consent' && <> <Pill>consent</Pill></>}
              </td>
              <td>
                {editing === a.id ? (
                  <div className="stack">
                    <textarea value={text} onChange={(e) => setText(e.target.value)} autoFocus />
                    <div className="row">
                      <Btn small kind="primary" onAct={async () => {
                        await act(() => api.patch(`/applications/${applicationId}/answers/${a.id}`, { answer: text }));
                        setEditing(null);
                      }}>Save</Btn>
                      <Btn small onClick={() => setEditing(null)}>Cancel</Btn>
                    </div>
                  </div>
                ) : (
                  <>
                    {a.status === 'filled' ? <span className="pre">{a.answer}</span>
                      : <span>{a.status === 'failed' ? 'Could not be filled' : 'Left blank'}</span>}
                    {a.note && <div className="hint">{a.note}</div>}
                  </>
                )}
              </td>
              <td>
                <div className="row">
                  {a.status === 'filled' && <Pill tone={SOURCE[a.source][1]}>{SOURCE[a.source][0]}</Pill>}
                  {a.status === 'failed' && <Pill tone="bad">Failed</Pill>}
                  {a.flagged && <Pill tone="warn" title="Review this before submitting">Review</Pill>}
                  {a.edited && <Pill tone="info" title="Changed after it was filled">Edited</Pill>}
                </div>
              </td>
              <td>
                <div className="row">
                  {a.status === 'filled' && <Copy text={a.answer} />}
                  {editable && editing !== a.id && (
                    <Btn small onClick={() => { setEditing(a.id); setText(a.answer); }}>Edit</Btn>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const STATUS_TONE: Record<string, string> = {
  none: 'muted', drafted: 'muted', sent: 'info', replied: 'accent',
  referred: 'good', declined: 'bad', no_response: 'muted',
};
const STATUS_LABEL: Record<string, string> = {
  none: 'Not contacted', drafted: 'Draft ready', sent: 'Sent', replied: 'Replied',
  referred: 'Referred', declined: 'Declined', no_response: 'No response',
};

/** A draft the user copies into LinkedIn. The log button sits next to copy. */
export function Composer({ message, profileUrl }: { message: Message; profileUrl: string }) {
  const act = useAct('outreach', 'posting', 'status');
  const [body, setBody] = useState(message.body);
  const [seen, setSeen] = useState(message.body);
  if (message.body !== seen) {          // redrafted on the server
    setSeen(message.body);
    setBody(message.body);
  }
  const over = body.length > message.char_cap;
  const save = () => (body !== message.body
    ? act(() => api.patch(`/messages/${message.id}`, { body })) : Promise.resolve());
  return (
    <div className="composer">
      <div className="spread">
        <span className="dim">
          {message.kind === 'followup' ? 'Follow-up nudge' : 'Message draft'}
          {message.posting_title ? ` about ${message.posting_title}` : ''}
          {' · '}{message.source === 'llm' ? 'drafted by Claude' : message.source === 'template' ? 'template' : 'edited by you'}
        </span>
        <span className={`num count ${over ? 'over' : 'dim'}`}>{body.length} / {message.char_cap}</span>
      </div>
      <textarea value={body} onChange={(e) => setBody(e.target.value)} onBlur={save}
                aria-label="Message draft" />
      {over && <p className="bad-text hint">Over the character limit. Trim it before sending.</p>}
      <div className="row">
        <Copy text={body} label="Copy message" kind="primary" />
        <Btn small onAct={async () => { await save(); await act(() => api.post(`/messages/${message.id}/sent`), 'Logged as sent'); }}>
          Mark sent
        </Btn>
        {profileUrl && <a className="btn small" href={profileUrl} target="_blank" rel="noreferrer">Open profile</a>}
        <span className="grow" />
        <Btn small kind="ghost" onAct={() => act(() => api.post('/messages/draft', {
          contact_id: message.contact_id, posting_id: message.posting_id, kind: message.kind, regenerate: true,
        }))}>Redraft</Btn>
        <Btn small kind="ghost" onAct={() => act(() => api.del(`/messages/${message.id}`))}>Discard</Btn>
      </div>
    </div>
  );
}

export function ContactCard({ contact, postings }: {
  contact: Contact; postings: { id: number; title: string }[];
}) {
  const act = useAct('outreach', 'posting', 'status');
  const [postingId, setPostingId] = useState<number | null>(postings[0]?.id ?? null);
  const [shared, setShared] = useState(contact.shared_context);
  const [replying, setReplying] = useState(false);
  const [reply, setReply] = useState({ outcome: 'replied', body: '' });
  const messages = contact.messages ?? [];
  const status = contact.status ?? 'none';
  const patch = (fields: Partial<Contact>) => act(() => api.patch(`/contacts/${contact.id}`, fields));
  return (
    <div className="contact">
      <div className="spread">
        <div className="grow">
          <div className="row">
            <strong>{contact.profile_url
              ? <a href={contact.profile_url} target="_blank" rel="noreferrer">{contact.name}</a>
              : contact.name}</strong>
            <Pill tone={STATUS_TONE[status]}>{STATUS_LABEL[status] ?? status}</Pill>
            {contact.source === 'manual' && <Pill>added by hand</Pill>}
          </div>
          <div className="dim">
            {[contact.title, contact.company].filter(Boolean).join(' · ')}
            {contact.connected_on ? ` · connected ${day(contact.connected_on)}` : ''}
          </div>
          {contact.hint && <div className="hint">{contact.hint}. Former colleague?</div>}
        </div>
        <select value={contact.relationship_type} aria-label="Relationship"
                onChange={(e) => patch({ relationship_type: e.target.value })}>
          {RELATIONSHIPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <input value={shared} placeholder="What you share (a team, a project, a school). The draft will use it."
             onChange={(e) => setShared(e.target.value)} aria-label="Shared context"
             onBlur={() => shared !== contact.shared_context && patch({ shared_context: shared })} />
      {messages.map((m) => (m.direction === 'out' && !m.sent_at
        ? <Composer key={m.id} message={m} profileUrl={contact.profile_url} />
        : (
          <div key={m.id} className={`msg ${m.direction}`}>
            <div className="dim hint row">
              {m.direction === 'out'
                ? `You${m.kind === 'followup' ? ' (follow-up)' : ''}, sent ${ago(m.sent_at)}`
                : `${contact.name.split(' ')[0]} · ${m.outcome ? STATUS_LABEL[m.outcome] : 'replied'} ${ago(m.sent_at)}`}
              {m.direction === 'out' && (
                <Btn small kind="ghost" onAct={() => act(() => api.post(`/messages/${m.id}/unsent`))}>Undo sent</Btn>
              )}
            </div>
            {m.body && <div className="pre">{m.body}</div>}
          </div>
        )))}
      <div className="row">
        {postings.length > 1 && (
          <select value={postingId ?? ''} onChange={(e) => setPostingId(Number(e.target.value))}
                  aria-label="Role to mention" style={{ maxWidth: 260 }}>
            {postings.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
          </select>
        )}
        <Btn small kind="primary" onAct={() => act(() => api.post('/messages/draft', {
          contact_id: contact.id, posting_id: postingId,
        }))}>Draft message</Btn>
        <Btn small onClick={() => setReplying(!replying)}>Log reply</Btn>
        <span className="grow" />
        <Btn small kind="ghost" onAct={async () => {
          if (confirm(`Remove ${contact.name} and their message history?`)) await act(() => api.del(`/contacts/${contact.id}`));
        }}>Remove</Btn>
      </div>
      {replying && (
        <div className="composer">
          <div className="row">
            <select value={reply.outcome} onChange={(e) => setReply({ ...reply, outcome: e.target.value })}
                    style={{ width: 'auto' }} aria-label="Outcome">
              <option value="replied">Replied</option>
              <option value="referred">Referred me</option>
              <option value="declined">Declined</option>
              <option value="no_response">No response</option>
            </select>
            <input className="grow" placeholder="Notes or what they said (optional)" value={reply.body}
                   onChange={(e) => setReply({ ...reply, body: e.target.value })} />
            <Btn small kind="primary" onAct={async () => {
              await act(() => api.post(`/contacts/${contact.id}/reply`, { ...reply, posting_id: postingId }), 'Logged');
              setReplying(false);
              setReply({ outcome: 'replied', body: '' });
            }}>Save</Btn>
          </div>
        </div>
      )}
    </div>
  );
}

/** Add a contact by hand: a second-degree target found through a search link. */
export function AddContact({ company }: { company?: string }) {
  const act = useAct('outreach', 'posting', 'matches');
  const blank = { name: '', title: '', profile_url: '', company: company ?? '', relationship_type: 'hiring_team' };
  const [c, setC] = useState(blank);
  return (
    <div className="form-grid">
      <input placeholder="Name" value={c.name} onChange={(e) => setC({ ...c, name: e.target.value })} aria-label="Name" />
      <input placeholder="Profile URL" value={c.profile_url} onChange={(e) => setC({ ...c, profile_url: e.target.value })} aria-label="Profile URL" />
      <input placeholder="Title" value={c.title} onChange={(e) => setC({ ...c, title: e.target.value })} aria-label="Title" />
      {!company && <input placeholder="Company" value={c.company} onChange={(e) => setC({ ...c, company: e.target.value })} aria-label="Company" />}
      <select value={c.relationship_type} onChange={(e) => setC({ ...c, relationship_type: e.target.value })} aria-label="Relationship">
        {RELATIONSHIPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      <Btn kind="primary" disabled={!c.name.trim()} onAct={async () => {
        const out = await act(() => api.post('/contacts', c), 'Contact added');
        if (out) setC(blank);
      }}>Add contact</Btn>
    </div>
  );
}
