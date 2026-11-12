import { deepQueryAll, isElementVisible, sleep } from '../lib/dom'
import {
  collectFields,
  fieldOptions,
  hostAllowed,
  isSearchControl,
  normalizeOptions,
} from '../lib/collect'
import {
  createEntryIndexer,
  getContext,
  matchContext,
  matchFileContext,
  normalize,
  type IndexedSection,
  type SpecCategory,
} from '../lib/fieldMatcher'
import {
  applyMatch,
  attachFile,
  clearHighlights,
  contextFor,
  hasExistingValue,
  highlight,
  type Fillable,
} from '../lib/filler'
import {
  fillWidget,
  readWidgetOptions,
  widgetHasValue,
  WIDGET_CONTROL_SELECTOR,
} from '../lib/widgetFiller'
import {
  emptyFillResult,
  messageType,
  sanitizeFillResult,
  type ContentResponse,
  type FillResult,
  type FrameResult,
  type FrameRun,
  type RunTreeRequest,
  type RunTreeResponse,
  type ScanPreview,
  type TreeDone,
} from '../lib/messages'
import {
  addCustomAnswer,
  getProfile,
  getSettings,
  recordApplication,
  type Settings,
} from '../lib/storage'
import { mountOverlay, type OverlayHandle } from './overlay'

const isTop = window.top === window

/** May THIS frame participate in scans/fills? Top always; children only when
 * same-site with the top page or on the ATS allowlist. */
function frameAllowed(): boolean {
  if (isTop) return true
  const own = location.hostname
  try {
    const origins = location.ancestorOrigins
    const topOrigin = origins?.[origins.length - 1]
    const topHost = topOrigin ? new URL(topOrigin).hostname : undefined
    return hostAllowed(own, topHost)
  } catch {
    return hostAllowed(own)
  }
}

/**
 * Every http(s) frame handles exactly its own document (each gets the
 * FRAME_RUN broadcast). srcdoc/about:blank/blob iframes get no content script,
 * so the parent reaches in via contentDocument — ownership is decided by the
 * child DOCUMENT's resolved protocol, never the raw src attribute (a relative
 * src still resolves to http and runs its own instance).
 */
function collectOwnFields(): Fillable[] {
  const fields = collectFields(document)
  for (const frame of Array.from(document.querySelectorAll('iframe'))) {
    try {
      const doc = frame.contentDocument
      if (doc && !/^https?:$/i.test(doc.location.protocol)) {
        fields.push(...collectFields(doc))
      }
    } catch {
      // cross-origin — its own instance handles it
    }
  }
  return fields
}

interface RunOptions {
  fill: boolean
  skipKeys?: ReadonlySet<string>
}

function disabledCategories(settings: Settings): Set<SpecCategory> {
  const off = new Set<SpecCategory>()
  if (!settings.fillEEO) off.add('eeo')
  if (!settings.fillDisability) off.add('disability')
  if (!settings.fillSalary) off.add('salary')
  return off
}

interface LocalRun {
  result: FillResult
  preview: ScanPreview
  /** Repeating-section rows the form currently shows (education/experience). */
  rows: Record<IndexedSection, number>
}

function emptyLocalRun(): LocalRun {
  return {
    result: { ...emptyFillResult(), frames: 1 },
    preview: { items: [] },
    rows: { education: 0, experience: 0 },
  }
}

/** Human name of the control, for the popup's field breakdown. */
function controlName(field: Fillable): string {
  switch (field.type) {
    case 'value':
      if (field.el.localName === 'textarea') return 'textarea'
      return (field.el as HTMLInputElement).type || 'text'
    case 'select':
      return 'dropdown'
    case 'radio':
      return 'radio'
    case 'checkbox':
      return 'checkbox'
    case 'file':
      return 'file'
    case 'contenteditable':
      return 'rich text'
    case 'widget':
      return 'custom dropdown'
  }
}

