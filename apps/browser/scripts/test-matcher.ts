import {
  chooseOption,
  chooseOptionMulti,
  createEntryIndexer,
  matchContext,
  matchFileContext,
  normalize,
  parseCandidates,
  type FieldContext,
  type SpecCategory,
} from '../src/lib/fieldMatcher'
import { normalizeOptions } from '../src/lib/collect'
import { formatForInput, parseFreeDate } from '../src/lib/dates'
import { emptyProfile, type Profile } from '../src/lib/profile'

function ctx(label: string, autocomplete = '', section = ''): FieldContext {
  return {
    signal: normalize(label),
    autocomplete,
    displayLabel: label,
    sectionSignal: normalize(section),
  }
}

const profile: Profile = {
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
  state: 'CA',
  zip: '94158',
  country: 'United States',
  linkedin: 'https://linkedin.com/in/alex',
  github: 'https://github.com/alex',
  website: 'https://alex.dev',
  twitter: '@alex',
  currentCompany: 'Acme Corp',
  currentTitle: 'Senior Engineer',
  yearsExperience: '7',
  desiredSalary: '$180k',
  earliestStartDate: '2026-08',
  remotePreference: 'Remote',
  workAuthorized: 'yes',
  requireSponsorship: 'no',
  willingToRelocate: 'yes',
  gender: 'Male',
  pronouns: 'He/Him',
  raceEthnicity: 'Asian',
  veteranStatus: 'I am not a veteran',
  disabilityStatus: 'No',
  howHeard: 'LinkedIn',
  coverLetter: 'I am excited...',
  summary: 'Seasoned engineer...',
  experience: [
    {
      id: 'e1',
      company: 'Acme Corp',
      title: 'Senior Engineer',
      location: 'SF',
      startDate: 'Mar 2021',
      endDate: 'Present',
      description: 'Led the platform team.',
    },
    {
      id: 'e2',
      company: 'Globex',
      title: 'Engineer',
      location: 'Seattle',
      startDate: '2018',
      endDate: '2021',
      description: 'Built the billing system.',
    },
  ],
  education: [
    {
      id: 'ed1',
      school: 'UC Berkeley',
      degree: 'BSc',
      field: 'Computer Science',
      startDate: '2013',
      endDate: '2017',
      gpa: '3.8',
    },
    {
      id: 'ed2',
      school: 'Stanford University',
      degree: 'MSc',
      field: 'Machine Learning',
      startDate: '2017',
      endDate: '2019',
      gpa: '3.9',
    },
  ],
}

let pass = 0
let fail = 0

function expectKey(
  label: string,
  expected: string | null,
  opts: { autocomplete?: string; section?: string; disabled?: SpecCategory[] } = {},
) {
  const m = matchContext(ctx(label, opts.autocomplete ?? '', opts.section ?? ''), profile, profile.customAnswers, {
    disabledCategories: new Set(opts.disabled ?? []),
  })
  const got = m?.key ?? null
  if (got === expected) {
    pass++
  } else {
    fail++
    console.log(`✗ "${label}" (section="${opts.section ?? ''}") → expected ${expected}, got ${got} (value=${m?.value ?? '∅'})`)
  }
}

// Core identity / contact
expectKey('First Name', 'firstName')
expectKey('Last Name', 'lastName')
expectKey('Full Name', 'fullName')
expectKey('Legal Name', 'fullName')
expectKey('Email Address', 'email') // must NOT be addressLine1
expectKey('E-mail', 'email')
expectKey('Phone Number', 'phone')
expectKey('Mobile', 'phone')

// Address block
expectKey('Street Address', 'addressLine1')
expectKey('Address Line 1', 'addressLine1')
expectKey('Address Line 2', 'addressLine2')
expectKey('Apartment / Suite', 'addressLine2')
expectKey('City', 'city')
expectKey('State', 'state')
expectKey('Province / Region', 'state')
expectKey('Zip Code', 'zip')
expectKey('Postal Code', 'zip')
expectKey('Country', 'country')

