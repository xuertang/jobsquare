import { useEffect, useRef, useState } from 'react'
import {
  emptyProfile,
  sampleProfile,
  type CustomAnswer,
  type Education,
  type Profile,
  type StoredFile,
  type WorkExperience,
} from '../lib/profile'
import {
  defaultSettings,
  getApplications,
  getProfile,
  getSettings,
  onProfileChange,
  saveApplications,
  saveProfile,
  saveSettings,
  type ApplicationStatus,
  type Settings,
  type TrackedApplication,
} from '../lib/storage'
import { buildInterviewPrepPrompt } from '../lib/interviewPrep'
import { Logo } from '../popup/Logo'
import { Section, SelectField, TextArea, TextField, YesNoField } from './fields'

type SaveState = 'idle' | 'saving' | 'saved'

function uid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return 'id-' + Math.random().toString(36).slice(2)
}

const MAX_DOC_BYTES = 6 * 1024 * 1024 // stored as data URLs in chrome.storage.local

const STATUS_OPTIONS: { value: ApplicationStatus; label: string }[] = [
  { value: 'filled', label: 'Filled' },
  { value: 'applied', label: 'Applied' },
  { value: 'interviewing', label: 'Interviewing' },
  { value: 'offer', label: 'Offer' },
  { value: 'rejected', label: 'Rejected' },
]