/** Match (and optionally fill) every field in THIS frame. */
async function runLocal({ fill, skipKeys }: RunOptions): Promise<LocalRun> {
  const [profile, settings] = await Promise.all([getProfile(), getSettings()])
  const fields = collectOwnFields()
  const disabled = disabledCategories(settings)
  // Maps the Nth education/experience row on the form to profile entry N.
  const indexer = createEntryIndexer()

  const result: FillResult = { ...emptyFillResult(), detected: fields.length, frames: 1 }
  const preview: ScanPreview = { items: [] }
  const seenUnmatched = new Set<string>()

  const pushItem = (item: {
    key: string
    label: string
    value: string
    displayLabel: string
    status: 'fill' | 'skip' | 'unmatched'
    control: string
    options?: string[]
  }) => {
    if (preview.items.length < 150) preview.items.push(item)
  }
  const pushUnmatched = (field: Fillable, displayLabel: string) => {
    // Surface only real question-looking labels for the answer-memory UI.
    if (!displayLabel || displayLabel.length <= 6 || seenUnmatched.has(displayLabel)) return
    seenUnmatched.add(displayLabel)
    // Choice fields carry their options so the answer editor can offer them.
    const options = fieldOptions(field)
    pushItem({
      key: '',
      label: '',
      value: '',
      displayLabel,
      status: 'unmatched',
      control: controlName(field),
      ...(options.length ? { options } : {}),
    })
    if (result.unmatched.length < 15) result.unmatched.push(displayLabel)
  }

  if (fill && settings.highlightFilled) clearHighlights()

  for (const field of fields) {
    const ctx = contextFor(field)
    const control = controlName(field)

    // File inputs: match against stored documents, not text specs.
    if (field.type === 'file') {
      const slot = matchFileContext(ctx)
      if (!slot) {
        pushUnmatched(field, ctx.displayLabel)
        continue
      }
      const stored = profile[slot]
      const key = `file:${slot}`
      const label = slot === 'resume' ? 'Resume' : 'Cover letter file'
      if (!stored) {
        // Recognized upload field, but no document stored yet.
        pushItem({ key, label, value: '', displayLabel: ctx.displayLabel, status: 'unmatched', control })
        continue
      }
      if (!settings.attachFiles) {
        pushItem({ key, label, value: stored.name, displayLabel: ctx.displayLabel, status: 'skip', control })
        continue
      }
      if (hasExistingValue(field) && !settings.overwriteExisting) {
        result.skipped++
        pushItem({ key, label, value: stored.name, displayLabel: ctx.displayLabel, status: 'skip', control })
        continue
      }
      // Skip-check BEFORE the scan branch so a scan with skipKeys (the
      // continuous-fill probe) doesn't count user-skipped fields as fillable.
      if (skipKeys?.has(key)) {
        result.skipped++
        pushItem({ key, label, value: stored.name, displayLabel: ctx.displayLabel, status: 'skip', control })
        continue
      }
      if (!fill) {
        result.filled++
        result.filledFields.push(label)
        pushItem({ key, label, value: stored.name, displayLabel: ctx.displayLabel, status: 'fill', control })
        continue
      }
      if (attachFile(field.el, stored)) {
        result.filled++
        result.filledFields.push(label)
        if (settings.highlightFilled) highlight(field)
      } else {
        result.skipped++
      }
      continue
    }

    const match = matchContext(ctx, profile, profile.customAnswers, {
      disabledCategories: disabled,
      entryIndex: indexer.next,
    })

    if (!match) {
      pushUnmatched(field, ctx.displayLabel)
      continue
    }

    const existing = field.type === 'widget' ? widgetHasValue(field.el) : hasExistingValue(field)
    if (existing && !settings.overwriteExisting) {
      result.skipped++
      pushItem({
        key: match.key,
        label: match.label,
        value: match.value,
        displayLabel: ctx.displayLabel,
        status: 'skip',
        control,
      })
      continue
    }

    if (skipKeys?.has(match.key)) {
      result.skipped++
      pushItem({
        key: match.key,
        label: match.label,
        value: match.value,
        displayLabel: ctx.displayLabel,
        status: 'skip',
        control,
      })
      continue
    }

    if (!fill) {
      result.filled++
      result.filledFields.push(match.label)
      pushItem({
        key: match.key,
        label: match.label,
        value: match.value,
        displayLabel: ctx.displayLabel,
        status: 'fill',
        control,
      })
      continue
    }

    let ok: boolean
    if (field.type === 'widget') {
      const outcome = await fillWidget(field.el, match)
      ok = outcome === 'filled'
      // Only when NO options ever rendered may the control be a plain
      // typeahead input — 'no-match' means options existed and typing a raw
      // string would leave an uncommitted search term that looks filled.
      if (outcome === 'no-options' && field.el.localName === 'input') {
        ok = applyMatch({ type: 'value', el: field.el as HTMLInputElement }, match)
      }
    } else {
      ok = applyMatch(field, match)
    }

    if (ok) {
      result.filled++
      result.filledFields.push(match.label)
      if (settings.highlightFilled) highlight(field)
    } else {
      result.skipped++
    }
  }

  return {
    result,
    preview,
    rows: { education: indexer.rowCount('education'), experience: indexer.rowCount('experience') },
  }
}

