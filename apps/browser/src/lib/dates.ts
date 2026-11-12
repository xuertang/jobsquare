/**
 * Free-form date parsing for profile values like "Mar 2021", "03/2021",
 * "2021-03-15", "March 2021", "2021". Native <input type=date|month> reject
 * anything but ISO strings, so unparseable values are skipped rather than
 * filled with garbage.
 */
export interface ParsedDate {
  year: number
  month?: number // 1-12
  day?: number // 1-31
}

const MONTHS: Record<string, number> = {
  jan: 1, january: 1,
  feb: 2, february: 2,
  mar: 3, march: 3,
  apr: 4, april: 4,
  may: 5,
  jun: 6, june: 6,
  jul: 7, july: 7,
  aug: 8, august: 8,
  sep: 9, sept: 9, september: 9,
  oct: 10, october: 10,
  nov: 11, november: 11,
  dec: 12, december: 12,
}

function validYear(y: number): boolean {
  return y >= 1900 && y <= 2100
}
function validMonth(m: number): boolean {
  return m >= 1 && m <= 12
}
function validDay(d: number): boolean {
  return d >= 1 && d <= 31
}

export function parseFreeDate(input: string): ParsedDate | null {
  const raw = input.trim().toLowerCase()
  if (!raw || raw === 'present' || raw === 'current' || raw === 'now' || raw === 'asap') {
    return null
  }

  // ISO: 2021-03-15 or 2021-03 or 2021/03/15
  let m = raw.match(/^(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?$/)
  if (m) {
    const year = Number(m[1])
    const month = Number(m[2])
    const day = m[3] ? Number(m[3]) : undefined
    if (validYear(year) && validMonth(month) && (day === undefined || validDay(day))) {
      return { year, month, day }
    }
    return null
  }

  // US: 03/15/2021 or 3/2021
  m = raw.match(/^(\d{1,2})[-/](?:(\d{1,2})[-/])?(\d{4})$/)
  if (m) {
    const first = Number(m[1])
    const second = m[2] ? Number(m[2]) : undefined
    const year = Number(m[3])
    if (!validYear(year)) return null
    if (second !== undefined) {
      // mm/dd/yyyy
      if (validMonth(first) && validDay(second)) return { year, month: first, day: second }
      return null
    }
    if (validMonth(first)) return { year, month: first }
    return null
  }

  // Month-name forms: "mar 2021", "march 15, 2021", "15 march 2021"
  m = raw.match(/^([a-z]+)\.?\s+(?:(\d{1,2})(?:st|nd|rd|th)?,?\s+)?(\d{4})$/)
  if (m) {
    const month = MONTHS[m[1]]
    const day = m[2] ? Number(m[2]) : undefined
    const year = Number(m[3])
    if (month && validYear(year) && (day === undefined || validDay(day))) {
      return { year, month, day }
    }
    return null
  }
  m = raw.match(/^(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\.?\s+(\d{4})$/)
  if (m) {
    const day = Number(m[1])
    const month = MONTHS[m[2]]
    const year = Number(m[3])
    if (month && validYear(year) && validDay(day)) return { year, month, day }
    return null
  }

  // Bare year
  m = raw.match(/^(\d{4})$/)
  if (m) {
    const year = Number(m[1])
    if (validYear(year)) return { year }
    return null
  }

  return null
}

const pad = (n: number) => String(n).padStart(2, '0')

/** Format for a native input. Returns null when the value can't satisfy the input type. */
export function formatForInput(input: string, type: 'date' | 'month'): string | null {
  const d = parseFreeDate(input)
  if (!d) return null
  const month = d.month ?? 1
  if (type === 'month') return `${d.year}-${pad(month)}`
  return `${d.year}-${pad(month)}-${pad(d.day ?? 1)}`
}
