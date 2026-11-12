import { useEffect, useState } from 'react'
import { fullName, type Profile } from '../lib/profile'
import type { BlockedFrames, FillResult, PreviewItem, ScanPreview } from '../lib/messages'
import { addCustomAnswer, getApplications, getProfile } from '../lib/storage'
import { fieldOptions, getActiveTab, openOptions, ping, runTree } from './api'
import { Logo } from './Logo'
import { ProfileTab } from './ProfileTab'

type Status = 'loading' | 'unsupported' | 'ready' | 'empty-profile'
type Tab = 'autofill' | 'profile'

/** Honest profile completeness across the fields that actually matter. */
export function profileCompleteness(p: Profile): number {
  const weighted: Array<[boolean, number]> = [
    [!!p.firstName.trim(), 2],
    [!!p.lastName.trim(), 2],
    [!!p.email.trim(), 2],
    [!!p.phone.trim(), 2],
    [!!p.addressLine1.trim(), 1],
    [!!p.city.trim(), 1],
    [!!p.country.trim(), 1],
    [!!p.linkedin.trim(), 1],
    [!!p.currentCompany.trim(), 1],
    [!!p.currentTitle.trim(), 1],
    [!!p.workAuthorized, 1],
    [!!p.requireSponsorship, 1],
    [p.education.length > 0, 1],
    [p.experience.length > 0, 1],
    [!!p.resume, 2],
  ]
  const total = weighted.reduce((s, [, w]) => s + w, 0)
  const got = weighted.reduce((s, [ok, w]) => s + (ok ? w : 0), 0)
  return Math.round((got / total) * 100)
}