/**
 * Choices for one question, found by its page label — used by the answer
 * editor so saving an answer for a dropdown offers the real options.
 *
 * Passive extraction (fieldOptions) covers native selects, radio groups and
 * pre-rendered listboxes. react-select widgets build their menu only on open,
 * so those are read by briefly opening the control. That mutation is why this
 * runs on demand — when the person opens the editor for this field — and
 * never during a scan.
 */
function findFieldByQuestion(question: string): Fillable | null {
  for (const field of collectOwnFields()) {
    if (field.type === 'file') continue
    if (contextFor(field).displayLabel === question) return field
  }
  return null
}

async function optionsForField(field: Fillable): Promise<string[]> {
  const passive = fieldOptions(field)
  if (passive.length) return passive
  if (field.type === 'widget') return normalizeOptions(await readWidgetOptions(field.el))
  return []
}

async function optionsForQuestion(question: string): Promise<string[]> {
  const field = findFieldByQuestion(question)
  return field ? optionsForField(field) : []
}

// --- repeating sections: "Add another" expansion ------------------------------

/** Entries the user actually filled in (ignoring the id field). */
function countProfileEntries<T extends { id: string }>(entries: T[]): number {
  return entries.filter((e) =>
    Object.entries(e).some(
      ([k, v]) => k !== 'id' && typeof v === 'string' && v.trim().length > 0,
    ),
  ).length
}

const ADD_TEXT_RE = /\badd\b|\banother\b/i
const SECTION_RES: Record<IndexedSection, RegExp> = {
  education: /education|school|degree|academic/,
  experience: /experience|employment|work history|job history|position|employer/,
}

/**
 * Find the "Add another" control for a repeating section. Only inert anchors
 * (#/javascript:) and buttons qualify — a real link would navigate away.
 */
function findSectionAdder(kind: IndexedSection): HTMLElement | null {
  for (const el of deepQueryAll<HTMLElement>(document, 'button, a, [role="button"]')) {
    if (el.closest('[data-browser-overlay]')) continue
    const text = (el.textContent ?? '').replace(/\s+/g, ' ').trim()
    if (!text || text.length > 60 || !ADD_TEXT_RE.test(text)) continue
    if (!isElementVisible(el)) continue
    if (el.localName === 'a') {
      const href = el.getAttribute('href') ?? ''
      const inert = href === '' || href === '#' || href.startsWith('javascript:')
      if (!inert && el.getAttribute('role') !== 'button') continue
    }
    const signal = normalize(text) + ' ' + getContext(el).sectionSignal
    if (SECTION_RES[kind].test(signal)) return el
  }
  return null
}

async function waitForFieldGrowth(before: number, timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    if (collectOwnFields().length > before) return true
    if (Date.now() > deadline) return false
    await sleep(100)
  }
}

/**
 * Fill this frame; if the profile has more education/experience entries than
 * the form shows AND the section has an "Add another" control, click it, wait
 * for the new row, and fill again. Already-filled fields are skipped on
 * re-passes (hasExistingValue), so only the new rows get written.
 */
async function runLocalFill(skipKeys: ReadonlySet<string>): Promise<LocalRun> {
  let run = await runLocal({ fill: true, skipKeys })
  let totalFilled = run.result.filled
  let filledFields = [...run.result.filledFields]

  for (let round = 0; round < 6; round++) {
    const profile = await getProfile()
    const want: Record<IndexedSection, number> = {
      education: countProfileEntries(profile.education),
      experience: countProfileEntries(profile.experience),
    }
    // Only expand sections the form actually has (rows > 0).
    const kind = (['education', 'experience'] as const).find(
      (s) => run.rows[s] > 0 && want[s] > run.rows[s],
    )
    if (!kind) break
    const adder = findSectionAdder(kind)
    if (!adder) break
    const before = collectOwnFields().length
    adder.click()
    if (!(await waitForFieldGrowth(before, 1500))) break
    const again = await runLocal({ fill: true, skipKeys })
    // Guard against a form that ignores the click semantics (no new rows).
    if (again.rows[kind] <= run.rows[kind]) {
      run = again
      break
    }
    totalFilled += again.result.filled
    filledFields = filledFields.concat(again.result.filledFields)
    run = again
  }

  run.result.filled = totalFilled
  run.result.filledFields = filledFields.slice(0, 60)
  return run
}

// --- whole-tab runs (via the background aggregator) --------------------------

