/**
 * In-page floating Gongzuo button + review panel (Simplify-style), rendered in
 * a closed shadow root so page CSS can't restyle it. Vanilla DOM on purpose —
 * pulling React into the content script would add ~140 kB to every page.
 */
import type { FillResult, ScanPreview } from '../lib/messages'

export interface OverlayCallbacks {
  getPreview: () => Promise<ScanPreview>
  onFill: (skipKeys: ReadonlySet<string>) => Promise<FillResult>
  onSaveAnswer: (question: string, answer: string) => Promise<void>
  /** Choices for a question, resolved on demand (may open a custom dropdown). */
  onLoadOptions?: (question: string) => Promise<string[]>
  onOpenOptions: () => void
}

export interface OverlayHandle {
  setCount: (count: number) => void
  destroy: () => void
}

const DISMISS_KEY = 'browser-overlay-dismissed'

const CSS = `
  :host { all: initial; }
  * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  .root { position: fixed; right: 18px; bottom: 18px; z-index: 2147483646; display: flex; flex-direction: column; align-items: flex-end; gap: 10px; }
  .pill {
    display: flex; align-items: center; gap: 8px;
    background: #14161f; color: #e7e9ee;
    border: 1px solid #33384a; border-radius: 999px;
    padding: 8px 14px 8px 9px; cursor: pointer;
    box-shadow: 0 4px 18px rgba(0,0,0,0.35);
    font-size: 13px; font-weight: 600; user-select: none;
  }
  .pill:hover { border-color: #6366f1; }
  .pill__logo { width: 22px; height: 22px; border-radius: 6px; background: #6366f1; display: grid; place-items: center; color: #fff; font-size: 12px; font-weight: 800; }
  .pill__count { background: rgba(99,102,241,0.22); color: #a5b4fc; border-radius: 999px; padding: 1px 8px; font-size: 12px; }
  .pill__x { color: #9aa1b1; margin-left: 2px; font-size: 14px; padding: 0 2px; }
  .pill__x:hover { color: #fff; }
  .panel {
    width: 340px; max-height: min(480px, 70vh); overflow: hidden auto;
    background: #14161f; color: #e7e9ee; border: 1px solid #33384a;
    border-radius: 14px; box-shadow: 0 8px 32px rgba(0,0,0,0.45);
    display: none; flex-direction: column;
  }
  .panel.open { display: flex; }
  .panel__head { display: flex; align-items: center; gap: 8px; padding: 12px 14px; border-bottom: 1px solid #262b3a; position: sticky; top: 0; background: #14161f; }
  .panel__title { font-weight: 700; font-size: 14px; flex: 1; }
  .iconbtn { background: none; border: none; color: #9aa1b1; cursor: pointer; font-size: 14px; padding: 3px 6px; border-radius: 6px; }
  .iconbtn:hover { color: #fff; background: #232838; }
  .panel__body { padding: 8px 14px; display: flex; flex-direction: column; gap: 4px; }
  .sect { color: #9aa1b1; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin: 8px 0 4px; }
  .row { display: flex; align-items: center; gap: 8px; padding: 5px 0; font-size: 13px; }
  .row input[type=checkbox] { accent-color: #6366f1; width: 15px; height: 15px; flex: 0 0 auto; cursor: pointer; }
  .row__label { flex: 1; min-width: 0; }
  .row__name { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .row__value { display: block; color: #9aa1b1; font-size: 11.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .um { padding: 5px 0; font-size: 12.5px; }
  .um__q { color: #cbd0dc; display: block; margin-bottom: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .um__add { background: none; border: none; color: #818cf8; font-size: 12px; cursor: pointer; padding: 0; }
  .um__add:hover { text-decoration: underline; }
  .um textarea { width: 100%; background: #1d2130; color: #e7e9ee; border: 1px solid #33384a; border-radius: 8px; padding: 7px 9px; font-size: 12.5px; min-height: 54px; resize: vertical; margin-top: 4px; }
  .um__optlabel { margin: 6px 0 3px; font-size: 11px; color: #8b91a4; }
  .um__opts { display: flex; flex-wrap: wrap; gap: 4px; max-height: 128px; overflow-y: auto; }
  .um__opt { background: #1d2130; color: #c9cedd; border: 1px solid #33384a; border-radius: 999px; padding: 3px 9px; font: inherit; font-size: 11.5px; cursor: pointer; text-align: left; }
  .um__opt:hover { border-color: #5b63f0; color: #e7e9ee; }
  .um__opt--on { background: #3a41c9; border-color: #5b63f0; color: #fff; }
  .um__save { background: #6366f1; color: #fff; border: none; border-radius: 7px; padding: 5px 12px; font-size: 12px; font-weight: 600; cursor: pointer; margin-top: 4px; }
  .panel__foot { padding: 12px 14px; border-top: 1px solid #262b3a; position: sticky; bottom: 0; background: #14161f; display: flex; gap: 8px; }
  .fillbtn { flex: 1; background: #6366f1; color: #fff; border: none; border-radius: 10px; padding: 10px; font-size: 13.5px; font-weight: 700; cursor: pointer; }
  .fillbtn:hover { background: #818cf8; }
  .fillbtn:disabled { opacity: 0.55; cursor: default; }
  .done { padding: 6px 0 2px; font-size: 13px; }
  .done strong { color: #a5b4fc; }
  .hint { color: #9aa1b1; font-size: 12px; line-height: 1.4; padding: 4px 0; }
  .empty { color: #9aa1b1; font-size: 12.5px; font-style: italic; padding: 6px 0; }
`

