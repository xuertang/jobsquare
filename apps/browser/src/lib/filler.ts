import { formatForInput } from './dates'
import { chooseOptionMulti, getContext, precedingSiblingText, type MatchedField } from './fieldMatcher'
import type { StoredFile } from './profile'

const HIGHLIGHT_STYLE_ID = 'browser-highlight-style'
const HIGHLIGHT_CLASS = 'browser-filled'

/**
 * Set an input/textarea value the way React expects. React tracks the value via
 * a private property and ignores plain `el.value = x`; calling the prototype's
 * native setter and dispatching bubbling input/change events makes controlled
 * components (Greenhouse, Lever, Workday, Ashby, …) register the change.
 */
export function setNativeValue(
  el: HTMLInputElement | HTMLTextAreaElement,
  value: string,
  opts: { keepFocus?: boolean } = {},
): void {
  // Resolve the prototype in the element's OWN realm — elements from
  // same-origin iframes are instances of that frame's constructors.
  const win = (el.ownerDocument.defaultView ?? window) as typeof window
  const proto =
    el.localName === 'textarea' ? win.HTMLTextAreaElement.prototype : win.HTMLInputElement.prototype
  const descriptor = Object.getOwnPropertyDescriptor(proto, 'value')
  el.focus()
  if (descriptor?.set) {
    descriptor.set.call(el, value)
  } else {
    el.value = value
  }
  el.dispatchEvent(new Event('input', { bubbles: true }))
  el.dispatchEvent(new Event('change', { bubbles: true }))
  el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }))
  if (!opts.keepFocus) el.blur()
}

function fillValue(el: HTMLInputElement | HTMLTextAreaElement, match: MatchedField): boolean {
  let value = match.candidates[0] ?? match.value
  if (el.localName === 'input') {
    const type = (el as HTMLInputElement).type.toLowerCase()
    if (type === 'date' || type === 'month') {
      // First parseable candidate wins ("ASAP | 2026-08" → 2026-08).
      const formatted = match.candidates
        .map((c) => formatForInput(c, type))
        .find((f): f is string => f !== null)
      if (!formatted) return false // unparseable → skip rather than fill garbage
      value = formatted
    }
  }
  setNativeValue(el, value)
  return true
}

function fillSelect(el: HTMLSelectElement, match: MatchedField): boolean {
  const options = Array.from(el.options).map((o) => ({
    value: o.value,
    label: o.textContent ?? '',
  }))
  const idx = chooseOptionMulti(options, match.candidates, match.kind)
  if (idx < 0) return false
  if (el.selectedIndex === idx) return true
  el.selectedIndex = idx
  el.dispatchEvent(new Event('input', { bubbles: true }))
  el.dispatchEvent(new Event('change', { bubbles: true }))
  return true
}

export function radioLabel(radio: HTMLInputElement): string {
  const labels = radio.labels ? Array.from(radio.labels) : []
  const fromLabel = labels.map((l) => l.textContent ?? '').join(' ').trim()
  if (fromLabel) return fromLabel
  const aria = radio.getAttribute('aria-label')
  if (aria) return aria
  const wrap = radio.closest('label')
  if (wrap) return wrap.textContent ?? ''
  return radio.value
}

function fillRadioGroup(radios: HTMLInputElement[], match: MatchedField): boolean {
  const options = radios.map((r) => ({ value: r.value, label: radioLabel(r) }))
  const idx = chooseOptionMulti(options, match.candidates, match.kind)
  if (idx < 0) return false
  const radio = radios[idx]
  if (radio.checked) return true
  radio.checked = true
  radio.dispatchEvent(new Event('input', { bubbles: true }))
  radio.dispatchEvent(new Event('change', { bubbles: true }))
  radio.click?.()
  return true
}

function fillCheckbox(el: HTMLInputElement, match: MatchedField): boolean {
  if (match.kind !== 'yesno') return false
  const want = (match.candidates[0] ?? match.value).trim().toLowerCase() === 'yes'
  if (el.checked === want) return true
  el.checked = want
  el.dispatchEvent(new Event('input', { bubbles: true }))
  el.dispatchEvent(new Event('change', { bubbles: true }))
  el.click?.()
  // click() may toggle again; force the intended state.
  if (el.checked !== want) {
    el.checked = want
    el.dispatchEvent(new Event('change', { bubbles: true }))
  }
  return true
}

/**
 * Fill a contenteditable rich-text editor (Quill, ProseMirror, Lexical, …).
 * execCommand('insertText') routes through the editor's beforeinput handling;
 * fall back to textContent + a synthetic InputEvent.
 */
function fillContentEditable(el: HTMLElement, value: string): boolean {
  const doc = el.ownerDocument
  const win = doc.defaultView ?? window
  el.focus()
  try {
    const selection = win.getSelection()
    selection?.selectAllChildren(el)
    const ok = doc.execCommand('insertText', false, value)
    if (ok && (el.textContent ?? '').includes(value.slice(0, 40))) {
      el.blur()
      return true
    }
  } catch {
    /* fall through to direct set */
  }
  el.textContent = value
  el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }))
  el.dispatchEvent(new Event('change', { bubbles: true }))
  el.blur()
  return true
}

// --- file attach ------------------------------------------------------------

