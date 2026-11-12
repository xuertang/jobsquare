import {
  emptyFillResult,
  mergeFillResults,
  mergePreviews,
  messageType,
  sanitizeFillResult,
  sanitizePreview,
  type FrameAck,
  type FrameResult,
  type FrameRun,
  type RunTreeRequest,
  type RunTreeResponse,
  type ScanPreview,
  type FieldOptionsRequest,
  type FieldOptionsResponse,
} from '../lib/messages'
import { getSettings, seedIfEmpty } from '../lib/storage'

const BADGE_COLOR = '#6366f1'

chrome.runtime.onInstalled.addListener(async (details) => {
  await seedIfEmpty()
  chrome.action.setBadgeBackgroundColor({ color: BADGE_COLOR })
  if (details.reason === 'install') {
    chrome.runtime.openOptionsPage()
  }
})

chrome.runtime.onStartup?.addListener(() => {
  chrome.action.setBadgeBackgroundColor({ color: BADGE_COLOR })
})

async function setBadge(tabId: number | undefined, count: number): Promise<void> {
  if (tabId == null) return
  const settings = await getSettings()
  const text = settings.showBadge && count > 0 ? String(count) : ''
  try {
    await chrome.action.setBadgeText({ tabId, text })
    await chrome.action.setBadgeBackgroundColor({ tabId, color: BADGE_COLOR })
  } catch {
    // tab may have closed
  }
}

// --- cross-frame run aggregation ---------------------------------------------
// One fill/scan request fans out to every frame in the tab (each frame handles
// exactly its own document). Frames ACK immediately, then report results; the
// aggregation resolves when every ACKed frame reported or on timeout.

interface Aggregation {
  acked: number
  /** ACK window closed — the set of working frames is final. */
  ackClosed: boolean
  resolved: boolean
  results: ReturnType<typeof emptyFillResult>[]
  previews: ScanPreview[]
  blocked: { frames: number; detected: number; fillable: number; hosts: Set<string> }
  finish: () => void
  ackWindow: ReturnType<typeof setTimeout>
  hardCap: ReturnType<typeof setTimeout>
}

const aggregations = new Map<string, Aggregation>()

function runTree(req: RunTreeRequest, tabId: number, respond: (r: RunTreeResponse) => void): void {
  const requestId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

  const agg: Aggregation = {
    acked: 0,
    ackClosed: false,
    resolved: false,
    results: [],
    previews: [],
    blocked: { frames: 0, detected: 0, fillable: 0, hosts: new Set() },
    finish: () => {
      if (agg.resolved) return
      agg.resolved = true
      clearTimeout(agg.ackWindow)
      clearTimeout(agg.hardCap)
      aggregations.delete(requestId)
      let result = emptyFillResult()
      let preview: ScanPreview = { items: [] }
      for (const r of agg.results) result = mergeFillResults(result, r)
      for (const p of agg.previews) preview = mergePreviews(preview, p)
      // frames merged additively from zero; correct the double-count of the seed
      result.frames = agg.results.length
      const blocked =
        agg.blocked.frames > 0
          ? {
              frames: agg.blocked.frames,
              detected: agg.blocked.detected,
              fillable: agg.blocked.fillable,
              hosts: Array.from(agg.blocked.hosts).slice(0, 5),
            }
          : undefined
      respond({ ok: agg.results.length > 0, result, preview, blocked, error: agg.results.length ? undefined : 'No frame answered — is this a regular web page?' })
      // Tell the top frame the merged outcome so tracking / continuous-fill
      // arming keys off whole-tab numbers (popup-initiated fills included).
      if (req.fill && agg.results.length > 0) {
        chrome.tabs
          .sendMessage(tabId, { type: 'GONGZUO_TREE_DONE', result }, { frameId: 0 })
          .catch(() => {})
      }
    },
    // After the ACK window closes we know how many frames are working.
    ackWindow: setTimeout(() => {
      agg.ackClosed = true
      // Nobody working, or every worker already reported → done.
      if (agg.results.length >= agg.acked) agg.finish()
    }, 800),
    // Hard cap: widget-heavy fills are slow, but never hang the caller.
    hardCap: setTimeout(() => agg.finish(), req.fill ? 25_000 : 4_000),
  }
  aggregations.set(requestId, agg)

  const msg: FrameRun = {
    type: 'GONGZUO_FRAME_RUN',
    requestId,
    fill: req.fill,
    skipKeys: req.skipKeys,
  }
  chrome.tabs.sendMessage(tabId, msg).catch((err: unknown) => {
    // Frames reply via separate FRAME_ACK/FRAME_RESULT messages, never via
    // sendResponse — so this promise ALWAYS rejects with "The message port
    // closed…" even on success. Only "Could not establish connection" means
    // no content script exists anywhere in the tab (chrome:// etc.).
    const m = err instanceof Error ? err.message : String(err)
    if (m.includes('Could not establish connection') || m.includes('Receiving end does not exist')) {
      agg.finish()
    }
  })
}