export function Options() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [settings, setSettings] = useState<Settings>(defaultSettings())
  const [apps, setApps] = useState<TrackedApplication[]>([])
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [importError, setImportError] = useState<string | null>(null)
  const [preppedId, setPreppedId] = useState<string | null>(null)
  const saveTimer = useRef<number | undefined>(undefined)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    void (async () => {
      setProfile(await getProfile())
      setSettings(await getSettings())
      setApps(await getApplications())
    })()
    // The content script appends custom answers ("answer memory") while this
    // page may be open — fold external writes in so a later commit() doesn't
    // clobber them with a stale snapshot.
    const off = onProfileChange((stored) => {
      setProfile((prev) => {
        if (!prev) return stored
        const known = new Set(prev.customAnswers.map((c) => c.id))
        const added = stored.customAnswers.filter((c) => !known.has(c.id))
        return added.length ? { ...prev, customAnswers: [...prev.customAnswers, ...added] } : prev
      })
    })
    return off
  }, [])

  function commit(next: Profile) {
    setProfile(next)
    setSaveState('saving')
    window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(async () => {
      await saveProfile(next)
      setSaveState('saved')
      window.setTimeout(() => setSaveState('idle'), 1500)
    }, 400)
  }

  function set<K extends keyof Profile>(key: K, value: Profile[K]) {
    if (!profile) return
    commit({ ...profile, [key]: value })
  }

  async function updateSettings(patch: Partial<Settings>) {
    const next = { ...settings, ...patch }
    setSettings(next)
    await saveSettings(next)
  }

  // --- collections -------------------------------------------------------
  function addExperience() {
    if (!profile) return
    const item: WorkExperience = {
      id: uid(),
      company: '',
      title: '',
      location: '',
      startDate: '',
      endDate: '',
      description: '',
    }
    commit({ ...profile, experience: [...profile.experience, item] })
  }
  function updateExperience(id: string, patch: Partial<WorkExperience>) {
    if (!profile) return
    commit({
      ...profile,
      experience: profile.experience.map((e) => (e.id === id ? { ...e, ...patch } : e)),
    })
  }
  function removeExperience(id: string) {
    if (!profile) return
    commit({ ...profile, experience: profile.experience.filter((e) => e.id !== id) })
  }

  function addEducation() {
    if (!profile) return
    const item: Education = {
      id: uid(),
      school: '',
      degree: '',
      field: '',
      startDate: '',
      endDate: '',
      gpa: '',
    }
    commit({ ...profile, education: [...profile.education, item] })
  }
  function updateEducation(id: string, patch: Partial<Education>) {
    if (!profile) return
    commit({
      ...profile,
      education: profile.education.map((e) => (e.id === id ? { ...e, ...patch } : e)),
    })
  }
  function removeEducation(id: string) {
    if (!profile) return
    commit({ ...profile, education: profile.education.filter((e) => e.id !== id) })
  }

  // --- documents ---------------------------------------------------------
  async function setDocument(slot: 'resume' | 'coverLetterFile', file: File) {
    if (!profile) return
    if (file.size > MAX_DOC_BYTES) {
      setImportError(`"${file.name}" is ${(file.size / 1024 / 1024).toFixed(1)} MB — max is 6 MB.`)
      return
    }
    setImportError(null)
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(new Error('read failed'))
      reader.readAsDataURL(file)
    })
    const stored: StoredFile = { name: file.name, type: file.type, size: file.size, dataUrl }
    commit({ ...profile, [slot]: stored })
  }

  function clearDocument(slot: 'resume' | 'coverLetterFile') {
    if (!profile) return
    commit({ ...profile, [slot]: null })
  }

  // --- application tracker -----------------------------------------------
  async function updateApp(id: string, patch: Partial<TrackedApplication>) {
    const next = apps.map((a) => (a.id === id ? { ...a, ...patch } : a))
    setApps(next)
    await saveApplications(next)
  }
  async function removeApp(id: string) {
    const next = apps.filter((a) => a.id !== id)
    setApps(next)
    await saveApplications(next)
  }

  /** Copy a ready-to-paste interview-prep prompt (career-ops methodology). */
  async function prepApp(app: TrackedApplication) {
    if (!profile) return
    try {
      await navigator.clipboard.writeText(buildInterviewPrepPrompt(profile, app))
      setPreppedId(app.id)
      window.setTimeout(() => setPreppedId((cur) => (cur === app.id ? null : cur)), 2500)
    } catch {
      setImportError('Could not copy to clipboard — click the page once and retry.')
    }
  }

  function addCustom() {
    if (!profile) return
    const item: CustomAnswer = { id: uid(), keywords: '', answer: '' }
    commit({ ...profile, customAnswers: [...profile.customAnswers, item] })
  }
  function updateCustom(id: string, patch: Partial<CustomAnswer>) {
    if (!profile) return
    commit({
      ...profile,
      customAnswers: profile.customAnswers.map((c) => (c.id === id ? { ...c, ...patch } : c)),
    })
  }
  function removeCustom(id: string) {
    if (!profile) return
    commit({ ...profile, customAnswers: profile.customAnswers.filter((c) => c.id !== id) })
  }

  // --- import / export ---------------------------------------------------
  function exportJson() {
    if (!profile) return
    const blob = new Blob([JSON.stringify(profile, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'browser-profile.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  function sanitizeStoredFile(v: unknown): StoredFile | null {
    if (!v || typeof v !== 'object') return null
    const f = v as Partial<StoredFile>
    if (typeof f.name !== 'string' || typeof f.dataUrl !== 'string' || !f.dataUrl.startsWith('data:')) {
      return null
    }
    const size =
      typeof f.size === 'number' && Number.isFinite(f.size)
        ? f.size
        : Math.floor((f.dataUrl.length * 3) / 4)
    if (size > MAX_DOC_BYTES) return null
    return { name: f.name.slice(0, 200), type: typeof f.type === 'string' ? f.type : '', size, dataUrl: f.dataUrl }
  }

  async function importJson(file: File) {
    setImportError(null)
    try {
      const parsed = JSON.parse(await file.text())
      if (typeof parsed !== 'object' || parsed == null) throw new Error('Not a profile object')
      const next: Profile = { ...emptyProfile(), ...parsed }
      // Enforce the same limits/shape on imported documents as the upload path.
      next.resume = sanitizeStoredFile(next.resume)
      next.coverLetterFile = sanitizeStoredFile(next.coverLetterFile)
      // Ensure collections are arrays with ids.
      next.experience = (Array.isArray(next.experience) ? next.experience : []).map((e) => ({
        ...e,
        id: e.id || uid(),
      }))
      next.education = (Array.isArray(next.education) ? next.education : []).map((e) => ({
        ...e,
        id: e.id || uid(),
      }))
      next.customAnswers = (Array.isArray(next.customAnswers) ? next.customAnswers : []).map((c) => ({
        ...c,
        id: c.id || uid(),
      }))
      commit(next)
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Could not read file')
    }
  }

  if (!profile) {
    return <div className="loading">Loading…</div>
  }

  return (
    <div className="page">
      <header className="topbar">
        <div className="topbar__brand">
          <Logo size={32} />
          <div>
            <h1>Gongzuo</h1>
            <p>Your details, filled into job applications in one click.</p>
          </div>
        </div>
        <div className="topbar__actions">
          <span className={'savechip savechip--' + saveState}>
            {saveState === 'saving' ? 'Saving…' : saveState === 'saved' ? '✓ Saved' : 'Autosaved'}
          </span>
          <button className="btn" onClick={() => fileRef.current?.click()}>
            Import
          </button>
          <button className="btn" onClick={exportJson}>
            Export
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="application/json"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) void importJson(f)
              e.target.value = ''
            }}
          />
        </div>
      </header>

      {importError && <div className="banner banner--error">Import failed: {importError}</div>}

      <main className="content">
        <Section title="Personal" description="How your name appears on applications.">
          <TextField label="First name" value={profile.firstName} onChange={(v) => set('firstName', v)} />
          <TextField label="Middle name" value={profile.middleName} onChange={(v) => set('middleName', v)} />
          <TextField label="Last name" value={profile.lastName} onChange={(v) => set('lastName', v)} />
          <TextField
            label="Preferred name"
            value={profile.preferredName}
            onChange={(v) => set('preferredName', v)}
            placeholder="Goes by…"
          />
        </Section>

        <Section title="Contact">
          <TextField label="Email" type="email" value={profile.email} onChange={(v) => set('email', v)} />
          <TextField label="Phone" type="tel" value={profile.phone} onChange={(v) => set('phone', v)} />
        </Section>

        <Section title="Address">
          <TextField
            label="Address line 1"
            wide
            value={profile.addressLine1}
            onChange={(v) => set('addressLine1', v)}
          />
          <TextField
            label="Address line 2"
            wide
            value={profile.addressLine2}
            onChange={(v) => set('addressLine2', v)}
            placeholder="Apt, suite, unit (optional)"
          />
          <TextField label="City" value={profile.city} onChange={(v) => set('city', v)} />
          <TextField label="State / Province" value={profile.state} onChange={(v) => set('state', v)} />
          <TextField label="ZIP / Postal code" value={profile.zip} onChange={(v) => set('zip', v)} />
          <TextField label="Country" value={profile.country} onChange={(v) => set('country', v)} />
        </Section>

        <Section title="Online presence">
          <TextField
            label="LinkedIn"
            wide
            value={profile.linkedin}
            onChange={(v) => set('linkedin', v)}
            placeholder="https://linkedin.com/in/…"
          />
          <TextField
            label="GitHub"
            value={profile.github}
            onChange={(v) => set('github', v)}
            placeholder="https://github.com/…"
          />
          <TextField
            label="Website / Portfolio"
            value={profile.website}
            onChange={(v) => set('website', v)}
          />
          <TextField label="Twitter / X" value={profile.twitter} onChange={(v) => set('twitter', v)} />
        </Section>

        <Section title="Professional">
          <TextField
            label="Current company"
            value={profile.currentCompany}
            onChange={(v) => set('currentCompany', v)}
          />
          <TextField
            label="Current title"
            value={profile.currentTitle}
            onChange={(v) => set('currentTitle', v)}
          />
          <TextField
            label="Years of experience"
            value={profile.yearsExperience}
            onChange={(v) => set('yearsExperience', v)}
          />
          <TextField
            label="Desired salary"
            value={profile.desiredSalary}
            onChange={(v) => set('desiredSalary', v)}
            placeholder="e.g. $150,000"
          />
          <TextField
            label="Notice period"
            value={profile.noticePeriod}
            onChange={(v) => set('noticePeriod', v)}
            placeholder="e.g. 2 weeks"
          />
          <TextField
            label="Earliest start date"
            value={profile.earliestStartDate}
            onChange={(v) => set('earliestStartDate', v)}
          />
        </Section>

        <Section
          title="Application preferences"
          description="Common eligibility questions. Leave a dropdown blank to skip it."
        >
          <YesNoField
            label="Authorized to work?"
            value={profile.workAuthorized}
            onChange={(v) => set('workAuthorized', v)}
          />
          <YesNoField
            label="Require visa sponsorship?"
            value={profile.requireSponsorship}
            onChange={(v) => set('requireSponsorship', v)}
          />
          <YesNoField
            label="Willing to relocate?"
            value={profile.willingToRelocate}
            onChange={(v) => set('willingToRelocate', v)}
          />
          <SelectField
            label="Remote preference"
            value={profile.remotePreference}
            onChange={(v) => set('remotePreference', v)}
            options={[
              { value: '', label: '—' },
              { value: 'Remote', label: 'Remote' },
              { value: 'Hybrid', label: 'Hybrid' },
              { value: 'On-site', label: 'On-site' },
              { value: 'Flexible', label: 'Flexible' },
            ]}
          />
          <TextField
            label="How did you hear about us?"
            wide
            value={profile.howHeard}
            onChange={(v) => set('howHeard', v)}
            placeholder="e.g. LinkedIn | Job board | Company website"
            hint="Separate alternatives with “|” — dropdowns try each until one matches."
          />
        </Section>

        <Section
          title="Voluntary self-identification"
          description="Optional EEO/diversity questions. Filled only when a form asks and you provide a value. Equivalent wordings are matched automatically — “Male” also selects “Man”, and any decline-to-answer phrasing matches them all."
        >
          <TextField label="Gender" value={profile.gender} onChange={(v) => set('gender', v)} />
          <TextField label="Pronouns" value={profile.pronouns} onChange={(v) => set('pronouns', v)} />
          <TextField
            label="Race / Ethnicity"
            value={profile.raceEthnicity}
            onChange={(v) => set('raceEthnicity', v)}
          />
          <YesNoField
            label="Hispanic / Latino?"
            value={profile.hispanicLatino}
            onChange={(v) => set('hispanicLatino', v)}
          />
          <TextField
            label="Veteran status"
            value={profile.veteranStatus}
            onChange={(v) => set('veteranStatus', v)}
          />
          <TextField
            label="Disability status"
            value={profile.disabilityStatus}
            onChange={(v) => set('disabilityStatus', v)}
          />
        </Section>

        <Section
          title="Documents"
          description="Stored locally and auto-attached to matching upload fields on applications."
        >
          <DocumentSlot
            label="Resume / CV"
            stored={profile.resume}
            onUpload={(f) => void setDocument('resume', f)}
            onClear={() => clearDocument('resume')}
          />
          <DocumentSlot
            label="Cover letter (file)"
            stored={profile.coverLetterFile}
            onUpload={(f) => void setDocument('coverLetterFile', f)}
            onClear={() => clearDocument('coverLetterFile')}
          />
        </Section>

        <Section title="Long-form answers">
          <TextArea
            label="Professional summary"
            value={profile.summary}
            onChange={(v) => set('summary', v)}
            placeholder="Used for 'tell us about yourself' / 'additional information' fields."
          />
          <TextArea
            label="Cover letter / motivation"
            value={profile.coverLetter}
            onChange={(v) => set('coverLetter', v)}
            placeholder="Used for 'why do you want to work here' style prompts."
          />
        </Section>

        <section className="section">
          <div className="section__head section__head--row">
            <div>
              <h2 className="section__title">Work experience</h2>
              <p className="section__desc">Optional. Helps with multi-step application forms.</p>
            </div>
            <button className="btn btn--sm" onClick={addExperience}>
              + Add
            </button>
          </div>
          {profile.experience.map((e) => (
            <div className="repeat" key={e.id}>
              <div className="grid">
                <TextField label="Company" value={e.company} onChange={(v) => updateExperience(e.id, { company: v })} />
                <TextField label="Title" value={e.title} onChange={(v) => updateExperience(e.id, { title: v })} />
                <TextField label="Location" value={e.location} onChange={(v) => updateExperience(e.id, { location: v })} />
                <TextField label="Start" value={e.startDate} onChange={(v) => updateExperience(e.id, { startDate: v })} placeholder="2021-03" />
                <TextField label="End" value={e.endDate} onChange={(v) => updateExperience(e.id, { endDate: v })} placeholder="Present" />
                <TextArea label="Description" value={e.description} onChange={(v) => updateExperience(e.id, { description: v })} />
              </div>
              <button className="link link--danger" onClick={() => removeExperience(e.id)}>
                Remove
              </button>
            </div>
          ))}
          {profile.experience.length === 0 && <p className="empty">No experience added.</p>}
        </section>

        <section className="section">
          <div className="section__head section__head--row">
            <div>
              <h2 className="section__title">Education</h2>
            </div>
            <button className="btn btn--sm" onClick={addEducation}>
              + Add
            </button>
          </div>
          {profile.education.map((e) => (
            <div className="repeat" key={e.id}>
              <div className="grid">
                <TextField label="School" value={e.school} onChange={(v) => updateEducation(e.id, { school: v })} />
                <TextField label="Degree" value={e.degree} onChange={(v) => updateEducation(e.id, { degree: v })} />
                <TextField label="Field of study" value={e.field} onChange={(v) => updateEducation(e.id, { field: v })} />
                <TextField label="GPA" value={e.gpa} onChange={(v) => updateEducation(e.id, { gpa: v })} />
                <TextField label="Start" value={e.startDate} onChange={(v) => updateEducation(e.id, { startDate: v })} />
                <TextField label="End" value={e.endDate} onChange={(v) => updateEducation(e.id, { endDate: v })} />
              </div>
              <button className="link link--danger" onClick={() => removeEducation(e.id)}>
                Remove
              </button>
            </div>
          ))}
          {profile.education.length === 0 && <p className="empty">No education added.</p>}
        </section>

        <section className="section">
          <div className="section__head section__head--row">
            <div>
              <h2 className="section__title">Custom answers</h2>
              <p className="section__desc">
                Match any question by keywords and provide a canned answer. These take priority over
                the built-in matching. In any answer (or profile value), list alternatives with
                “|” — e.g. “LinkedIn | Job board | Social media” — and dropdowns/radios will try
                each until one matches the form's options.
              </p>
            </div>
            <button className="btn btn--sm" onClick={addCustom}>
              + Add
            </button>
          </div>
          {profile.customAnswers.map((c) => (
            <div className="repeat" key={c.id}>
              <div className="grid">
                <TextField
                  label="Match keywords (comma-separated)"
                  wide
                  value={c.keywords}
                  onChange={(v) => updateCustom(c.id, { keywords: v })}
                  placeholder="e.g. why, interested, this role"
                />
                <TextArea
                  label="Answer"
                  value={c.answer}
                  onChange={(v) => updateCustom(c.id, { answer: v })}
                />
              </div>
              <button className="link link--danger" onClick={() => removeCustom(c.id)}>
                Remove
              </button>
            </div>
          ))}
          {profile.customAnswers.length === 0 && <p className="empty">No custom answers yet.</p>}
        </section>

        <Section title="Settings">
          <Toggle
            label="In-page autofill button"
            description="Show the floating Gongzuo button on pages with fillable forms."
            checked={settings.showOverlay}
            onChange={(v) => updateSettings({ showOverlay: v })}
          />
          <Toggle
            label="Highlight filled fields"
            description="Briefly outline each field after filling."
            checked={settings.highlightFilled}
            onChange={(v) => updateSettings({ highlightFilled: v })}
          />
          <Toggle
            label="Overwrite existing values"
            description="Replace values that are already in the form. Off = only fill blanks."
            checked={settings.overwriteExisting}
            onChange={(v) => updateSettings({ overwriteExisting: v })}
          />
          <Toggle
            label="Continuously fill multi-page forms"
            description="After you fill once, keep filling as Workday-style forms reveal new steps."
            checked={settings.continuousFill}
            onChange={(v) => updateSettings({ continuousFill: v })}
          />
          <Toggle
            label="Attach documents"
            description="Auto-attach your stored resume/cover letter to upload fields."
            checked={settings.attachFiles}
            onChange={(v) => updateSettings({ attachFiles: v })}
          />
          <Toggle
            label="Track applications"
            description="Log every filled application to the local tracker below."
            checked={settings.trackApplications}
            onChange={(v) => updateSettings({ trackApplications: v })}
          />
          <Toggle
            label="Show field-count badge"
            description="Display the number of fillable fields on the toolbar icon."
            checked={settings.showBadge}
            onChange={(v) => updateSettings({ showBadge: v })}
          />
        </Section>

        <Section
          title="Sensitive fields"
          description="Choose which optional questions Gongzuo is allowed to fill. Off = always left blank for you to answer by hand."
        >
          <Toggle
            label="Voluntary EEO / demographics"
            description="Gender, pronouns, race/ethnicity, veteran status."
            checked={settings.fillEEO}
            onChange={(v) => updateSettings({ fillEEO: v })}
          />
          <Toggle
            label="Disability status"
            checked={settings.fillDisability}
            onChange={(v) => updateSettings({ fillDisability: v })}
          />
          <Toggle
            label="Salary expectations"
            checked={settings.fillSalary}
            onChange={(v) => updateSettings({ fillSalary: v })}
          />
        </Section>

        <section className="section">
          <div className="section__head">
            <h2 className="section__title">Applications</h2>
            <p className="section__desc">
              Filled applications are logged here automatically — locally, like everything else.
              <strong> Prep</strong> copies a company-specific interview-prep prompt (your profile +
              this application, career-ops methodology) to paste into Claude or any assistant.
            </p>
          </div>
          {apps.length === 0 && <p className="empty">Nothing tracked yet. Fill an application!</p>}
          {apps.map((a) => (
            <div className="approw" key={a.id}>
              <div className="approw__main">
                <a className="approw__title" href={a.url} target="_blank" rel="noreferrer">
                  {a.title || a.host || a.url}
                </a>
                <span className="approw__meta">
                  {a.host} · {new Date(a.date).toLocaleDateString()} · {a.filledCount} fields
                </span>
              </div>
              <select
                className="field__input approw__status"
                value={a.status}
                onChange={(e) => void updateApp(a.id, { status: e.target.value as ApplicationStatus })}
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              <button
                className={'btn btn--sm' + (a.status === 'interviewing' ? ' btn--primary' : '')}
                title="Copy an interview-prep prompt for this application"
                onClick={() => void prepApp(a)}
              >
                {preppedId === a.id ? 'Copied ✓' : 'Prep'}
              </button>
              <button className="link link--danger" onClick={() => void removeApp(a.id)}>
                Remove
              </button>
            </div>
          ))}
        </section>

        <section className="section section--danger">
          <div className="section__head">
            <h2 className="section__title">Data</h2>
            <p className="section__desc">Everything is stored locally in your browser only.</p>
          </div>
          <div className="row">
            <button className="btn" onClick={() => commit(sampleProfile())}>
              Load sample data
            </button>
            <button
              className="btn btn--danger"
              onClick={() => {
                if (confirm('Clear all profile data? This cannot be undone.')) commit(emptyProfile())
              }}
            >
              Clear all data
            </button>
          </div>
        </section>
      </main>

      <footer className="pagefoot">
        Gongzuo stores your data locally with <code>chrome.storage.local</code>. Nothing leaves your
        device.
      </footer>
    </div>
  )
}

