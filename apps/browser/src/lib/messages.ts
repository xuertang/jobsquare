/**
 * Message protocol. All cross-frame coordination goes through extension
 * messaging (popup/content → background → every frame in the tab) — never
 * window.postMessage, which web pages could forge to trigger fills and
 * harvest profile data from attacker-controlled forms.
 */

export interface FillResult {
  detected: number
  filled: number
  skipped: number
  /** Human-readable labels of the fields that were filled, for the popup. */
  filledFields: string[]
  /** Detected fields we had no profile value for. */
  unmatched: string[]
  /** Number of frames that contributed to this result. */
  frames?: number
}

export type PreviewStatus = 'fill' | 'skip' | 'unmatched'

export interface PreviewItem {
  /** Match key (spec key, custom:<id>, or file:<slot>); '' for unmatched fields. */
  key: string
  /** Matched profile-field label ("Email"); '' for unmatched fields. */
  label: string
  /** The value/selection that would be filled; '' when nothing applies. */
  value: string
  /** The field's own label as it appears on the page. */
  displayLabel: string
  /** fill = will be filled · skip = has a value / user-skipped · unmatched = no profile match. */
  status: PreviewStatus
  /** Human name of the control: text, dropdown, radio, file, rich text… */
  control: string
  /**
   * For unmatched choice fields (dropdown / radio / custom dropdown): the
   * options the page actually offers, so the answer editor can present them
   * instead of an empty text box. Absent for text fields, and for widgets
   * whose menu only exists once opened.
   */
  options?: string[]
}

export interface ScanPreview {
  items: PreviewItem[]
}

export function emptyFillResult(): FillResult {
  return { detected: 0, filled: 0, skipped: 0, filledFields: [], unmatched: [], frames: 0 }
}

export function mergeFillResults(a: FillResult, b: FillResult): FillResult {
  return {
    detected: a.detected + b.detected,
    filled: a.filled + b.filled,
    skipped: a.skipped + b.skipped,
    filledFields: [...a.filledFields, ...b.filledFields].slice(0, 60),
    unmatched: [...a.unmatched, ...b.unmatched].slice(0, 30),
    frames: (a.frames ?? 1) + (b.frames ?? 1),
  }
}

/** Cross-frame identity: matched rows collapse per match key + status, unmatched per page label. */
const itemIdent = (i: PreviewItem) =>
  i.status === 'unmatched' ? `u:${i.displayLabel}` : `${i.status}:${i.key}`

export function mergePreviews(a: ScanPreview, b: ScanPreview): ScanPreview {
  const items = [...a.items]
  const seen = new Set(a.items.map(itemIdent))
  for (const item of b.items) {
    const id = itemIdent(item)
    // Keep one row per identity for the review UI (a fill still hits every field).
    if (!seen.has(id)) {
      seen.add(id)
      items.push(item)
    }
  }
  return { items: items.slice(0, 150) }
}

// --- popup/content → background ---------------------------------------------

export interface RunTreeRequest {
  type: 'GONGZUO_RUN_TREE'
  /** Tab to run in. Omitted when sent from a content script (background uses sender.tab). */
  tabId?: number
  fill: boolean
  skipKeys?: string[]
}

/** Popup → background → content: choices for one question on the page. */
export interface FieldOptionsRequest {
  type: 'GONGZUO_FIELD_OPTIONS'
  /** Tab to ask. Omitted from a content script (background uses sender.tab). */
  tabId?: number
  question: string
}

export interface FieldOptionsResponse {
  ok: boolean
  options: string[]
}

export type BackgroundRequest =
  | { type: 'GONGZUO_BADGE'; count: number }
  | { type: 'GONGZUO_OPEN_OPTIONS' }
  | RunTreeRequest
  | FieldOptionsRequest
  | FrameAck
  | FrameResult

export interface BlockedFrames {
  frames: number
  detected: number
  fillable: number
  hosts: string[]
}