function onFrameAck(msg: FrameAck): void {
  const agg = aggregations.get(msg.requestId)
  if (agg) agg.acked++
}

function onFrameResult(msg: FrameResult): void {
  const agg = aggregations.get(msg.requestId)
  if (!agg || agg.resolved) return
  agg.results.push(sanitizeFillResult(msg.result))
  agg.previews.push(sanitizePreview(msg.preview))
  const blockedDetected = Number(msg.blockedDetected) || 0
  if (blockedDetected > 0) {
    agg.blocked.frames++
    agg.blocked.detected += Math.min(blockedDetected, 10_000)
    agg.blocked.fillable += Math.min(Number(msg.blockedFillable) || 0, 10_000)
    if (typeof msg.blockedHost === 'string' && msg.blockedHost) {
      agg.blocked.hosts.add(msg.blockedHost.slice(0, 100))
    }
  }
  // Only resolve early once the ACK window closed — before that, slower frames
  // may not have ACKed yet and a fast frame's result would end the run.
  if (agg.ackClosed && agg.results.length >= agg.acked) agg.finish()
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const type = messageType(message)

  if (type === 'GONGZUO_BADGE') {
    const count = Number((message as { count?: unknown }).count) || 0
    void setBadge(sender.tab?.id, count)
    return false
  }

  if (type === 'GONGZUO_OPEN_OPTIONS') {
    chrome.runtime.openOptionsPage()
    return false
  }

  if (type === 'GONGZUO_RUN_TREE') {
    const req = message as RunTreeRequest
    const tabId = req.tabId ?? sender.tab?.id
    if (tabId == null) {
      sendResponse({
        ok: false,
        result: emptyFillResult(),
        preview: { items: [] },
        error: 'no tab',
      } satisfies RunTreeResponse)
      return false
    }
    runTree(req, tabId, sendResponse)
    return true // async response
  }

  if (type === 'GONGZUO_FIELD_OPTIONS') {
    const req = message as FieldOptionsRequest
    const tabId = req.tabId ?? sender.tab?.id
    if (tabId == null) {
      sendResponse({ ok: false, options: [] } satisfies FieldOptionsResponse)
      return false
    }
    // The field may live in any frame, so ask the tab and take the first
    // frame that recognizes the question.
    chrome.tabs
      .sendMessage(tabId, { type: 'GONGZUO_FIELD_OPTIONS', question: req.question })
      .then((res: FieldOptionsResponse | undefined) =>
        sendResponse({ ok: !!res?.ok, options: res?.options ?? [] } satisfies FieldOptionsResponse),
      )
      .catch(() => sendResponse({ ok: false, options: [] } satisfies FieldOptionsResponse))
    return true // async response
  }

  if (type === 'GONGZUO_FRAME_ACK') {
    onFrameAck(message as FrameAck)
    return false
  }

  if (type === 'GONGZUO_FRAME_RESULT') {
    onFrameResult(message as FrameResult)
    return false
  }

  return false
})

// Clear the badge when navigating to a new page within a tab.
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === 'loading') {
    chrome.action.setBadgeText({ tabId, text: '' }).catch(() => {})
  }
})