export function dataUrlToFile(stored: StoredFile): File | null {
  try {
    const comma = stored.dataUrl.indexOf(',')
    if (comma < 0) return null
    const meta = stored.dataUrl.slice(0, comma)
    const b64 = stored.dataUrl.slice(comma + 1)
    const binary = atob(b64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
    const type = stored.type || /data:([^;]+)/.exec(meta)?.[1] || 'application/octet-stream'
    return new File([bytes], stored.name, { type })
  } catch {
    return null
  }
}

/** Does the input's `accept` attribute allow this file? (empty accept = anything) */
export function inputAcceptsFile(el: HTMLInputElement, file: { name: string; type: string }): boolean {
  const accept = (el.accept ?? '').trim()
  if (!accept) return true
  const name = file.name.toLowerCase()
  const type = file.type.toLowerCase()
  return accept
    .split(',')
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean)
    .some((token) => {
      if (token.startsWith('.')) return name.endsWith(token)
      if (token.endsWith('/*')) return type.startsWith(token.slice(0, -1))
      return type === token
    })
}

/**
 * Programmatically attach a locally-stored file to an <input type=file>.
 * Building the File ourselves and assigning a DataTransfer's FileList is
 * allowed by browsers — the pick-a-file dialog is only mandatory when reading
 * files we did NOT construct.
 */
export function attachFile(el: HTMLInputElement, stored: StoredFile): boolean {
  const file = dataUrlToFile(stored)
  if (!file) return false
  if (!inputAcceptsFile(el, file)) return false
  try {
    const dt = new DataTransfer()
    dt.items.add(file)
    el.files = dt.files
    el.dispatchEvent(new Event('input', { bubbles: true }))
    el.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  } catch {
    return false
  }
}

export type Fillable =
  | { type: 'value'; el: HTMLInputElement | HTMLTextAreaElement }
  | { type: 'select'; el: HTMLSelectElement }
  | { type: 'checkbox'; el: HTMLInputElement }
  | { type: 'radio'; els: HTMLInputElement[] }
  | { type: 'file'; el: HTMLInputElement }
  | { type: 'contenteditable'; el: HTMLElement }
  | { type: 'widget'; el: HTMLElement }

/** Is this field already populated by the user? */
export function hasExistingValue(field: Fillable): boolean {
  switch (field.type) {
    case 'value':
      return field.el.value.trim().length > 0
    case 'select': {
      const el = field.el
      // Index 0 is usually a "Select…" placeholder.
      return el.selectedIndex > 0 && el.value.trim().length > 0
    }
    case 'checkbox':
      return false // a checkbox always has a defined state; treat as overwritable
    case 'radio':
      return field.els.some((r) => r.checked)
    case 'file':
      return (field.el.files?.length ?? 0) > 0
    case 'contenteditable':
      return (field.el.textContent ?? '').trim().length > 0
    case 'widget':
      return false // widgetHasValue() is checked by the caller (needs widgetFiller)
  }
}

/**
 * Apply a match to a native field. Widget fields are handled by
 * widgetFiller.fillWidget (async); calling this with one returns false.
 */
export function applyMatch(field: Fillable, match: MatchedField): boolean {
  try {
    switch (field.type) {
      case 'value':
        return fillValue(field.el, match)
      case 'select':
        return fillSelect(field.el, match)
      case 'checkbox':
        return fillCheckbox(field.el, match)
      case 'radio':
        return fillRadioGroup(field.els, match)
      case 'contenteditable':
        return fillContentEditable(field.el, match.candidates[0] ?? match.value)
      case 'file':
      case 'widget':
        return false
    }
  } catch {
    return false
  }
}

export function representative(field: Fillable): HTMLElement {
  return field.type === 'radio' ? field.els[0] : field.el
}

/**
 * The question shared by a group of radios/checkboxes. Each option usually
 * sits inside its own wrapping <label> ("Yes"), which counts as a label and
 * suppresses getContext's preceding-text walk — so the question ("Are you
 * authorized to work?") must be read off the group's common container instead:
 * its aria-label, or the nearest short text preceding it (Lever's
 * .application-label pattern). precedingSiblingText refuses to cross siblings
 * containing other controls, so it can't leak the previous field's question.
 */
function groupQuestion(els: HTMLElement[]): string | undefined {
  const first = els[0]
  if (!first) return undefined
  let container: HTMLElement | null = first.parentElement
  while (container && els.some((e) => !container!.contains(e))) {
    container = container.parentElement
  }
  if (!container) return undefined
  const aria = container.getAttribute('aria-label')
  if (aria) return aria
  return precedingSiblingText(container) || undefined
}

export function contextFor(field: Fillable) {
  if (field.type === 'radio') {
    // Use the group's question (fieldset legend / aria-label / preceding
    // label text), not a single option's label.
    return getContext(field.els[0], groupQuestion(field.els))
  }
  return getContext(field.el)
}

function ensureHighlightStyle(): void {
  if (document.getElementById(HIGHLIGHT_STYLE_ID)) return
  const style = document.createElement('style')
  style.id = HIGHLIGHT_STYLE_ID
  style.textContent = `
    .${HIGHLIGHT_CLASS} {
      outline: 2px solid #6366f1 !important;
      outline-offset: 1px !important;
      border-radius: 4px !important;
      transition: outline-color 1s ease-out !important;
      animation: gongzuo-pulse 0.6s ease-out;
    }
    @keyframes gongzuo-pulse {
      0% { box-shadow: 0 0 0 0 rgba(99,102,241,0.5); }
      100% { box-shadow: 0 0 0 8px rgba(99,102,241,0); }
    }
  `
  document.documentElement.appendChild(style)
}

export function highlight(field: Fillable): void {
  ensureHighlightStyle()
  const el = representative(field)
  el.classList.add(HIGHLIGHT_CLASS)
}

export function clearHighlights(): void {
  for (const el of Array.from(document.querySelectorAll('.' + HIGHLIGHT_CLASS))) {
    el.classList.remove(HIGHLIGHT_CLASS)
  }
}