// Links
expectKey('LinkedIn Profile URL', 'linkedin')
expectKey('GitHub', 'github')
expectKey('Personal Website', 'website')
expectKey('Portfolio', 'website')

// Professional
expectKey('Current Company', 'currentCompany')
expectKey('Current Job Title', 'currentTitle')
expectKey('Years of Experience', 'yearsExperience')
expectKey('Desired Salary', 'desiredSalary')
expectKey('Salary Expectations', 'desiredSalary')

// Eligibility
expectKey('Are you legally authorized to work in the United States?', 'workAuthorized')
expectKey('Will you now or in the future require sponsorship for employment visa status?', 'requireSponsorship')
expectKey('Are you willing to relocate?', 'willingToRelocate')

// EEO
expectKey('Gender', 'gender')
expectKey('Race / Ethnicity', 'raceEthnicity')
expectKey('Veteran Status', 'veteranStatus')
expectKey('Pronouns', 'pronouns') // plural label must match the singular keyword

// Live-form regressions (Affirm/Lever/Ashby scans, 2026-07)
expectKey('Where are you currently located?', 'city') // Ashby location typeahead
expectKey('Current location', 'city') // Lever
expectKey('How did you first learn about Affirm as an employer?', 'howHeard') // NOT currentCompany
expectKey('Name Pronunciation', null) // NOT fullName
// Lever renders these as grouped radios/checkboxes; once the group question is
// in the signal, greedy date/company keywords must not hijack it.
expectKey(
  'Do you now or in the future require visa sponsorship for employment at Spotify? Yes No',
  'requireSponsorship', // NOT expEndDate ('to' + 'employment')
)
expectKey(
  'Do you require company-sponsored work visa sponsorship? Yes No',
  'requireSponsorship', // NOT currentCompany ('company')
)

// Long form
expectKey('Why do you want to work here?', 'coverLetter')
expectKey('Tell us about yourself', 'summary')
expectKey('How did you hear about us?', 'howHeard')

// Autocomplete-driven
expectKey('xyz', 'firstName', { autocomplete: 'given-name' })
expectKey('xyz', 'email', { autocomplete: 'email' })
expectKey('xyz', 'country', { autocomplete: 'tel-country-code' })

// Phone country-code selector next to a phone input
expectKey('Country Dial Code', 'country')

// Negative: unrelated field should not match
expectKey('Favorite color', null)

// Regression: bare "first"/"last" must be exact-only
expectKey('first', 'firstName')
expectKey('last', 'lastName')
expectKey('Last Employer', 'currentCompany') // NOT lastName
expectKey('First choice of location', null) // NOT firstName

// Regression: search boxes must not match title/company specs
expectKey('Search job title or keywords', null)
expectKey('Search companies', null)

// --- new: education / experience ------------------------------------------
expectKey('School Name', 'school')
expectKey('University', 'school')
expectKey('Degree', 'degree')
expectKey('Major', 'fieldOfStudy')
expectKey('Field of Study', 'fieldOfStudy')
expectKey('GPA', 'gpa')
expectKey('Describe your responsibilities', 'responsibilities')

// Section-aware date disambiguation
expectKey('Start Date', 'eduStartDate', { section: 'Education' })
expectKey('End Date', 'eduEndDate', { section: 'Education history' })
expectKey('Start Date', 'expStartDate', { section: 'Work Experience' })
expectKey('End Date', 'expEndDate', { section: 'Employment history' })
expectKey('Start Date', 'earliestStartDate') // no section → availability
expectKey('When can you start?', 'earliestStartDate')

// remotePreference (was a dead profile field before)
expectKey('Workplace Type', 'remotePreference')
expectKey('Are you looking for remote or hybrid?', 'remotePreference')

// --- new: sensitive-category gating ----------------------------------------
expectKey('Gender', null, { disabled: ['eeo'] })
expectKey('Veteran Status', null, { disabled: ['eeo'] })
expectKey('Disability Status', 'disabilityStatus')
expectKey('Disability Status', null, { disabled: ['disability'] })
expectKey('Desired Salary', null, { disabled: ['salary'] })
expectKey('First Name', 'firstName', { disabled: ['eeo', 'disability', 'salary'] })

