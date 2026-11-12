/**
 * Filling for custom (non-native) dropdowns: ARIA comboboxes, React-Select,
 * Workday data-automation-id widgets, and other div/button-based menus.
 *
 * Strategy: open the widget with a realistic pointer sequence, wait for
 * [role=option] nodes to render (they often portal to <body>), pick the best
 * option with the same chooseOption() used for native selects, click it, and
 * close with Escape if nothing matched.
 */
import { chooseOptionMulti, type MatchedField } from './fieldMatcher'
import { deepQueryAll, isElementVisible, sleep } from './dom'
import { setNativeValue } from './filler'

export const OPTION_SELECTOR = [
  '[role="option"]',
  '[data-automation-id="promptOption"]',
  '[data-automation-id*="menuItem"]',
  // intl-tel-input country rows (older versions have no ARIA roles)
  '.iti__country',
  'li.country',
].join(', ')

/** Selector for widget *controls* (the thing you click to open the menu). */
export const WIDGET_CONTROL_SELECTOR = [
  '[role="combobox"]',
  '[aria-haspopup="listbox"]',
  '[aria-haspopup="menu"][data-automation-id]',
  'button[data-automation-id*="select"]',
  'button[data-automation-id*="dropdown"]',
  // MUI-style selects: aria-haspopup="true" — only when labeled, so nav
  // hamburger menus and account dropdowns don't flood the field list
  '[aria-haspopup="true"][aria-labelledby]',
  '[aria-haspopup="true"][aria-label]',
  // intl-tel-input-style phone country flag button (.iti__selected-flag /
  // legacy .selected-flag) — often carries no ARIA at all
  '[class*="selected-flag"]',
].join(', ')

/**
 * How a widget fill ended. 'no-options' (nothing ever rendered) is the only
 * case where falling back to typing plain text into the control makes sense.
 */
export type WidgetFillOutcome = 'filled' | 'no-options' | 'no-match'

function pointerClick(el: HTMLElement): void {
  const opts = { bubbles: true, cancelable: true, composed: true }
  el.dispatchEvent(new PointerEvent('pointerdown', opts))
  el.dispatchEvent(new MouseEvent('mousedown', opts))
  el.dispatchEvent(new PointerEvent('pointerup', opts))
  el.dispatchEvent(new MouseEvent('mouseup', opts))
  el.dispatchEvent(new MouseEvent('click', opts))
}

function pressKey(el: HTMLElement, key: string): void {
  const opts = { bubbles: true, cancelable: true, key, composed: true }
  el.dispatchEvent(new KeyboardEvent('keydown', opts))
  el.dispatchEvent(new KeyboardEvent('keyup', opts))
}

function visibleOptions(exclude: ReadonlySet<Element>, doc: Document): HTMLElement[] {
  return deepQueryAll<HTMLElement>(doc, OPTION_SELECTOR).filter(
    (el) => !exclude.has(el) && isElementVisible(el),
  )
}

async function waitForOptions(
  exclude: ReadonlySet<Element>,
  doc: Document,
  timeoutMs: number,
): Promise<HTMLElement[]> {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const found = visibleOptions(exclude, doc)
    if (found.length > 0) return found
    if (Date.now() > deadline) return []
    await sleep(80)
  }
}

function optionText(el: HTMLElement): string {
  return (el.textContent ?? '').replace(/\s+/g, ' ').trim()
}

const optionSignature = (els: HTMLElement[]) => els.map(optionText).join('␞')

const INNER_INPUT_SELECTOR = 'input:not([type=hidden]):not([type=checkbox]):not([type=radio])'

/** The editable input inside/behind a combobox control, if any (React-Select). */
function innerInput(control: HTMLElement): HTMLInputElement | null {
  if (control.localName === 'input') return control as HTMLInputElement
  return (
    control.querySelector<HTMLInputElement>(INNER_INPUT_SELECTOR) ??
    control.shadowRoot?.querySelector<HTMLInputElement>(INNER_INPUT_SELECTOR) ??
    null
  )
}

function clickOption(option: HTMLElement): void {
  option.scrollIntoView({ block: 'nearest' })
  pointerClick(option)
}

function pickIndex(options: HTMLElement[], match: MatchedField): number {
  return chooseOptionMulti(
    options.map((o) => ({ value: o.getAttribute('data-value') ?? '', label: optionText(o) })),
    match.candidates,
    match.kind,
  )
}

/**
 * Fill a custom dropdown/combobox.
 * Must run sequentially per page — two open menus interfere with each other.
 */