function DocumentSlot({
  label,
  stored,
  onUpload,
  onClear,
}: {
  label: string
  stored: StoredFile | null
  onUpload: (file: File) => void
  onClear: () => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <div className="field">
      <span className="field__label">{label}</span>
      {stored ? (
        <div className="docslot">
          <span className="docslot__name" title={stored.name}>
            📄 {stored.name}
          </span>
          <span className="docslot__size">{(stored.size / 1024).toFixed(0)} KB</span>
          <button className="link link--danger" onClick={onClear}>
            Remove
          </button>
        </div>
      ) : (
        <button className="btn btn--sm" onClick={() => inputRef.current?.click()}>
          Upload file…
        </button>
      )}
      <input
        ref={inputRef}
        type="file"
        hidden
        accept=".pdf,.doc,.docx,.txt,.rtf"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onUpload(f)
          e.target.value = ''
        }}
      />
    </div>
  )
}

function Toggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string
  description?: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  // A real (visually hidden) checkbox makes the whole label row clickable and
  // keyboard/screen-reader accessible; the styled switch just mirrors state.
  return (
    <label className="toggle field--wide">
      <span className="toggle__text">
        <span className="toggle__label">{label}</span>
        {description && <span className="toggle__desc">{description}</span>}
      </span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }}
      />
      <span className={'switch' + (checked ? ' switch--on' : '')} aria-hidden="true">
        <span className="switch__dot" />
      </span>
    </label>
  )
}
