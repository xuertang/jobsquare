import {
  emptyFillResult,
  type ContentRequest,
  type ContentResponse,
  type RunTreeRequest,
  type RunTreeResponse,
  type FieldOptionsRequest,
  type FieldOptionsResponse,
} from '../lib/messages'

export interface TabState {
  tabId: number
}

export async function getActiveTab(): Promise<TabState | null> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  if (!tab?.id) return null
  return { tabId: tab.id }
}

/** Is a Gongzuo content script alive in the top frame of this tab? */
export function ping(tabId: number): Promise<boolean> {
  const req: ContentRequest = { type: 'GONGZUO_PING' }
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, req, { frameId: 0 }, (res: ContentResponse) => {
      if (chrome.runtime.lastError) {
        resolve(false)
        return
      }
      resolve(!!res && res.ok)
    })
  })
}

/** Run a scan or fill across every frame in the tab (background aggregates). */
export async function runTree(tabId: number, fill: boolean): Promise<RunTreeResponse> {
  const req: RunTreeRequest = { type: 'GONGZUO_RUN_TREE', tabId, fill }
  try {
    const res = (await chrome.runtime.sendMessage(req)) as RunTreeResponse | undefined
    return (
      res ?? { ok: false, result: emptyFillResult(), preview: { items: [] } }
    )
  } catch {
    return { ok: false, result: emptyFillResult(), preview: { items: [] } }
  }
}

/**
 * Choices for one question on the page, for the answer editor. Resolved by the
 * content script, which may briefly open a custom dropdown to read its menu,
 * so this is only called when the person opens the editor for that field.
 */
export async function fieldOptions(tabId: number, question: string): Promise<string[]> {
  const req: FieldOptionsRequest = { type: 'GONGZUO_FIELD_OPTIONS', tabId, question }
  try {
    const res = (await chrome.runtime.sendMessage(req)) as FieldOptionsResponse | undefined
    return res?.options ?? []
  } catch {
    return []
  }
}

export function openOptions(): void {
  chrome.runtime.openOptionsPage()
}
