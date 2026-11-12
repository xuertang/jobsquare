import { useState } from 'react'
import { fullName, type Profile } from '../lib/profile'
import { openOptions } from './api'

/** One click-to-copy block. Children are display; `text` is what gets copied. */
function Copy({ text, className, children }: { text: string; className?: string; children: React.ReactNode }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      className={'copyblock' + (copied ? ' copyblock--copied' : '') + (className ? ' ' + className : '')}
      title="Click to copy"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setCopied(true)
          window.setTimeout(() => setCopied(false), 1200)
        } catch {
          /* clipboard denied — nothing sensible to do in a popup */
        }
      }}
    >
      {children}
      <span className="copyblock__badge">{copied ? '✓ Copied' : '⧉'}</span>
    </button>
  )
}

function Sect({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="ptab__sect">
      <div className="ptab__head">{title}</div>
      {children}
    </div>
  )
}

const dash = (a: string, b: string) => [a, b].filter(Boolean).join(' – ') || ''

export function ProfileTab({ profile, onRefresh }: { profile: Profile; onRefresh: () => void }) {
  const name = fullName(profile)
  const location = [profile.city, profile.state, profile.country].filter(Boolean).join(', ')

  const links = [
    ['LinkedIn', profile.linkedin],
    ['GitHub', profile.github],
    ['Website', profile.website],
    ['Twitter / X', profile.twitter],
  ].filter(([, v]) => v.trim())

  const details = [
    ['Current role', [profile.currentTitle, profile.currentCompany].filter(Boolean).join(' at ')],
    ['Years of experience', profile.yearsExperience],
    ['Salary expectation', profile.desiredSalary],
    ['Notice period', profile.noticePeriod],
    ['Earliest start', profile.earliestStartDate],
    ['Work location preference', profile.remotePreference],
  ].filter(([, v]) => v.trim())

  const empty =
    !name && !profile.email && !profile.phone && profile.experience.length === 0 && profile.education.length === 0

  if (empty) {
    return (
      <div className="card card--warn">
        <p>Your profile is empty.</p>
        <button className="btn btn--primary" onClick={openOptions}>
          Set up your profile
        </button>
      </div>
    )
  }

  return (
    <div className="ptab">
      <div className="ptab__hint">
        <strong>Click any block to copy it</strong> — reference your profile while answering
        questions Gongzuo can't fill.
      </div>

      <div className="ptab__toolbar">
        <button className="link" onClick={onRefresh}>
          ⟳ Refresh
        </button>
        <button className="link" onClick={openOptions}>
          ✎ Edit
        </button>
      </div>

      <div className="ptab__scroll">
        <Sect title="Contact">
          {name && <Copy text={name}>{name}</Copy>}
          {location && <Copy text={location}>{location}</Copy>}
          {profile.email && <Copy text={profile.email}>{profile.email}</Copy>}
          {profile.phone && <Copy text={profile.phone}>{profile.phone}</Copy>}
          {profile.addressLine1 && (
            <Copy text={[profile.addressLine1, profile.addressLine2].filter(Boolean).join(', ')}>
              {profile.addressLine1}
              {profile.addressLine2 ? `, ${profile.addressLine2}` : ''}
            </Copy>
          )}
          {profile.zip && <Copy text={profile.zip}>ZIP: {profile.zip}</Copy>}
        </Sect>

        {links.length > 0 && (
          <Sect title="Links">
            {links.map(([label, url]) => (
              <Copy key={label} text={url}>
                <span className="ptab__linklabel">{label}</span> {url}
              </Copy>
            ))}
          </Sect>
        )}

        {profile.education.length > 0 && (
          <Sect title="Education">
            {profile.education.map((e) => (
              <div className="ptab__entry" key={e.id}>
                {e.school && (
                  <Copy text={e.school} className="copyblock--title">
                    {e.school}
                  </Copy>
                )}
                {(e.degree || e.field) && (
                  <Copy text={[e.degree, e.field].filter(Boolean).join(', ')}>
                    {[e.degree, e.field].filter(Boolean).join(', ')}
                  </Copy>
                )}
                {(e.startDate || e.endDate) && (
                  <Copy text={dash(e.startDate, e.endDate)}>{dash(e.startDate, e.endDate)}</Copy>
                )}
                {e.gpa && <Copy text={e.gpa}>GPA: {e.gpa}</Copy>}
              </div>
            ))}
          </Sect>
        )}

        {profile.experience.length > 0 && (
          <Sect title="Experience">
            {profile.experience.map((e) => (
              <div className="ptab__entry" key={e.id}>
                {e.title && (
                  <Copy text={e.title} className="copyblock--title">
                    {e.title}
                  </Copy>
                )}
                {(e.company || e.location) && (
                  <Copy text={[e.company, e.location].filter(Boolean).join(' · ')}>
                    {[e.company, e.location].filter(Boolean).join(' · ')}
                  </Copy>
                )}
                {(e.startDate || e.endDate) && (
                  <Copy text={dash(e.startDate, e.endDate)}>{dash(e.startDate, e.endDate)}</Copy>
                )}
                {e.description.trim() && (
                  <Copy text={e.description.trim()} className="copyblock--multi">
                    {e.description.trim()}
                  </Copy>
                )}
              </div>
            ))}
          </Sect>
        )}

        {details.length > 0 && (
          <Sect title="Details">
            {details.map(([label, v]) => (
              <Copy key={label} text={v}>
                <span className="ptab__linklabel">{label}</span> {v}
              </Copy>
            ))}
          </Sect>
        )}

        {profile.summary.trim() && (
          <Sect title="Summary">
            <Copy text={profile.summary.trim()} className="copyblock--multi">
              {profile.summary.trim()}
            </Copy>
          </Sect>
        )}

        {profile.coverLetter.trim() && (
          <Sect title="Cover letter">
            <Copy text={profile.coverLetter.trim()} className="copyblock--multi">
              {profile.coverLetter.trim()}
            </Copy>
          </Sect>
        )}

        {profile.customAnswers.some((c) => c.answer.trim()) && (
          <Sect title="Saved answers">
            {profile.customAnswers
              .filter((c) => c.answer.trim())
              .slice(0, 20)
              .map((c) => (
                <Copy key={c.id} text={c.answer.trim()} className="copyblock--multi">
                  <span className="ptab__linklabel">{c.keywords || 'answer'}</span>
                  {c.answer.trim()}
                </Copy>
              ))}
          </Sect>
        )}
      </div>
    </div>
  )
}
