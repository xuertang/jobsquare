import { normalize } from './fieldMatcher'
import { emptyProfile, type Profile } from './profile'

const PROFILE_KEY = 'browser:profile'
const SETTINGS_KEY = 'browser:settings'
const APPLICATIONS_KEY = 'browser:applications'

export interface Settings {
  /** Overwrite fields that already have a value. */
  overwriteExisting: boolean
  /** Briefly highlight fields after filling. */
  highlightFilled: boolean
  /** Show a badge with the number of detected fields per tab. */
  showBadge: boolean
  /** Show the in-page floating Gongzuo button on application forms. */
  showOverlay: boolean
  /** Keep auto-filling as multi-step (Workday-style) forms reveal new pages. */
  continuousFill: boolean
  /** Fill voluntary EEO/demographic questions (gender, race, veteran…). */
  fillEEO: boolean
  /** Fill disability-status questions. */
  fillDisability: boolean
  /** Fill salary/compensation questions. */
  fillSalary: boolean
  /** Attach the stored resume/cover letter to file inputs. */
  attachFiles: boolean
  /** Log filled applications to the local tracker. */
  trackApplications: boolean
}

export function defaultSettings(): Settings {
  return {
    overwriteExisting: false,
    highlightFilled: true,
    showBadge: true,
    showOverlay: true,
    continuousFill: false,
    fillEEO: true,
    fillDisability: true,
    fillSalary: true,
    attachFiles: true,
    trackApplications: true,
  }
}

/** Merge a stored (possibly partial / older-schema) profile onto the current shape. */
function normalizeProfile(stored: unknown): Profile {
  const base = emptyProfile()
  if (stored && typeof stored === 'object') {
    return { ...base, ...(stored as Partial<Profile>) }
  }
  return base
}

export async function getProfile(): Promise<Profile> {
  const data = await chrome.storage.local.get(PROFILE_KEY)
  return normalizeProfile(data[PROFILE_KEY])
}

export async function saveProfile(profile: Profile): Promise<void> {
  await chrome.storage.local.set({ [PROFILE_KEY]: profile })
}

export async function getSettings(): Promise<Settings> {
  const data = await chrome.storage.local.get(SETTINGS_KEY)
  return { ...defaultSettings(), ...(data[SETTINGS_KEY] ?? {}) }
}

export async function saveSettings(settings: Settings): Promise<void> {
  await chrome.storage.local.set({ [SETTINGS_KEY]: settings })
}

/**
 * Answer memory: save an answer keyed on the (normalized) question so any
 * future application asking a similar question is filled automatically.
 * Saving again for the same question updates the stored answer in place.
 */
export async function addCustomAnswer(question: string, answer: string): Promise<void> {
  const keywords = normalize(question)
  const trimmed = answer.trim()
  if (!keywords || !trimmed) return
  const profile = await getProfile()
  const existing = profile.customAnswers.find((c) => c.keywords === keywords)
  if (existing) {
    existing.answer = trimmed
  } else {
    profile.customAnswers.push({
      id: `mem-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      keywords,
      answer: trimmed,
    })
  }
  await saveProfile(profile)
}

// --- application tracker ----------------------------------------------------

export type ApplicationStatus = 'filled' | 'applied' | 'interviewing' | 'offer' | 'rejected'

export interface TrackedApplication {
  id: string
  url: string
  host: string
  /** Page title at fill time — usually "<Job title> - <Company>". */
  title: string
  filledCount: number
  /** ISO datetime of the (latest) fill. */
  date: string
  status: ApplicationStatus
}

export async function getApplications(): Promise<TrackedApplication[]> {
  const data = await chrome.storage.local.get(APPLICATIONS_KEY)
  const list = data[APPLICATIONS_KEY]
  return Array.isArray(list) ? (list as TrackedApplication[]) : []
}

export async function saveApplications(apps: TrackedApplication[]): Promise<void> {
  await chrome.storage.local.set({ [APPLICATIONS_KEY]: apps })
}

/**
 * Record a fill event. Re-fills of the same URL on the same day update the
 * existing entry instead of creating duplicates.
 */
export async function recordApplication(entry: {
  url: string
  title: string
  filledCount: number
}): Promise<void> {
  const apps = await getApplications()
  const now = new Date()
  const today = now.toISOString().slice(0, 10)
  let host = ''
  try {
    host = new URL(entry.url).hostname
  } catch {
    /* keep empty */
  }

  const existing = apps.find((a) => a.url === entry.url && a.date.slice(0, 10) === today)
  if (existing) {
    existing.filledCount = Math.max(existing.filledCount, entry.filledCount)
    existing.date = now.toISOString()
    existing.title = entry.title || existing.title
  } else {
    apps.unshift({
      id: `${now.getTime()}-${Math.random().toString(36).slice(2, 8)}`,
      url: entry.url,
      host,
      title: entry.title.slice(0, 160),
      filledCount: entry.filledCount,
      date: now.toISOString(),
      status: 'filled',
    })
  }
  // Keep the tracker bounded.
  await saveApplications(apps.slice(0, 500))
}

/**
 * Seed default SETTINGS on first install. The profile is deliberately NOT
 * seeded: pre-filling a fake sample profile would let a first-run user
 * one-click fabricated PII and work-authorization answers into a real job
 * application. "Load sample data" in Options is the explicit demo path.
 */
export async function seedIfEmpty(): Promise<void> {
  const data = await chrome.storage.local.get(SETTINGS_KEY)
  if (data[SETTINGS_KEY] == null) {
    await chrome.storage.local.set({ [SETTINGS_KEY]: defaultSettings() })
  }
}

export function onProfileChange(cb: (profile: Profile) => void): () => void {
  const listener = (
    changes: Record<string, chrome.storage.StorageChange>,
    area: string,
  ) => {
    if (area === 'local' && changes[PROFILE_KEY]) {
      cb(normalizeProfile(changes[PROFILE_KEY].newValue))
    }
  }
  chrome.storage.onChanged.addListener(listener)
  return () => chrome.storage.onChanged.removeListener(listener)
}
