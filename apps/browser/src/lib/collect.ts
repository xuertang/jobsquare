/**
 * Field collection — turning a document's raw controls into logical Fillable
 * fields (radio/checkbox groups collapse to one field, widgets claim their
 * inner inputs). Shared by the content script, the scan harness, and the
 * jobops OpenClaw plugin's fill bundle.
 */
import {
  controlVisible,
  controlVisibleStrict,
  deepQueryAll,
  isElementVisible,
  shadowContains,
  shadowParent,
} from './dom'
import { radioLabel, type Fillable } from './filler'
import { OPTION_SELECTOR, WIDGET_CONTROL_SELECTOR } from './widgetFiller'

export const FILLABLE_INPUT_TYPES = new Set([
  'text',
  'email',
  'tel',
  'url',
  'number',
  'search',
  'date',
  'month',
  '', // inputs with no explicit type default to text
])

/**
 * Hosts of the major ATS platforms. Frames NOT on this list and NOT same-site
 * with the top page are never scanned or filled — a page full of third-party
 * ad iframes must not receive profile PII.
 */
export const ATS_HOSTS = [
  'greenhouse.io',
  'lever.co',
  'myworkdayjobs.com',
  'workday.com',
  'ashbyhq.com',
  'icims.com',
  'smartrecruiters.com',
  'jobvite.com',
  'taleo.net',
  'avature.net',
  'bamboohr.com',
  'workable.com',
  'workablemail.com',
  'teamtailor.com',
  'recruitee.com',
  'breezy.hr',
  'jazz.co',
  'applytojob.com',
  'oraclecloud.com',
  'successfactors.com',
  'successfactors.eu',
  'adp.com',
  'paylocity.com',
  'paycomonline.net',
  'ultipro.com',
  'dayforcehcm.com',
  'greenhouse.dev',
  // long-tail ATS platforms commonly embedded on careers pages
  'phenompeople.com',
  'eightfold.ai',
  'personio.com',
  'personio.de',
  'join.com',
  'pinpointhq.com',
  'softgarden.io',
  'homerun.co',
  'jobylon.com',
  'rippling.com',
  'gusto.com',
  'zohorecruit.com',
  'freshteam.com',
  'clearcompany.com',
  'comeet.co',
  'fountain.com',
  'gupy.io',
  'catsone.com',
  'applicantstack.com',
  'trakstar.com',
  'hibob.com',
  'factorialhr.com',
  'csod.com',
  'brassring.com',
  'silkroad.com',
  'jobdiva.com',
  'paycor.com',
  'jobscore.com',
  'hirebridge.com',
]

export function hostMatches(host: string, allowed: string): boolean {
  return host === allowed || host.endsWith('.' + allowed)
}

/** Rough eTLD+1 — good enough to call careers.acme.com and jobs.acme.com same-site. */
export function siteOf(host: string): string {
  return host.split('.').slice(-2).join('.')
}

/** May a frame on `host` (under a top page on `topHost`) receive profile data? */
export function hostAllowed(host: string, topHost?: string): boolean {
  if (ATS_HOSTS.some((h) => hostMatches(host, h))) return true
  if (topHost && siteOf(topHost) === siteOf(host)) return true
  return false
}

export function isEditableControl(
  el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement,
): boolean {
  return !el.disabled && !(el as HTMLInputElement).readOnly
}

/** Search boxes are widgets we must never fill — selecting a "suggestion"
 * navigates away mid-application. */
export function isSearchControl(el: HTMLElement): boolean {
  if (el.closest('[role="search"]')) return true
  if (el.getAttribute('role') === 'searchbox') return true
  return el.localName === 'input' && (el as HTMLInputElement).type === 'search'
}

const MAX_OPTIONS = 60
/** Placeholder rows ("Select…", "-- choose --") are prompts, not answers. */
const PLACEHOLDER_OPTION = /^\s*(?:[-–—]+|select|choose|please\s|pick\s|none\b|\s)*(?:\.{3}|…)?\s*$/i
const PLACEHOLDER_PREFIX = /^\s*(?:select|choose|please|pick|start typing|search)\b/i

function cleanOption(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

function usableOption(text: string): boolean {
  if (!text || text.length > 120) return false
  return !PLACEHOLDER_OPTION.test(text) && !PLACEHOLDER_PREFIX.test(text)
}

/**
 * Collapse whitespace, drop placeholder prompts and over-long entries, dedupe
 * case-insensitively, and cap the list. Split out from fieldOptions so it is
 * testable without a DOM.
 */
export function normalizeOptions(raw: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const text of raw.map(cleanOption)) {
    if (!usableOption(text) || seen.has(text.toLowerCase())) continue
    seen.add(text.toLowerCase())
    out.push(text)
    if (out.length >= MAX_OPTIONS) break
  }
  return out
}

/**
 * The choices a person could actually pick for a choice-style field, in DOM
 * order — used by the review UI so saving an answer for a dropdown offers the
 * real options instead of a blank box.
 *
 * Strictly read-only: it never clicks, focuses, or types, so a custom widget
 * contributes options only when its menu already exists in the DOM (the
 * standard APG combobox keeps a display:none listbox). Widgets that build
 * their menu on open return [] rather than being poked into revealing it.
 */