async function runTree(fill: boolean, skipKeys: ReadonlySet<string>): Promise<RunTreeResponse> {
  const req: RunTreeRequest = {
    type: 'GONGZUO_RUN_TREE',
    fill,
    skipKeys: Array.from(skipKeys),
  }
  try {
    const res = (await chrome.runtime.sendMessage(req)) as RunTreeResponse | undefined
    if (res) return res
    return { ok: false, result: emptyFillResult(), preview: { items: [] } }
  } catch {
    // Background unreachable — degrade to this frame only.
    const { result, preview } = fill
      ? await runLocalFill(skipKeys)
      : await runLocal({ fill: false, skipKeys })
    return { ok: true, result, preview }
  }
}

// Answer memory lives in storage.addCustomAnswer (shared with the popup).

// --- fill orchestration (top frame) ------------------------------------------
// Bookkeeping (tracker, continuous-fill arming, badge) lives in the FRAME_RUN /
// TREE_DONE handlers so popup- and overlay-initiated fills share one path.

let fillInProgress = false
let fillWatchdog: number | undefined
let continuousArmed = false
let autoRuns = 0
let autoFillPending = false
let lastSkipKeys: ReadonlySet<string> = new Set()

/** User-initiated fill (overlay button). Popup fills go straight to runTree. */
async function userFill(skipKeys: ReadonlySet<string>): Promise<FillResult> {
  autoRuns = 0 // a real user action re-arms the continuous-fill budget
  const { result } = await runTree(true, skipKeys)
  return result
}

/** With continuous fill on, re-fill when a multi-step form reveals a new page. */
async function maybeContinueFill(): Promise<void> {
  if (!continuousArmed || fillInProgress || autoRuns >= 8) return
  const settings = await getSettings()
  if (!settings.continuousFill || settings.overwriteExisting) return
  const { result } = await runLocal({ fill: false, skipKeys: lastSkipKeys })
  if (result.filled === 0) return // nothing new appeared
  autoRuns++ // NOT reset by the fill below — the 8-run cap must bind
  autoFillPending = true
  try {
    await runTree(true, lastSkipKeys)
  } finally {
    autoFillPending = false
  }
}

// --- badge + overlay --------------------------------------------------------

let overlay: OverlayHandle | null = null

function reportBadge(): void {
  void runLocal({ fill: false }).then(({ result, preview }) => {
    chrome.runtime.sendMessage({ type: 'GONGZUO_BADGE', count: result.filled }).catch(() => {
      /* background may be asleep; ignore */
    })
    overlay?.setCount(preview.items.filter((i) => i.status === 'fill').length)
  })
}

async function ensureOverlay(): Promise<void> {
  if (!isTop || overlay) return
  const settings = await getSettings()
  if (!settings.showOverlay) return
  overlay = mountOverlay({
    getPreview: async () => (await runTree(false, new Set())).preview,
    onFill: (skipKeys) => userFill(skipKeys),
    onSaveAnswer: async (question, answer) => {
      await addCustomAnswer(question, answer)
    },
    onLoadOptions: (question) => optionsForQuestion(question),
    onOpenOptions: () => {
      chrome.runtime.sendMessage({ type: 'GONGZUO_OPEN_OPTIONS' }).catch(() => {})
    },
  })
}