export interface RunTreeResponse {
  ok: boolean
  result: FillResult
  preview: ScanPreview
  /** Frames excluded from filling for privacy (unknown cross-origin embeds). */
  blocked?: BlockedFrames
  error?: string
}

// --- background → every frame in the tab -------------------------------------

export interface FrameRun {
  type: 'GONGZUO_FRAME_RUN'
  requestId: string
  fill: boolean
  skipKeys?: string[]
}

/** Sent by each frame immediately so the aggregator knows who is working. */
export interface FrameAck {
  type: 'GONGZUO_FRAME_ACK'
  requestId: string
}

export interface FrameResult {
  type: 'GONGZUO_FRAME_RESULT'
  requestId: string
  result: FillResult
  preview: ScanPreview
  /** Set by frames excluded from filling (not same-site / not a known ATS):
   * how many fields they COULD have detected/filled. Never merged into the
   * main counts — surfaced separately so blocked forms aren't invisible. */
  blockedDetected?: number
  blockedFillable?: number
  /** The blocked frame's host, so the popup can say who was skipped. */
  blockedHost?: string
}

/** Sent by the background to the TOP frame after a fill aggregation resolves,
 * so tracking / continuous-fill arming keys off the merged whole-tab result. */
export interface TreeDone {
  type: 'GONGZUO_TREE_DONE'
  result: FillResult
}

// --- popup → top frame (simple probes) ---------------------------------------

export type ContentRequest = { type: 'GONGZUO_PING' } | FrameRun | TreeDone

export type ContentResponse = { ok: true; pong: true } | { ok: false; error: string }

export function messageType(msg: unknown): string {
  if (
    !!msg &&
    typeof msg === 'object' &&
    'type' in msg &&
    typeof (msg as { type: unknown }).type === 'string'
  ) {
    return (msg as { type: string }).type
  }
  return ''
}

// --- sanitizers (defense in depth for anything that crossed a boundary) ------

const num = (v: unknown) =>
  typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.min(Math.floor(v), 10_000) : 0
const str = (v: unknown, cap: number) => (typeof v === 'string' ? v.slice(0, cap) : '')
const strArr = (v: unknown, cap: number) =>
  Array.isArray(v)
    ? v.filter((s): s is string => typeof s === 'string').map((s) => s.slice(0, 120)).slice(0, cap)
    : []

export function sanitizeFillResult(raw: unknown): FillResult {
  const r = (raw ?? {}) as Partial<FillResult>
  return {
    detected: num(r.detected),
    filled: num(r.filled),
    skipped: num(r.skipped),
    filledFields: strArr(r.filledFields, 60),
    unmatched: strArr(r.unmatched, 30),
    frames: Math.max(1, num(r.frames)),
  }
}

const PREVIEW_STATUSES: PreviewStatus[] = ['fill', 'skip', 'unmatched']

export function sanitizePreview(raw: unknown): ScanPreview {
  const p = (raw ?? {}) as Partial<ScanPreview>
  const items = Array.isArray(p.items)
    ? p.items
        .filter((i): i is PreviewItem => !!i && typeof i === 'object')
        .map((i) => ({
          key: str(i.key, 80),
          label: str(i.label, 80),
          value: str(i.value, 400),
          displayLabel: str(i.displayLabel, 120),
          status: PREVIEW_STATUSES.includes(i.status as PreviewStatus)
            ? (i.status as PreviewStatus)
            : ('fill' as PreviewStatus),
          control: str(i.control, 24),
          // Cross-frame payload: cap count and length, drop blanks entirely so
          // an absent/garbage value never renders an empty chip row.
          ...(Array.isArray(i.options) && i.options.length
            ? {
                options: i.options
                  .filter((o): o is string => typeof o === 'string')
                  .map((o) => str(o, 120))
                  .filter(Boolean)
                  .slice(0, 60),
              }
            : {}),
        }))
        .filter((i) => i.key || i.displayLabel)
        .slice(0, 150)
    : []
  return { items }
}