export function fieldOptions(field: Fillable): string[] {
  let raw: string[] = []
  switch (field.type) {
    case 'select':
      raw = Array.from(field.el.options)
        .filter((o) => !o.disabled)
        .map((o) => o.textContent ?? o.value)
      break
    case 'radio':
      raw = field.els.map((r) => radioLabel(r))
      break
    case 'widget': {
      // Only this control's own subtree — a page-level option sweep would pull
      // in every other open menu's items.
      const own = deepQueryAll<HTMLElement>(field.el, OPTION_SELECTOR)
      const inShadow = field.el.shadowRoot
        ? deepQueryAll<HTMLElement>(field.el.shadowRoot, OPTION_SELECTOR)
        : []
      raw = [...own, ...inShadow].map((o) => o.textContent ?? '')
      break
    }
    default:
      return []
  }
  return normalizeOptions(raw)
}

/** Group raw form controls into logical fields (radio groups collapse to one). */
export function collectFields(root: ParentNode): Fillable[] {
  const fields: Fillable[] = []
  const radioGroups = new Map<string, HTMLInputElement[]>()
  const checkboxGroups = new Map<string, HTMLInputElement[]>()
  const unnamedRadioContainers = new Map<Element, number>()

  // Custom widget controls first, so native inputs nested inside them defer to
  // the widget handler. NOTE: elements may come from iframe realms — classify
  // by localName, never instanceof.
  const widgets = deepQueryAll<HTMLElement>(root, WIDGET_CONTROL_SELECTOR).filter(
    (el) =>
      el.localName !== 'select' &&
      isElementVisible(el) &&
      !isSearchControl(el) &&
      !el.closest('[data-browser-overlay]'),
  )
  // Dedup nested widget controls (e.g. [role=combobox] inside [aria-haspopup=listbox]);
  // the ancestor walk crosses shadow boundaries.
  const widgetSet = new Set(widgets)
  const topWidgets = widgets.filter((w) => {
    let p = shadowParent(w)
    while (p) {
      if (widgetSet.has(p as HTMLElement)) return false
      p = shadowParent(p)
    }
    return true
  })
  const insideWidget = (el: HTMLElement) => topWidgets.some((w) => shadowContains(w, el))

  const controls = deepQueryAll<HTMLElement>(
    root,
    'input, textarea, select, [contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"]',
  )

  for (const control of controls) {
    if (control.closest('[data-browser-overlay]')) continue
    const tag = control.localName

    if (tag === 'textarea') {
      const el = control as HTMLTextAreaElement
      if (!isEditableControl(el) || !controlVisibleStrict(el)) continue
      fields.push({ type: 'value', el })
      continue
    }

    if (tag === 'select') {
      const el = control as HTMLSelectElement
      // controlVisible, not isElementVisible: styled selects (phone country
      // pickers especially) are routinely opacity-0 under a decorated facade.
      if (!isEditableControl(el) || !controlVisible(el)) continue
      fields.push({ type: 'select', el })
      continue
    }

    if (tag === 'input') {
      const el = control as HTMLInputElement
      const type = (el.type || 'text').toLowerCase()
      if (!isEditableControl(el)) continue

      if (type === 'file') {
        // File inputs are routinely hidden behind styled buttons — do NOT
        // require visibility.
        fields.push({ type: 'file', el })
        continue
      }

      if (insideWidget(el)) continue // the widget handler owns it

      if (type === 'radio') {
        // Radios/checkboxes are conventionally opacity-0 under styled proxies.
        if (!controlVisible(el)) continue
        const formId = el.form?.getAttribute('name') ?? el.form?.getAttribute('id') ?? 'noform'
        let groupId = el.name
        if (!groupId) {
          // Name-less radios: group by nearest container, not one global bucket.
          const container = el.closest('fieldset, [role="radiogroup"]') ?? el.parentElement ?? el
          let n = unnamedRadioContainers.get(container)
          if (n === undefined) {
            n = unnamedRadioContainers.size
            unnamedRadioContainers.set(container, n)
          }
          groupId = `unnamed#${n}`
        }
        const key = `${formId}::${groupId}`
        const group = radioGroups.get(key)
        if (group) group.push(el)
        else radioGroups.set(key, [el])
        continue
      }

      if (type === 'checkbox') {
        if (!controlVisible(el)) continue
        // Checkboxes sharing a name are one QUESTION rendered as a choice
        // list (Lever renders pronouns, sponsorship, yes/no eligibility this
        // way). Collect them per name; groups of 2+ become option groups so
        // the question — not each option's own label — drives matching.
        // Lone checkboxes (consent boxes) keep their own context.
        if (el.name) {
          const formId = el.form?.getAttribute('name') ?? el.form?.getAttribute('id') ?? 'noform'
          const key = `${formId}::${el.name}`
          const group = checkboxGroups.get(key)
          if (group) group.push(el)
          else checkboxGroups.set(key, [el])
        } else {
          fields.push({ type: 'checkbox', el })
        }
        continue
      }

      if (FILLABLE_INPUT_TYPES.has(type)) {
        // Strict proxy visibility: hidden-self is OK only with a visible label
        // (styled date pickers) — honeypots have no visible label.
        if (!controlVisibleStrict(el) || isSearchControl(el)) continue
        fields.push({ type: 'value', el })
      }
      continue
    }

    // contenteditable rich-text editors
    if (control.isContentEditable && isElementVisible(control) && !insideWidget(control)) {
      fields.push({ type: 'contenteditable', el: control })
    }
  }

  for (const w of topWidgets) {
    fields.push({ type: 'widget', el: w })
  }

  for (const els of radioGroups.values()) {
    if (els.length) fields.push({ type: 'radio', els })
  }

  for (const els of checkboxGroups.values()) {
    // 2+ boxes under one name = single-question choice group; fill it like a
    // radio group (pick the option matching the profile value). A lone named
    // box stays an ordinary checkbox.
    if (els.length >= 2) fields.push({ type: 'radio', els })
    else fields.push({ type: 'checkbox', el: els[0] })
  }

  return fields
}