// --- dropdown option extraction (answer editor) -----------------------------
function expectOptions(name: string, raw: string[], expected: string[]) {
  const got = normalizeOptions(raw)
  if (JSON.stringify(got) === JSON.stringify(expected)) pass++
  else {
    fail++
    console.log(`✗ options "${name}": expected ${JSON.stringify(expected)}, got ${JSON.stringify(got)}`)
  }
}
// Placeholder prompts are not answers.
expectOptions('drops placeholders', ['Select…', 'Yes', 'No'], ['Yes', 'No'])
expectOptions('drops dashes/empties', ['--', '', '   ', 'Remote', '—'], ['Remote'])
expectOptions('drops "Please select"', ['Please select one', 'Male', 'Female'], ['Male', 'Female'])
expectOptions('drops typeahead prompts', ['Start typing...', 'Search', 'Canada'], ['Canada'])
// Real multi-word EEO wording survives intact — it's what gets stored.
expectOptions(
  'keeps federal phrasings',
  ['Please select', 'I am not a protected veteran', "I don't wish to answer"],
  ['I am not a protected veteran', "I don't wish to answer"],
)
expectOptions('collapses whitespace', ['  Bay   Area\n(Remote) '], ['Bay Area (Remote)'])
expectOptions('dedupes case-insensitively', ['Yes', 'yes', 'YES', 'No'], ['Yes', 'No'])
expectOptions('drops over-long entries', ['Yes', 'x'.repeat(130)], ['Yes'])
{
  // Cap at 60 so a country list can't bloat the cross-frame payload.
  const many = Array.from({ length: 200 }, (_, i) => `Country ${i}`)
  const got = normalizeOptions(many)
  if (got.length === 60 && got[0] === 'Country 0') pass++
  else {
    fail++
    console.log(`✗ options cap: got ${got.length}`)
  }
}
// An option whose text merely STARTS with a real word must survive; only
// prompt-leading words are dropped.
expectOptions('keeps "Selected by..." style text', ['Selective Service', 'Yes'], ['Selective Service', 'Yes'])

// --- file slots -------------------------------------------------------------
function expectFile(label: string, expected: string | null) {
  const got = matchFileContext(ctx(label))
  if (got === expected) pass++
  else {
    fail++
    console.log(`✗ file "${label}" → expected ${expected}, got ${got}`)
  }
}
expectFile('Resume/CV', 'resume')
expectFile('Upload your resume', 'resume')
expectFile('Attach CV', 'resume')
expectFile('Cover Letter', 'coverLetterFile')
expectFile('Profile photo', null)
// Regression: "Attach <other document>" must not receive the resume
expectFile('Attach transcript', null)
expectFile('Attach your file', 'resume') // generic attach with no other noun

// --- dates ------------------------------------------------------------------
function expectDate(input: string, type: 'date' | 'month', expected: string | null) {
  const got = formatForInput(input, type)
  if (got === expected) pass++
  else {
    fail++
    console.log(`✗ date "${input}" (${type}) → expected ${expected}, got ${got}`)
  }
}
expectDate('Mar 2021', 'month', '2021-03')
expectDate('March 2021', 'date', '2021-03-01')
expectDate('2021-03-15', 'date', '2021-03-15')
expectDate('03/2021', 'month', '2021-03')
expectDate('03/15/2021', 'date', '2021-03-15')
expectDate('2021', 'month', '2021-01')
expectDate('Present', 'date', null)
expectDate('ASAP', 'date', null)
expectDate('garbage', 'date', null)
expectDate('September 3, 2024', 'date', '2024-09-03')

if (parseFreeDate('15 march 2021')?.day === 15) pass++
else {
  fail++
  console.log('✗ parseFreeDate("15 march 2021") day mismatch')
}

// --- chooseOption -----------------------------------------------------------
function expectOption(name: string, options: string[], target: string, kind: 'text' | 'yesno', expectedIdx: number) {
  const opts = options.map((o) => ({ value: o, label: o }))
  const idx = chooseOption(opts, target, kind)
  if (idx === expectedIdx) pass++
  else {
    fail++
    console.log(`✗ option "${name}": expected idx ${expectedIdx}, got ${idx}`)
  }
}

