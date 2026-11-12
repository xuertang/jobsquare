/** DOM helpers that pierce open shadow roots (Workday & co. render into them). */

export function deepQueryAll<T extends Element>(root: ParentNode, selector: string): T[] {
  const out: T[] = []
  const visit = (node: ParentNode) => {
    try {
      out.push(...Array.from(node.querySelectorAll<T>(selector)))
    } catch {
      return // invalid selector would throw everywhere; bail
    }
    for (const el of Array.from(node.querySelectorAll<HTMLElement>('*'))) {
      if (el.shadowRoot) visit(el.shadowRoot)
    }
  }
  visit(root)
  return out
}

export function isElementVisible(el: HTMLElement): boolean {
  if (el.hidden) return false
  // Use the element's own realm — elements from same-origin iframes must be
  // measured with their own window.
  const win = el.ownerDocument.defaultView ?? window
  const style = win.getComputedStyle(el)
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
    return false
  }
  const rect = el.getBoundingClientRect()
  return rect.width > 0 && rect.height > 0
}

/**
 * Visibility check for native controls that are conventionally hidden under a
 * styled proxy (opacity-0 radios/checkboxes, React-Select's inner input).
 * display:none / visibility:hidden still count as hidden (honeypots, template
 * rows) — but an opacity-0 / zero-size control whose label or parent is
 * visible is judged by its proxy.
 */
export function controlVisible(el: HTMLElement): boolean {
  if (isElementVisible(el)) return true
  const win = el.ownerDocument.defaultView ?? window
  const style = win.getComputedStyle(el)
  if (style.display === 'none' || style.visibility === 'hidden') return false
  const labels = (el as HTMLInputElement).labels
  if (labels) {
    for (const l of Array.from(labels)) if (isElementVisible(l)) return true
  }
  const parent = el.parentElement
  return parent ? isElementVisible(parent) : false
}

/**
 * Stricter variant for TEXT inputs: a hidden-self control only counts when an
 * associated <label> is visible (styled date-pickers hide the native input).
 * Parent visibility alone is NOT enough — that would re-admit honeypots.
 */
export function controlVisibleStrict(el: HTMLElement): boolean {
  if (isElementVisible(el)) return true
  const win = el.ownerDocument.defaultView ?? window
  const style = win.getComputedStyle(el)
  if (style.display === 'none' || style.visibility === 'hidden') return false
  const labels = (el as HTMLInputElement).labels
  if (labels) {
    for (const l of Array.from(labels)) if (isElementVisible(l)) return true
  }
  return false
}

/** parentElement that can climb out of an open shadow root to its host. */
export function shadowParent(el: Element): Element | null {
  if (el.parentElement) return el.parentElement
  const root = el.getRootNode()
  // Duck-typed: ShadowRoot instanceof fails across iframe realms.
  const host = (root as ShadowRoot).host as Element | undefined
  return host ?? null
}

/** Element.contains() that crosses open shadow boundaries. */
export function shadowContains(ancestor: Element, el: Element): boolean {
  let node: Element | null = el
  while (node) {
    if (node === ancestor) return true
    node = shadowParent(node)
  }
  return false
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
