/**
 * The user's job-application profile. Everything Gongzuo knows how to fill in.
 * Stored locally in chrome.storage.local — never sent anywhere.
 */
export interface WorkExperience {
  id: string
  company: string
  title: string
  location: string
  startDate: string // free-form, e.g. "2021-03" or "Mar 2021"
  endDate: string // free-form or "Present"
  description: string
}

export interface Education {
  id: string
  school: string
  degree: string
  field: string
  startDate: string
  endDate: string
  gpa: string
}

export interface CustomAnswer {
  id: string
  /** keywords (comma separated) that should match a question, e.g. "why,interested,company" */
  keywords: string
  answer: string
}

/** A file (resume / cover letter) stored locally as a data URL. */
export interface StoredFile {
  name: string
  type: string
  size: number
  dataUrl: string
}

export type YesNo = '' | 'yes' | 'no'

export interface Profile {
  // Personal
  firstName: string
  middleName: string
  lastName: string
  preferredName: string

  // Contact
  email: string
  phone: string

  // Address
  addressLine1: string
  addressLine2: string
  city: string
  state: string
  zip: string
  country: string

  // Online presence
  linkedin: string
  github: string
  website: string
  twitter: string

  // Current role / professional
  currentCompany: string
  currentTitle: string
  yearsExperience: string
  desiredSalary: string
  noticePeriod: string
  earliestStartDate: string

  // Application preferences
  workAuthorized: YesNo
  requireSponsorship: YesNo
  willingToRelocate: YesNo
  remotePreference: string

  // Voluntary / EEO (all optional)
  gender: string
  pronouns: string
  raceEthnicity: string
  veteranStatus: string
  disabilityStatus: string
  hispanicLatino: YesNo

  // Long-form
  coverLetter: string
  summary: string
  howHeard: string

  // Collections
  experience: WorkExperience[]
  education: Education[]
  customAnswers: CustomAnswer[]

  // Documents (stored locally as data URLs)
  resume: StoredFile | null
  coverLetterFile: StoredFile | null
}

export function emptyProfile(): Profile {
  return {
    firstName: '',
    middleName: '',
    lastName: '',
    preferredName: '',
    email: '',
    phone: '',
    addressLine1: '',
    addressLine2: '',
    city: '',
    state: '',
    zip: '',
    country: '',
    linkedin: '',
    github: '',
    website: '',
    twitter: '',
    currentCompany: '',
    currentTitle: '',
    yearsExperience: '',
    desiredSalary: '',
    noticePeriod: '',
    earliestStartDate: '',
    workAuthorized: '',
    requireSponsorship: '',
    willingToRelocate: '',
    remotePreference: '',
    gender: '',
    pronouns: '',
    raceEthnicity: '',
    veteranStatus: '',
    disabilityStatus: '',
    hispanicLatino: '',
    coverLetter: '',
    summary: '',
    howHeard: '',
    experience: [],
    education: [],
    customAnswers: [],
    resume: null,
    coverLetterFile: null,
  }
}

/** A small sample profile so first-time users can see the extension work immediately. */
export function sampleProfile(): Profile {
  return {
    ...emptyProfile(),
    firstName: 'Alex',
    lastName: 'Rivera',
    email: 'alex.rivera@example.com',
    phone: '+1 (415) 555-0199',
    addressLine1: '500 Terry A Francois Blvd',
    city: 'San Francisco',
    state: 'CA',
    zip: '94158',
    country: 'United States',
    linkedin: 'https://linkedin.com/in/alexrivera',
    github: 'https://github.com/alexrivera',
    website: 'https://alexrivera.dev',
    currentCompany: 'Acme Corp',
    currentTitle: 'Senior Software Engineer',
    yearsExperience: '7',
    workAuthorized: 'yes',
    requireSponsorship: 'no',
    willingToRelocate: 'yes',
    remotePreference: 'Remote',
    howHeard: 'LinkedIn',
  }
}

export function fullName(p: Profile): string {
  return [p.firstName, p.lastName].filter(Boolean).join(' ').trim()
}