expectOption('yesno-yes', ['Select…', 'Yes', 'No'], 'yes', 'yesno', 1)
expectOption('yesno-no', ['Select…', 'Yes', 'No'], 'no', 'yesno', 2)
// Regression: "I do not…" must be selectable for want=no despite the "i do" prefix
expectOption(
  'sponsorship-no',
  ['Select…', 'I do require sponsorship', 'I do not require sponsorship'],
  'no',
  'yesno',
  2,
)
expectOption(
  'sponsorship-yes',
  ['Select…', 'I do require sponsorship', 'I do not require sponsorship'],
  'yes',
  'yesno',
  1,
)
// yesno with an unrecognized value must NOT default to the "no" branch —
// "US Citizen" on a Yes/No control matches nothing (safe no-fill)…
expectOption('yesno-unknown-value', ['Select…', 'Yes', 'No'], 'US Citizen', 'yesno', -1)
// …but still lands on a matching labeled option via text fallback.
expectOption('yesno-text-fallback', ['US Citizen', 'Green Card', 'No'], 'US Citizen', 'yesno', 0)
// And "Yes | US Citizen" answers plain Yes/No via the first candidate.
{
  const opts = ['Select…', 'Yes', 'No'].map((o) => ({ value: o, label: o }))
  const idx = chooseOptionMulti(opts, ['Yes', 'US Citizen'], 'yesno')
  if (idx === 1) pass++
  else {
    fail++
    console.log(`✗ yesno multi Yes|US Citizen: expected 1, got ${idx}`)
  }
}
expectOption('country', ['Select…', 'Canada', 'United States', 'Mexico'], 'United States', 'text', 2)
// Phone-country pickers list "Name +code" — prefix matching must resolve them
expectOption('dial-code', ['United Kingdom +44', 'United States +1', 'Mexico +52'], 'United States', 'text', 1)
expectOption('state-abbr', ['--', 'California', 'Colorado'], 'California', 'text', 1)
expectOption('remote', ['Select…', 'On-site', 'Hybrid', 'Remote'], 'Remote', 'text', 3)

// --- multi-candidate values (“a | b” alternatives) --------------------------
function expectCandidates(name: string, raw: string, expected: string[]) {
  const got = parseCandidates(raw)
  if (JSON.stringify(got) === JSON.stringify(expected)) pass++
  else {
    fail++
    console.log(`✗ candidates "${name}": expected ${JSON.stringify(expected)}, got ${JSON.stringify(got)}`)
  }
}

expectCandidates('two alternatives', 'BSc | Bachelor of Science', ['BSc', 'Bachelor of Science'])
expectCandidates('three, unspaced', 'LinkedIn|Job board|Social media', ['LinkedIn', 'Job board', 'Social media'])
expectCandidates('single value untouched', 'LinkedIn', ['LinkedIn'])
expectCandidates('empty segments dropped', 'a || b', ['a', 'b'])
// Prose containing "|" must NOT be split (long segments)
const prose =
  'In my current role I own the data platform | a system spanning ingestion, storage, and query layers across three teams and two regions.'
expectCandidates('long prose stays intact', prose, [prose])

// chooseOptionMulti: first candidate misses, second matches
{
  const opts = ['Select…', 'Job Board', 'Social Media'].map((o) => ({ value: o, label: o }))
  const idx = chooseOptionMulti(opts, ['LinkedIn', 'Job Board'], 'text')
  if (idx === 1) pass++
  else {
    fail++
    console.log(`✗ chooseOptionMulti fallback: expected 1, got ${idx}`)
  }
  const none = chooseOptionMulti(opts, ['LinkedIn', 'Referral'], 'text')
  if (none === -1) pass++
  else {
    fail++
    console.log(`✗ chooseOptionMulti no-match: expected -1, got ${none}`)
  }
}