export function Popup() {
  const [status, setStatus] = useState<Status>('loading')
  const [tab, setTab] = useState<Tab>('autofill')
  const [tabId, setTabId] = useState<number | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [scanResult, setScanResult] = useState<FillResult | null>(null)
  const [scanPreview, setScanPreview] = useState<ScanPreview | null>(null)
  const [blocked, setBlocked] = useState<BlockedFrames | null>(null)
  const [fillResult, setFillResult] = useState<FillResult | null>(null)
  const [fieldsOpen, setFieldsOpen] = useState(false)
  const [appCount, setAppCount] = useState(0)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void (async () => {
      const [prof, apps] = await Promise.all([getProfile(), getApplications()])
      setProfile(prof)
      setAppCount(apps.length)

      const tab = await getActiveTab()
      if (!tab) {
        setStatus('unsupported')
        return
      }
      setTabId(tab.tabId)

      const reachable = await ping(tab.tabId)
      if (!reachable) {
        setStatus('unsupported')
        return
      }

      setStatus(profileCompleteness(prof) === 0 ? 'empty-profile' : 'ready')
      const scan = await runTree(tab.tabId, false)
      if (scan.ok) {
        setScanResult(scan.result)
        setScanPreview(scan.preview)
        setBlocked(scan.blocked ?? null)
      }
    })()
  }, [])

  async function rescan() {
    if (tabId == null) return
    const res = await runTree(tabId, false)
    if (res.ok) {
      setScanResult(res.result)
      setScanPreview(res.preview)
      setBlocked(res.blocked ?? null)
    }
  }

  async function handleFill() {
    if (tabId == null) return
    setBusy(true)
    setFillResult(null)
    const res = await runTree(tabId, true)
    setFillResult(res.ok ? res.result : null)
    setBusy(false)
    // Re-scan so the field breakdown reflects the post-fill state.
    await rescan()
  }

  /** Answer memory: save an unmatched question's answer to the profile, then
   * re-scan — the field should move from "No match" to "Will fill". */
  async function handleSaveAnswer(question: string, answer: string) {
    await addCustomAnswer(question, answer)
    await rescan()
  }

  const name = profile ? fullName(profile) : ''
  const completeness = profile ? profileCompleteness(profile) : 0

  return (
    <div className="popup">
      <header className="popup__header">
        <Logo size={28} />
        <div className="popup__brand">
          <span className="popup__title">Gongzuo</span>
          <span className="popup__subtitle">Job application autofill</span>
        </div>
        <button className="icon-btn" title="Edit profile" onClick={openOptions} aria-label="Edit profile">
          ⚙
        </button>
      </header>

      <nav className="tabs" role="tablist">
        <button
          className={'tabs__tab' + (tab === 'autofill' ? ' tabs__tab--active' : '')}
          role="tab"
          aria-selected={tab === 'autofill'}
          onClick={() => setTab('autofill')}
        >
          ✎ Autofill
        </button>
        <button
          className={'tabs__tab' + (tab === 'profile' ? ' tabs__tab--active' : '')}
          role="tab"
          aria-selected={tab === 'profile'}
          onClick={() => {
            setTab('profile')
            void getProfile().then(setProfile) // fresh copy in case options changed it
          }}
        >
          ◉ Profile
        </button>
      </nav>

      {tab === 'profile' && profile && (
        <ProfileTab profile={profile} onRefresh={() => void getProfile().then(setProfile)} />
      )}

      {tab === 'autofill' && (
        <>
      <section className="popup__profile">
        <div className="avatar">{(name || '?').slice(0, 1).toUpperCase()}</div>
        <div className="popup__profile-meta">
          <span className="popup__name">{name || 'No profile yet'}</span>
          <span className="popup__email">{profile?.email || 'Add your details to get started'}</span>
        </div>
        <span className={'pill ' + (completeness >= 70 ? 'pill--good' : 'pill--warn')}>
          {completeness}%
        </span>
      </section>

      {status === 'loading' && <p className="hint">Scanning page…</p>}

      {status === 'unsupported' && (
        <div className="card card--muted">
          <p>Gongzuo can't run on this page.</p>
          <p className="hint">
            Open a job application (Greenhouse, Lever, Workday, a company careers page…) and try
            again. Browser pages like <code>chrome://</code> and the Web Store are off-limits.
          </p>
        </div>
      )}

      {status === 'empty-profile' && (
        <div className="card card--warn">
          <p>Your profile is empty.</p>
          <button className="btn btn--primary" onClick={openOptions}>
            Set up your profile
          </button>
        </div>
      )}

      {(status === 'ready' || status === 'empty-profile') && scanResult && (
        <>
          <div className="stats">
            <button
              className={'stat stat--btn' + (fieldsOpen ? ' stat--open' : '')}
              onClick={() => setFieldsOpen((v) => !v)}
              aria-expanded={fieldsOpen}
            >
              <span className="stat__num">{scanResult.detected}</span>
              <span className="stat__label">fields found {fieldsOpen ? '▴' : '▾'}</span>
            </button>
            <button
              className={'stat stat--btn stat--accent' + (fieldsOpen ? ' stat--open' : '')}
              onClick={() => setFieldsOpen((v) => !v)}
              aria-expanded={fieldsOpen}
            >
              <span className="stat__num">{scanResult.filled}</span>
              <span className="stat__label">fillable {fieldsOpen ? '▴' : '▾'}</span>
            </button>
            {(scanResult.frames ?? 1) > 1 && (
              <div className="stat">
                <span className="stat__num">{scanResult.frames}</span>
                <span className="stat__label">frames</span>
              </div>
            )}
          </div>
          {fieldsOpen && scanPreview && (
            <FieldBreakdown
              preview={scanPreview}
              onSaveAnswer={handleSaveAnswer}
              onLoadOptions={
                tabId == null ? undefined : (q) => fieldOptions(tabId, q)
              }
            />
          )}
          {blocked && blocked.detected > 0 && (
            <div className="card card--warn">
              <p>
                {blocked.detected} {blocked.detected === 1 ? 'field' : 'fields'} found in an
                embedded frame from <code>{blocked.hosts[0] ?? 'another site'}</code> — not filled,
                because that site isn't a recognized application platform.
              </p>
              <p className="hint">
                If the real application lives there, open it directly (right-click the form → open
                frame in new tab) and fill it on its own page.
              </p>
            </div>
          )}
        </>
      )}

      {status === 'ready' && (
        <button
          className="btn btn--primary btn--block"
          onClick={handleFill}
          disabled={busy || (scanResult?.filled ?? 0) === 0}
        >
          {busy ? 'Filling…' : 'Fill this page'}
        </button>
      )}

      {fillResult && (
        <div className="result">
          <p className="result__headline">
            Filled <strong>{fillResult.filled}</strong>{' '}
            {fillResult.filled === 1 ? 'field' : 'fields'}
            {fillResult.skipped > 0 && (
              <span className="hint"> · {fillResult.skipped} skipped</span>
            )}
          </p>
          {fillResult.filledFields.length > 0 && (
            <ul className="chips">
              {dedupe(fillResult.filledFields).map((f) => (
                <li key={f} className="chip">
                  {f}
                </li>
              ))}
            </ul>
          )}
          {fillResult.filled === 0 && (
            <p className="hint">
              Nothing matched. Some forms hide fields until you scroll, or use widgets Gongzuo can't
              read. Try scrolling the form into view, then fill again.
            </p>
          )}
        </div>
      )}
        </>
      )}

      <footer className="popup__footer">
        <button className="link" onClick={openOptions}>
          Edit profile &amp; settings
        </button>
        {appCount > 0 && (
          <span className="hint">
            {appCount} tracked {appCount === 1 ? 'application' : 'applications'}
          </span>
        )}
      </footer>
    </div>
  )
}