function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  cls?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag)
  if (cls) el.className = cls
  if (text !== undefined) el.textContent = text
  return el
}

/** Control types that present a fixed list of choices. */
function isChoice(control: string): boolean {
  return /dropdown|radio|checkbox|select/i.test(control)
}

export function mountOverlay(cb: OverlayCallbacks): OverlayHandle | null {
  try {
    if (sessionStorage.getItem(DISMISS_KEY)) return null
  } catch {
    /* sandboxed page without sessionStorage — still show */
  }

  const host = document.createElement('div')
  host.setAttribute('data-browser-overlay', '')
  const shadow = host.attachShadow({ mode: 'closed' })
  const style = document.createElement('style')
  style.textContent = CSS
  shadow.appendChild(style)

  const root = h('div', 'root')
  shadow.appendChild(root)

  // --- panel ---
  const panel = h('div', 'panel')
  const head = h('div', 'panel__head')
  const title = h('span', 'panel__title', 'Gongzuo autofill')
  const gear = h('button', 'iconbtn', '⚙')
  gear.title = 'Edit profile & settings'
  const collapse = h('button', 'iconbtn', '✕')
  collapse.title = 'Close'
  head.append(title, gear, collapse)

  const body = h('div', 'panel__body')
  const foot = h('div', 'panel__foot')
  const fillBtn = h('button', 'fillbtn', 'Fill fields')
  foot.appendChild(fillBtn)
  panel.append(head, body, foot)

  // --- pill ---
  const pill = h('div', 'pill')
  const logo = h('span', 'pill__logo', 'G')
  const pillText = h('span', undefined, 'Autofill')
  const count = h('span', 'pill__count', '0')
  const dismiss = h('span', 'pill__x', '✕')
  dismiss.title = 'Hide for this site (this tab session)'
  pill.append(logo, pillText, count, dismiss)

  root.append(panel, pill)
  document.documentElement.appendChild(host)

  const skipKeys = new Set<string>()
  let busy = false
  let open = false

  function setCount(n: number) {
    count.textContent = String(n)
    pill.style.display = n > 0 || open ? 'flex' : 'none'
  }

  function renderPreview(preview: ScanPreview) {
    body.textContent = ''
    const fillItems = preview.items.filter((i) => i.status === 'fill')
    const unmatchedItems = preview.items.filter((i) => i.status === 'unmatched' && !i.key)
    // Prune skip keys for fields no longer on the page, so counts can't drift
    // negative and stale keys aren't passed to onFill.
    const live = new Set(fillItems.map((i) => i.key))
    for (const k of Array.from(skipKeys)) if (!live.has(k)) skipKeys.delete(k)
    const remaining = () => fillItems.filter((i) => !skipKeys.has(i.key)).length

    if (fillItems.length === 0) {
      body.appendChild(
        h('p', 'empty', 'No fillable fields matched on this page yet. Scroll the form into view, or add more profile details.'),
      )
    } else {
      body.appendChild(h('div', 'sect', `Will fill (${fillItems.length})`))
      for (const item of fillItems) {
        const row = h('label', 'row')
        const check = document.createElement('input')
        check.type = 'checkbox'
        check.checked = !skipKeys.has(item.key)
        check.addEventListener('change', () => {
          if (check.checked) skipKeys.delete(item.key)
          else skipKeys.add(item.key)
          updateFillLabel(remaining())
        })
        const label = h('span', 'row__label')
        label.append(
          h('span', 'row__name', item.label),
          h('span', 'row__value', item.value.length > 60 ? item.value.slice(0, 60) + '…' : item.value),
        )
        row.append(check, label)
        body.appendChild(row)
      }
    }

    if (unmatchedItems.length > 0) {
      body.appendChild(h('div', 'sect', 'Unanswered questions'))
      body.appendChild(
        h('p', 'hint', 'Save an answer once and Gongzuo will reuse it whenever a similar question appears.'),
      )
      for (const item of unmatchedItems.slice(0, 8)) {
        const q = item.displayLabel
        let opts = item.options ?? []
        const wrap = h('div', 'um')
        wrap.appendChild(h('span', 'um__q', q))
        const add = h('button', 'um__add', '+ Save an answer')
        wrap.appendChild(add)
        add.addEventListener('click', async () => {
          add.remove()
          const ta = document.createElement('textarea')
          ta.placeholder = opts.length ? 'Pick an option above, or type your own…' : 'Your answer…'
          const save = h('button', 'um__save', 'Save & refill')

          // A choice control whose menu only exists while open (react-select on
          // Greenhouse/Lever) has no options from the scan — fetch them now
          // that the person has asked to answer this specific field.
          if (!opts.length && isChoice(item.control) && cb.onLoadOptions) {
            const loading = h('p', 'um__optlabel', 'Reading the options…')
            wrap.appendChild(loading)
            try {
              opts = await cb.onLoadOptions(q)
            } catch {
              opts = []
            }
            loading.remove()
            if (opts.length) ta.placeholder = 'Pick an option above, or type your own…'
          }

          if (opts.length) {
            // This field is a dropdown/radio, so show what it actually accepts.
            // Clicking a chip writes its exact wording into the box; a second
            // click removes it. Multiple picks join with " | ", which the
            // matcher already treats as ordered alternatives — handy when the
            // same question is worded differently on other sites.
            wrap.appendChild(h('p', 'um__optlabel', `Options on this ${item.control || 'field'}`))
            const chips = h('div', 'um__opts')
            const parts = () => ta.value.split('|').map((p) => p.trim()).filter(Boolean)
            const sync = () => {
              const chosen = new Set(parts().map((p) => p.toLowerCase()))
              for (const el of Array.from(chips.children)) {
                const on = chosen.has((el.textContent ?? '').trim().toLowerCase())
                el.classList.toggle('um__opt--on', on)
              }
            }
            for (const opt of opts) {
              const chip = h('button', 'um__opt', opt)
              chip.addEventListener('click', () => {
                const current = parts()
                const idx = current.findIndex((p) => p.toLowerCase() === opt.toLowerCase())
                if (idx >= 0) current.splice(idx, 1)
                else current.push(opt)
                ta.value = current.join(' | ')
                sync()
                ta.focus()
              })
              chips.appendChild(chip)
            }
            wrap.appendChild(chips)
            ta.addEventListener('input', sync)
            wrap.append(ta, save)
            sync()
          } else {
            wrap.append(ta, save)
          }

          ta.focus()
          save.addEventListener('click', async () => {
            const answer = ta.value.trim()
            if (!answer) return
            save.disabled = true
            await cb.onSaveAnswer(q, answer)
            await refresh()
          })
        })
        body.appendChild(wrap)
      }
    }
    updateFillLabel(remaining())
  }

  function updateFillLabel(n: number) {
    fillBtn.textContent = n > 0 ? `Fill ${n} ${n === 1 ? 'field' : 'fields'}` : 'Nothing to fill'
    fillBtn.disabled = n <= 0 || busy
  }

  function renderResult(result: FillResult) {
    const done = h('div', 'done')
    const strong = h('strong', undefined, String(result.filled))
    done.append('Filled ', strong, ` ${result.filled === 1 ? 'field' : 'fields'}`)
    if (result.skipped > 0) done.append(` · ${result.skipped} skipped`)
    body.prepend(done)
  }

  async function refresh() {
    const preview = await cb.getPreview()
    renderPreview(preview)
    setCount(preview.items.filter((i) => i.status === 'fill').length)
  }

  pill.addEventListener('click', async (e) => {
    if (e.target === dismiss) return
    open = !open
    panel.classList.toggle('open', open)
    if (open) await refresh()
  })
  dismiss.addEventListener('click', (e) => {
    e.stopPropagation()
    try {
      sessionStorage.setItem(DISMISS_KEY, '1')
    } catch {
      /* ignore */
    }
    handle.destroy()
  })
  collapse.addEventListener('click', () => {
    open = false
    panel.classList.remove('open')
  })
  gear.addEventListener('click', () => cb.onOpenOptions())

  fillBtn.addEventListener('click', async () => {
    if (busy) return
    busy = true
    fillBtn.textContent = 'Filling…'
    fillBtn.disabled = true
    try {
      const result = await cb.onFill(skipKeys)
      busy = false
      await refresh() // recomputes the remaining count + re-enables the button
      renderResult(result)
    } catch {
      busy = false
      fillBtn.disabled = false
      fillBtn.textContent = 'Fill failed — retry'
    }
  })

  const handle: OverlayHandle = {
    setCount,
    destroy() {
      host.remove()
    },
  }
  setCount(0)
  return handle
}
