/**
 * Field-identification harness: runs the extension's REAL collection + matching
 * pipeline (collectFields copy from content.ts + contextFor + matchContext)
 * against the live page and reports what each control resolved to.
 * Injected via the browser pane; results via window.__gzScan().
 */
import { collectFields } from '../src/lib/collect'
import {
  createEntryIndexer,
  matchContext,
  matchFileContext,
} from '../src/lib/fieldMatcher'
import { contextFor, type Fillable } from '../src/lib/filler'
import { WIDGET_CONTROL_SELECTOR } from '../src/lib/widgetFiller'
import { emptyProfile, type Profile } from '../src/lib/profile'

/** Every profile value populated so no spec is skipped for lack of data. */
function fullProfile(): Profile {
  return {
    ...emptyProfile(),
    firstName: 'Alex',
    middleName: 'J',
    lastName: 'Rivera',
    preferredName: 'Al',
    email: 'alex@example.com',
    phone: '+1 415 555 0199',
    addressLine1: '500 Terry Francois Blvd',
    addressLine2: 'Suite 7',
    city: 'San Francisco',
    state: 'California',
    zip: '94158',
    country: 'United States',
    linkedin: 'https://linkedin.com/in/alex',
    github: 'https://github.com/alex',
    website: 'https://alex.dev',
    twitter: '@alex',
    currentCompany: 'Acme Corp',
    currentTitle: 'Senior Engineer',
    yearsExperience: '7',
    desiredSalary: '$180,000',
    noticePeriod: '2 weeks',
    earliestStartDate: '2026-08',
    workAuthorized: 'yes',
    requireSponsorship: 'no',
    willingToRelocate: 'yes',
    remotePreference: 'Remote',
    gender: 'Male',
    pronouns: 'He/Him',
    raceEthnicity: 'Asian',
    veteranStatus: 'I am not a veteran',
    disabilityStatus: 'No',
    hispanicLatino: 'no',
    coverLetter: 'I am excited about this role.',
    summary: 'Seasoned engineer.',
    howHeard: 'LinkedIn',
    experience: [
      { id: 'e1', company: 'Acme Corp', title: 'Senior Engineer', location: 'SF', startDate: 'Mar 2021', endDate: 'Present', description: 'Led the platform team.' },
      { id: 'e2', company: 'Globex', title: 'Engineer', location: 'Seattle', startDate: '2018', endDate: '2021', description: 'Built billing.' },
    ],
    education: [
      { id: 'ed1', school: 'UC Berkeley', degree: 'BSc', field: 'Computer Science', startDate: '2013', endDate: '2017', gpa: '3.8' },
    ],
  }
}

interface ScanRow {
  control: string
  label: string
  key: string
  value: string
  signal: string
}

function scan(): { url: string; total: number; matched: number; rows: ScanRow[] } {
  const profile = fullProfile()
  const indexer = createEntryIndexer()
  const fields = collectFields(document)
  const rows: ScanRow[] = []

  for (const field of fields) {
    const ctx = contextFor(field)
    const control =
      field.type === 'value'
        ? (field.el as HTMLInputElement).type || field.el.localName
        : field.type
    if (field.type === 'file') {
      const slot = matchFileContext(ctx)
      rows.push({
        control: 'file',
        label: ctx.displayLabel,
        key: slot ?? 'UNMATCHED',
        value: '',
        signal: ctx.signal.slice(0, 90),
      })
      continue
    }
    const match = matchContext(ctx, profile, [], { entryIndex: indexer.next })
    rows.push({
      control,
      label: ctx.displayLabel,
      key: match?.key ?? 'UNMATCHED',
      value: match?.value?.slice(0, 30) ?? '',
      signal: ctx.signal.slice(0, 90),
    })
  }

  return {
    url: location.href,
    total: rows.length,
    matched: rows.filter((r) => r.key !== 'UNMATCHED').length,
    rows,
  }
}

;(window as unknown as { __gzScan?: typeof scan }).__gzScan = scan