function dedupe(items: string[]): string[] {
  return Array.from(new Set(items))
}

/** Control types that present a fixed list of choices. */
function isChoiceControl(control?: string): boolean {
  return !!control && /dropdown|radio|checkbox|select/i.test(control)
}

/** Inline "save this answer to my profile" editor for an unmatched question. */
function AddAnswer({
  question,
  options,
  control,
  onLoadOptions,
  onSave,
}: {
  question: string
  /** Page-offered choices when the field is a dropdown/radio; empty otherwise. */
  options?: string[]
  control?: string
  /** Fetches choices for a dropdown whose menu only exists while open. */
  onLoadOptions?: () => Promise<string[]>
  onSave: (question: string, answer: string) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [answer, setAnswer] = useState('')
  const [saving, setSaving] = useState(false)
  const [loaded, setLoaded] = useState<string[] | null>(null)
  const [loading, setLoading] = useState(false)
  const opts = loaded ?? options ?? []

  /** Open the editor; for a choice field with no scanned options, fetch them
   * now (the content script may briefly open the dropdown to read its menu). */
  async function openEditor() {
    setOpen(true)
    if ((options?.length ?? 0) > 0 || loaded || !onLoadOptions || !isChoiceControl(control)) return
    setLoading(true)
    try {
      setLoaded(await onLoadOptions())
    } finally {
      setLoading(false)
    }
  }

  /** Current picks, parsed from the box so typing and chips stay in agreement. */
  const parts = answer.split('|').map((p) => p.trim()).filter(Boolean)
  const chosen = new Set(parts.map((p) => p.toLowerCase()))
  /** Toggle a choice; several join with " | ", the matcher's alternatives syntax. */
  function toggle(opt: string) {
    const next = [...parts]
    const idx = next.findIndex((p) => p.toLowerCase() === opt.toLowerCase())
    if (idx >= 0) next.splice(idx, 1)
    else next.push(opt)
    setAnswer(next.join(' | '))
  }

  if (!open) {
    return (
      <button className="frow__add" onClick={() => void openEditor()}>
        + Add to profile
      </button>
    )
  }
  return (
    <div className="addanswer">
      {loading && <p className="addanswer__optlabel">Reading the options…</p>}
      {opts.length > 0 && (
        <>
          <p className="addanswer__optlabel">Options on this {control || 'field'}</p>
          <div className="addanswer__opts">
            {opts.map((opt) => (
              <button
                key={opt}
                type="button"
                className={
                  'addanswer__opt' + (chosen.has(opt.toLowerCase()) ? ' addanswer__opt--on' : '')
                }
                onClick={() => toggle(opt)}
                title={opt}
              >
                {opt}
              </button>
            ))}
          </div>
        </>
      )}
      <textarea
        className="addanswer__input"
        placeholder={
          opts.length ? 'Pick an option above, or type your own…' : 'Your answer for this question…'
        }
        value={answer}
        rows={2}
        autoFocus
        onChange={(e) => setAnswer(e.target.value)}
      />
      <div className="addanswer__actions">
        <button
          className="btn btn--primary btn--xs"
          disabled={saving || !answer.trim()}
          onClick={async () => {
            setSaving(true)
            try {
              await onSave(question, answer)
            } finally {
              setSaving(false)
            }
          }}
        >
          {saving ? 'Saving…' : 'Save & reuse'}
        </button>
        <button className="link" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      <p className="addanswer__hint">
        Saved locally as a custom answer — filled here and on any future application asking a
        similar question. Tip: list alternatives with “|” (e.g. “LinkedIn | Job board”) and
        dropdowns will try each until one matches.
      </p>
    </div>
  )
}

/** One expandable row: page-field name, control type, and the value/selection. */
function FieldRow({
  item,
  onSaveAnswer,
  onLoadOptions,
}: {
  item: PreviewItem
  onSaveAnswer: (question: string, answer: string) => Promise<void>
  onLoadOptions?: (question: string) => Promise<string[]>
}) {
  const [full, setFull] = useState(false)
  const clickable = item.value.length > 60
  // A recognized document slot with nothing stored needs an upload, not text.
  const isEmptyFileSlot = item.status === 'unmatched' && item.key.startsWith('file:')
  const canAddAnswer = item.status === 'unmatched' && !item.key && !!item.displayLabel

  return (
    <div className="frow">
      <div className="frow__top">
        <span className="frow__name" title={item.displayLabel}>
          {item.displayLabel || item.label}
        </span>
        {item.control && <span className="frow__type">{item.control}</span>}
      </div>
      {item.label && (
        <div
          className={'frow__map' + (clickable ? ' frow__map--clickable' : '')}
          onClick={clickable ? () => setFull((v) => !v) : undefined}
          title={clickable ? (full ? 'Collapse' : 'Show full value') : undefined}
        >
          <span className="frow__spec">{item.label}</span>
          {item.value ? (
            <span className={'frow__value' + (full ? ' frow__value--full' : '')}> → {item.value}</span>
          ) : (
            <span className="frow__missing"> → nothing stored yet</span>
          )}
        </div>
      )}
      {canAddAnswer && (
        <AddAnswer
          question={item.displayLabel}
          options={item.options}
          control={item.control}
          onLoadOptions={
            onLoadOptions ? () => onLoadOptions(item.displayLabel) : undefined
          }
          onSave={onSaveAnswer}
        />
      )}
      {isEmptyFileSlot && (
        <button className="frow__add" onClick={openOptions}>
          Upload in settings →
        </button>
      )}
    </div>
  )
}

const BREAKDOWN_GROUPS: { status: PreviewItem['status']; title: string; hint?: string }[] = [
  { status: 'fill', title: 'Will fill' },
  { status: 'skip', title: 'Skipped', hint: 'already has a value (turn on "Overwrite existing values" to replace)' },
  { status: 'unmatched', title: 'No match', hint: 'save an answer once — it fills here and on future applications' },
]

function FieldBreakdown({
  preview,
  onSaveAnswer,
  onLoadOptions,
}: {
  preview: ScanPreview
  onSaveAnswer: (question: string, answer: string) => Promise<void>
  onLoadOptions?: (question: string) => Promise<string[]>
}) {
  const groups = BREAKDOWN_GROUPS.map((g) => ({
    ...g,
    items: preview.items.filter((i) => i.status === g.status),
  })).filter((g) => g.items.length > 0)

  if (groups.length === 0) {
    return <p className="hint">No form fields detected on this page.</p>
  }

  return (
    <div className="fieldlist">
      {groups.map((g) => (
        <div className="fieldlist__group" key={g.status}>
          <div className={'fieldlist__head fieldlist__head--' + g.status}>
            {g.title} · {g.items.length}
          </div>
          {g.hint && <p className="fieldlist__hint">{g.hint}</p>}
          {g.items.map((item, idx) => (
            <FieldRow
              key={`${g.status}:${item.key || item.displayLabel}:${idx}`}
              item={item}
              onSaveAnswer={onSaveAnswer}
              onLoadOptions={onLoadOptions}
            />
          ))}
        </div>
      ))}
    </div>
  )
}
