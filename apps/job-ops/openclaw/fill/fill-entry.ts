/**
 * Page-side fill bundle for the jobops OpenClaw plugin.
 *
 * Built with esbuild into dist/fill-bundle.js and injected per-frame over CDP.
 * Reuses the browser extension's real engine (apps/browser/src/lib) — same
 * field collection, matching, synonym expansion, widget driving — minus
 * everything chrome.*: no storage, no overlay, no tracking.
 *
 * Exposes:
 *   window.__jobopsEligible(topHost?) → may THIS frame receive profile data?
 *   window.__jobopsFill(profile, settings) → fill report
 *
 * It fills; it NEVER clicks submit, never solves CAPTCHAs, never logs in.
 */
import { collectFields, hostAllowed } from '../../../browser/src/lib/collect'
import {
  createEntryIndexer,
  matchContext,
  matchFileContext,
  type SpecCategory,
} from '../../../browser/src/lib/fieldMatcher'
import {
  applyMatch,
  attachFile,
  contextFor,
  hasExistingValue,
  type Fillable,
} from '../../../browser/src/lib/filler'
import { fillWidget, widgetHasValue } from '../../../browser/src/lib/widgetFiller'
import type { Profile } from '../../../browser/src/lib/profile'

interface FillSettings {
  overwriteExisting: boolean
  fillEEO: boolean
  fillDisability: boolean
  fillSalary: boolean
  attachFiles: boolean
}

interface FillRow {
  control: string
  label: string
  key: string
  value: string
  status: 'filled' | 'skipped' | 'failed' | 'unmatched' | 'no-document'
}

interface FillReport {
  frame: string
  detected: number
  filled: number
  skipped: number
  failed: number
  unmatched: string[]
  rows: FillRow[]
}

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

function disabledCategories(settings: FillSettings): Set<SpecCategory> {
  const off = new Set<SpecCategory>()
  if (!settings.fillEEO) off.add('eeo')
  if (!settings.fillDisability) off.add('disability')
  if (!settings.fillSalary) off.add('salary')
  return off
}

async function fill(profile: Profile, settings: FillSettings): Promise<FillReport> {
  const fields = collectFields(document)
  const disabled = disabledCategories(settings)
  const indexer = createEntryIndexer()
  const report: FillReport = {
    frame: location.href,
    detected: fields.length,
    filled: 0,
    skipped: 0,
    failed: 0,
    unmatched: [],
    rows: [],
  }
  const row = (r: FillRow) => {
    if (report.rows.length < 200) report.rows.push(r)
  }

  for (const field of fields) {
    const ctx = contextFor(field)
    const control = controlName(field)

    if (field.type === 'file') {
      const slot = matchFileContext(ctx)
      if (!slot) {
        if (ctx.displayLabel.length > 6) report.unmatched.push(ctx.displayLabel)
        continue
      }
      const stored = profile[slot]
      const label = slot === 'resume' ? 'Resume' : 'Cover letter file'
      if (!stored) {
        row({ control, label, key: `file:${slot}`, value: '', status: 'no-document' })
        continue
      }
      if (!settings.attachFiles || (hasExistingValue(field) && !settings.overwriteExisting)) {
        report.skipped++
        row({ control, label, key: `file:${slot}`, value: stored.name, status: 'skipped' })
        continue
      }
      if (attachFile(field.el, stored)) {
        report.filled++
        row({ control, label, key: `file:${slot}`, value: stored.name, status: 'filled' })
      } else {
        report.failed++
        row({ control, label, key: `file:${slot}`, value: stored.name, status: 'failed' })
      }
      continue
    }

    const match = matchContext(ctx, profile, profile.customAnswers, {
      disabledCategories: disabled,
      entryIndex: indexer.next,
    })
    if (!match) {
      if (ctx.displayLabel.length > 6) report.unmatched.push(ctx.displayLabel)
      continue
    }

    const existing = field.type === 'widget' ? widgetHasValue(field.el) : hasExistingValue(field)
    if (existing && !settings.overwriteExisting) {
      report.skipped++
      row({ control, label: match.label, key: match.key, value: match.value.slice(0, 60), status: 'skipped' })
      continue
    }

    let ok: boolean
    if (field.type === 'widget') {
      // Widgets fill sequentially — two open menus interfere with each other.
      const outcome = await fillWidget(field.el, match)
      ok = outcome === 'filled'
      if (outcome === 'no-options' && field.el.localName === 'input') {
        ok = applyMatch({ type: 'value', el: field.el as HTMLInputElement }, match)
      }
    } else {
      ok = applyMatch(field, match)
    }

    if (ok) report.filled++
    else report.failed++
    row({
      control,
      label: match.label,
      key: match.key,
      value: match.value.slice(0, 60),
      status: ok ? 'filled' : 'failed',
    })
  }

  report.unmatched = [...new Set(report.unmatched)].slice(0, 20)
  return report
}

declare global {
  interface Window {
    __jobopsEligible?: (topHost?: string) => boolean
    __jobopsFill?: (profile: Profile, settings: FillSettings) => Promise<FillReport>
  }
}

window.__jobopsEligible = (topHost?: string) =>
  window === window.top || hostAllowed(location.hostname, topHost)
window.__jobopsFill = fill