// --- runtime message handling ------------------------------------------------

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const type = messageType(message)

  // Broadcast run: EVERY allowed frame answers for its own document.
  if (type === 'GONGZUO_FRAME_RUN') {
    const req = message as FrameRun
    // ACK synchronously so the aggregator knows we're working.
    chrome.runtime.sendMessage({ type: 'GONGZUO_FRAME_ACK', requestId: req.requestId }).catch(() => {})
    const skipKeys = new Set(req.skipKeys ?? [])

    if (isTop && req.fill) {
      lastSkipKeys = skipKeys
      fillInProgress = true
      window.clearTimeout(fillWatchdog)
      fillWatchdog = window.setTimeout(() => {
        fillInProgress = false
      }, 30_000)
    }

    // Unrelated third-party frames (ads, embeds) never see profile data.
    // They still SCAN (never fill) and report what they found via separate
    // blocked* fields, so a form in an unknown ATS frame isn't silently
    // invisible — the popup can tell the user it exists but wasn't filled.
    if (!frameAllowed()) {
      void runLocal({ fill: false, skipKeys }).then(({ result }) => {
        const empty = emptyLocalRun()
        const reply: FrameResult = {
          type: 'GONGZUO_FRAME_RESULT',
          requestId: req.requestId,
          result: empty.result,
          preview: empty.preview,
          blockedDetected: result.detected,
          blockedFillable: result.filled,
          blockedHost: location.hostname,
        }
        chrome.runtime.sendMessage(reply).catch(() => {})
      })
      return false
    }

    const work: Promise<LocalRun> = req.fill
      ? runLocalFill(skipKeys)
      : runLocal({ fill: false, skipKeys })

    void work.then(({ result, preview }) => {
      const reply: FrameResult = {
        type: 'GONGZUO_FRAME_RESULT',
        requestId: req.requestId,
        result,
        preview,
      }
      chrome.runtime.sendMessage(reply).catch(() => {})
    })
    return false
  }

  // Answer editor asking what a dropdown offers. Fields can live in any frame
  // (Greenhouse is often embedded), so this is handled BEFORE the top-frame
  // guard — but only the frame that actually owns the question replies, so the
  // one real answer wins the response race instead of an empty one.
  if (type === 'GONGZUO_FIELD_OPTIONS') {
    const q = String((message as { question?: unknown }).question ?? '')
    const field = q && frameAllowed() ? findFieldByQuestion(q) : null
    if (!field) return false // stay silent; another frame may own it
    void optionsForField(field).then(
      (options) => sendResponse({ ok: options.length > 0, options }),
      () => sendResponse({ ok: false, options: [] }),
    )
    return true // async response
  }

  if (!isTop) return false

  // Merged whole-tab fill finished (from the background aggregator).
  if (type === 'GONGZUO_TREE_DONE') {
    const done = sanitizeFillResult((message as TreeDone).result)
    fillInProgress = false
    window.clearTimeout(fillWatchdog)
    void (async () => {
      const settings = await getSettings()
      if (done.filled > 0 && settings.trackApplications) {
        await recordApplication({
          url: location.href,
          title: document.title,
          filledCount: done.filled,
        }).catch(() => {})
      }
      if (settings.continuousFill && !settings.overwriteExisting) {
        continuousArmed = true
        if (autoFillPending) autoRuns = Math.max(autoRuns, 1) // keep the cap honest
      }
      reportBadge()
    })()
    return false
  }

  if (type === 'GONGZUO_PING') {
    sendResponse({ ok: true, pong: true } satisfies ContentResponse)
    return false
  }

  return false
})

// --- boot -------------------------------------------------------------------

let badgeTimer: number | undefined
function scheduleBadge(): void {
  window.clearTimeout(badgeTimer)
  badgeTimer = window.setTimeout(() => {
    if (fillInProgress) return // our own fills mutate the DOM constantly
    reportBadge()
    void maybeContinueFill()
  }, 800)
}

if (isTop) {
  scheduleBadge()
  void ensureOverlay()
  const observer = new MutationObserver(() => scheduleBadge())
  observer.observe(document.documentElement, { childList: true, subtree: true })
}

// --- diagnostics --------------------------------------------------------------

/**
 * Run `__gongzuoDebug()` in DevTools on any page to see every control Gongzuo
 * saw, why rejected ones were rejected, and what accepted ones matched.
 */
async function debugDump(): Promise<void> {
  const profile = await getProfile()
  const settings = await getSettings()
  const disabled = disabledCategories(settings)
  const indexer = createEntryIndexer()
  const rows: Record<string, string>[] = []

  const collected = new Set(
    collectOwnFields().map((f) => (f.type === 'radio' ? f.els[0] : f.el)),
  )
  const all = deepQueryAll<HTMLElement>(
    document,
    'input, textarea, select, [contenteditable], ' + WIDGET_CONTROL_SELECTOR,
  )

  for (const el of all) {
    const tag = el.localName + ((el as HTMLInputElement).type ? `[${(el as HTMLInputElement).type}]` : '')
    const ctx = getContext(el)
    let status: string
    if (el.closest('[data-browser-overlay]')) status = 'rejected: browser overlay'
    else if (collected.has(el)) {
      const match = matchContext(ctx, profile, profile.customAnswers, {
        disabledCategories: disabled,
        entryIndex: indexer.next,
      })
      status = match ? `matched: ${match.key} → "${match.value.slice(0, 40)}"` : 'collected, no match'
    } else if ((el as HTMLInputElement).disabled) status = 'rejected: disabled'
    else if ((el as HTMLInputElement).readOnly) status = 'rejected: readonly'
    else if (!isElementVisible(el)) status = 'rejected: not visible (self)'
    else if (isSearchControl(el)) status = 'rejected: search control'
    else status = 'rejected: other (nested in widget / unsupported type)'
    rows.push({ tag, label: ctx.displayLabel.slice(0, 50), signal: ctx.signal.slice(0, 70), status })
  }

  console.log(`[gongzuo] frame ${location.href} — allowed to fill: ${frameAllowed()}`)
  console.table(rows)
}

;(window as unknown as { __gongzuoDebug?: () => Promise<void> }).__gongzuoDebug = debugDump

// Mark presence for debugging.
;(window as unknown as { __gongzuo?: boolean }).__gongzuo = true