// matchContext carries parsed candidates through
{
  const multiProfile: Profile = { ...profile, howHeard: 'LinkedIn | Job board' }
  const m = matchContext(ctx('How did you hear about us?'), multiProfile, [])
  if (m && m.candidates.length === 2 && m.candidates[1] === 'Job board' && m.value === 'LinkedIn | Job board') {
    pass++
  } else {
    fail++
    console.log(`✗ matchContext candidates: got ${JSON.stringify(m?.candidates)} value=${m?.value}`)
  }
}

// --- built-in synonym expansion ---------------------------------------------
const asOpts = (options: string[]) => options.map((o) => ({ value: o, label: o }))

function expectPick(name: string, label: string, p: Profile, options: string[], expectedIdx: number) {
  const m = matchContext(ctx(label), p, [])
  const idx = m ? chooseOptionMulti(asOpts(options), m.candidates, m.kind) : -99
  if (idx === expectedIdx) pass++
  else {
    fail++
    console.log(
      `✗ pick "${name}": expected ${expectedIdx}, got ${idx} (candidates=${JSON.stringify(m?.candidates)})`,
    )
  }
}

// Stored "Male" fills a dropdown that says "Man"; stored value stays first so
// text inputs are untouched.
{
  const m = matchContext(ctx('Gender'), profile, [])
  const cands = m?.candidates ?? []
  if (m && cands[0] === 'Male' && cands.map(normalize).includes('man')) pass++
  else {
    fail++
    console.log(`✗ gender expansion: got ${JSON.stringify(cands)}`)
  }
}
expectPick('gender Man', 'Gender', profile, ['Select…', 'Man', 'Woman', 'Non-binary'], 1)
// Word-boundary + tiering guard: "Male" must NOT land on "Female" — the exact
// synonym "Man" wins even though "Female" comes first in the list.
expectPick('gender not Female', 'Gender', profile, ['Female', 'Man'], 1)
expectOption('gender-no-substring', ['Female', 'Woman'], 'Male', 'text', -1)

// Decline wording crosses ATS vocabularies (Workday ↔ Lever ↔ Greenhouse)
expectPick(
  'decline crosses ATSes',
  'Gender',
  { ...profile, gender: 'Prefer not to say' },
  ['Select…', 'Male', 'Female', "I don't wish to answer"],
  3,
)

// Veteran: stored free-text maps onto Workday's exact federal phrasing
expectPick(
  'veteran phrasing',
  'Veteran Status',
  profile, // stored: 'I am not a veteran'
  [
    'Select One',
    'I identify as one or more of the classifications of a protected veteran',
    'I am not a protected veteran',
    "I don't wish to answer",
  ],
  2,
)

// Disability: bare "No" hits the full CC-305 phrasing exactly
expectPick(
  'disability CC-305',
  'Disability Status',
  profile, // stored: 'No'
  [
    'Please select',
    'Yes, I have a disability, or have had one in the past',
    'No, I do not have a disability and have not had one in the past',
    'I do not want to answer',
  ],
  2,
)

// Race: "African American" ↔ "Black"
expectPick(
  'race synonym',
  'Race / Ethnicity',
  { ...profile, raceEthnicity: 'African American' },
  ['Select…', 'Asian', 'Black', 'White'],
  2,
)

// Workplace: "On-site" ↔ "In office" (no substring relation)
expectPick(
  'onsite in-office',
  'Workplace Type',
  { ...profile, remotePreference: 'On-site' },
  ['Remote', 'Hybrid', 'In office'],
  2,
)

// Custom answers are NOT synonym-expanded — the user's text is authoritative
{
  const custom = [{ id: 'c1', keywords: 'gender', answer: 'Male' }]
  const m = matchContext(ctx('Gender'), profile, custom)
  if (m?.key === 'custom:c1' && m.candidates.length === 1 && m.candidates[0] === 'Male') pass++
  else {
    fail++
    console.log(`✗ custom not expanded: got ${m?.key} ${JSON.stringify(m?.candidates)}`)
  }
}