export async function fillWidget(
  control: HTMLElement,
  match: MatchedField,
): Promise<WidgetFillOutcome> {
  const doc = control.ownerDocument
  // Snapshot options that are ALREADY VISIBLE (other static listboxes). Hidden
  // pre-rendered options must stay eligible — the standard APG combobox keeps
  // its menu in the DOM (display:none) until opened.
  const preExisting = new Set<Element>(
    deepQueryAll<HTMLElement>(doc, OPTION_SELECTOR).filter(isElementVisible),
  )

  const input = innerInput(control)
  try {
    control.scrollIntoView({ block: 'center' })
  } catch {
    /* scroll can throw in odd embeds; non-fatal */
  }

  // 1. Open.
  ;(input ?? control).focus()
  pointerClick(control)
  let options = await waitForOptions(preExisting, doc, 900)

  // 2. If nothing rendered, try keyboard-open, then typing (typeahead filter).
  if (options.length === 0) {
    pressKey(input ?? control, 'ArrowDown')
    options = await waitForOptions(preExisting, doc, 500)
  }
  if (options.length === 0 && input) {
    setNativeValue(input, match.candidates[0] ?? match.value, { keepFocus: true })
    options = await waitForOptions(preExisting, doc, 1200)
  }
  if (options.length === 0) {
    pressKey(input ?? control, 'Escape')
    return 'no-options'
  }

  // 3. Choose. Cap the list; huge country lists are fine but guard degenerate pages.
  const rendered = options.slice(0, 400)
  const idx = pickIndex(rendered, match)

  // 3b. Typeahead fallback: the open-all list had no match — type each
  // candidate value in turn to filter ("BSc" may find nothing while
  // "Bachelor" does). Wait for the option list to actually CHANGE from the
  // pre-typing snapshot; async selects debounce, and re-reading too early
  // returns the stale list.
  if (idx < 0 && input && !input.value) {
    let before = optionSignature(rendered)
    for (const candidate of match.candidates.slice(0, 3)) {
      setNativeValue(input, candidate, { keepFocus: true })
      const deadline = Date.now() + 1200
      let filtered: HTMLElement[] = []
      for (;;) {
        filtered = visibleOptions(preExisting, doc)
        if (filtered.length > 0 && optionSignature(filtered) !== before) break
        if (Date.now() > deadline) break
        await sleep(80)
      }
      const fIdx = filtered.length > 0 ? pickIndex(filtered, match) : -1
      if (fIdx >= 0) {
        clickOption(filtered[fIdx])
        await sleep(60)
        return 'filled'
      }
      before = optionSignature(filtered)
    }
    pressKey(input, 'Escape')
    return 'no-match'
  }

  if (idx < 0) {
    pressKey(input ?? control, 'Escape')
    return 'no-match'
  }

  // 4. Click the winner.
  clickOption(rendered[idx])
  await sleep(60)

  // 5. If the menu is somehow still open, close it so the next widget can open.
  const lingering = visibleOptions(preExisting, doc)
  if (lingering.length > 0) pressKey(input ?? control, 'Escape')
  return 'filled'
}

/** Placeholder-looking text that does NOT count as a chosen value. */
const PLACEHOLDER_RE = /^(select|choose|pick|search|please|none|all|any|--|—|…|\.\.\.)/i

/** Best-effort: does this widget already show a chosen value? */
export function widgetHasValue(control: HTMLElement): boolean {
  const input = innerInput(control)
  if (input?.value.trim()) return true
  if (control.querySelector('[class*="singleValue"], [class*="single-value"]')) return true
  const automationValue = control.getAttribute('data-value')
  if (automationValue && automationValue.trim()) return true
  if (!input) {
    // Button/div widgets (Workday, APG comboboxes) show the chosen value as text.
    const text = (control.textContent ?? '').replace(/\s+/g, ' ').trim()
    if (text && !PLACEHOLDER_RE.test(text)) return true
  }
  return false
}

/**
 * Read a custom dropdown's choices by briefly opening it, then restoring it.
 *
 * Needed because react-select (Greenhouse, Lever) builds its menu only on
 * open — nothing is in the DOM to read passively. This therefore MUTATES the
 * page (focus + click + Escape), so it is never called during a background
 * scan: only when the person explicitly opens the answer editor for this
 * field. Any pre-existing selection is left alone — we never click an option.
 */
export async function readWidgetOptions(control: HTMLElement): Promise<string[]> {
  const doc = control.ownerDocument
  const preExisting = new Set<Element>(
    deepQueryAll<HTMLElement>(doc, OPTION_SELECTOR).filter(isElementVisible),
  )
  const input = innerInput(control)
  const active = doc.activeElement as HTMLElement | null
  try {
    ;(input ?? control).focus()
    pointerClick(control)
    let options = await waitForOptions(preExisting, doc, 900)
    if (options.length === 0) {
      pressKey(input ?? control, 'ArrowDown')
      options = await waitForOptions(preExisting, doc, 600)
    }
    return options.slice(0, 200).map(optionText)
  } catch {
    return []
  } finally {
    // Close without choosing anything, and hand focus back where it was.
    try {
      pressKey(input ?? control, 'Escape')
      ;(input ?? control).blur()
      if (active && active !== input && active !== control) active.focus?.()
    } catch {
      /* best effort */
    }
  }
}
