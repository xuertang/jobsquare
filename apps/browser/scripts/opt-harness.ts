/**
 * Verifies fieldOptions() against a live form: for every unmatched choice
 * field, report the options the answer editor would offer.
 */
import { collectFields, fieldOptions } from '../src/lib/collect'
import { createEntryIndexer, matchContext, matchFileContext } from '../src/lib/fieldMatcher'
import { contextFor } from '../src/lib/filler'
import { emptyProfile, type Profile } from '../src/lib/profile'

function probe() {
  const profile: Profile = { ...emptyProfile(), firstName: 'Alex', lastName: 'Rivera', email: 'a@b.c' }
  const indexer = createEntryIndexer()
  const rows: unknown[] = []
  for (const field of collectFields(document)) {
    if (field.type === 'file') continue
    const ctx = contextFor(field)
    const m = matchContext(ctx, profile, [], { entryIndex: indexer.next })
    if (m) continue // matched fields don't show the answer editor
    const opts = fieldOptions(field)
    rows.push({ control: field.type, q: ctx.displayLabel.slice(0, 54), n: opts.length, options: opts.slice(0, 6) })
  }
  return { url: location.href, unmatched: rows.length, withOptions: rows.filter((r: any) => r.n > 0).length, rows }
}
;(window as unknown as { __gzOpts?: typeof probe }).__gzOpts = probe