// --- repeating sections (indexed matching) -----------------------------------
{
  const indexer = createEntryIndexer()
  const opts = { entryIndex: indexer.next }
  const check = (label: string, section: string, expectKeyName: string, expectValue: string) => {
    const m = matchContext(ctx(label, '', section), profile, [], opts)
    if (m?.key === expectKeyName && m.value === expectValue) pass++
    else {
      fail++
      console.log(`✗ indexed "${label}": expected ${expectKeyName}=${expectValue}, got ${m?.key}=${m?.value}`)
    }
  }
  // Row 1 (Greenhouse-style Education section)
  check('School', 'Education', 'school', 'UC Berkeley')
  check('Degree', 'Education', 'degree', 'BSc')
  // Row 2 — the SECOND School/Degree fields read education[1]
  check('School', 'Education', 'school', 'Stanford University')
  check('Degree', 'Education', 'degree', 'MSc')
  // Work Experience rows: section-gated company/title
  check('Company', 'Work Experience', 'expCompany', 'Acme Corp')
  check('Title', 'Work Experience', 'expTitle', 'Senior Engineer')
  check('Company', 'Work Experience', 'expCompany', 'Globex')
  check('Title', 'Work Experience', 'expTitle', 'Engineer')
  check('Location', 'Employment history', 'expLocation', 'SF')

  // Row 2 label is suffixed for the review UI
  const m2 = matchContext(ctx('Location', '', 'Employment history'), profile, [], opts)
  if (m2?.label === 'Job location #2') pass++
  else {
    fail++
    console.log(`✗ indexed label: expected "Job location #2", got "${m2?.label}"`)
  }

  // Row 3 exists on the form but not in the profile → unmatched, and NOT
  // hijacked by the generic currentCompany spec
  const m3 = matchContext(ctx('Company', '', 'Work Experience'), profile, [], opts)
  if (m3 === null) pass++
  else {
    fail++
    console.log(`✗ indexed exhausted: expected null, got ${m3.key}=${m3.value}`)
  }

  // rowCount reflects what the form showed
  if (indexer.rowCount('experience') === 3 && indexer.rowCount('education') === 2) pass++
  else {
    fail++
    console.log(`✗ rowCount: exp=${indexer.rowCount('experience')} edu=${indexer.rowCount('education')}`)
  }
}

// Outside a section, generic specs still win
expectKey('Current Company', 'currentCompany')
expectKey('City', 'city')

// --- interview-prep prompt (career-ops mode sync) ----------------------------
{
  const { buildInterviewPrepPrompt, guessCompanyRole } = await import('../src/lib/interviewPrep')
  const app = {
    id: 'a1',
    url: 'https://boards.greenhouse.io/acmecorp/jobs/123',
    host: 'boards.greenhouse.io',
    title: 'Job Application for Senior Software Engineer at Acme Corp',
    filledCount: 12,
    date: '2026-07-20T10:00:00.000Z',
    status: 'interviewing' as const,
  }
  const guess = guessCompanyRole(app)
  if (guess.company === 'Acme Corp' && guess.role === 'Senior Software Engineer') pass++
  else {
    fail++
    console.log(`✗ guessCompanyRole: got ${JSON.stringify(guess)}`)
  }

  // ATS-slug fallback when the title is unhelpful
  const guess2 = guessCompanyRole({ ...app, title: '' })
  if (guess2.company === 'Acmecorp') pass++
  else {
    fail++
    console.log(`✗ guessCompanyRole slug: got ${JSON.stringify(guess2)}`)
  }

  const prompt = buildInterviewPrepPrompt(profile, app)
  const mustContain = [
    'Senior Software Engineer at Acme Corp',
    'https://boards.greenhouse.io/acmecorp/jobs/123',
    'recruiter-screen',
    'peer-tech',
    'NEVER invent interview questions',
    'UC Berkeley', // profile context made it in
    'Acme Corp', // experience
    'Story mapping',
  ]
  const missing = mustContain.filter((s) => !prompt.includes(s))
  if (missing.length === 0) pass++
  else {
    fail++
    console.log(`✗ prep prompt missing: ${JSON.stringify(missing)}`)
  }
}

console.log(`\n${pass} passed, ${fail} failed`)
if (fail > 0) process.exit(1)
