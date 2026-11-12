/**
 * Pure pipeline.md logic — parsing the Pending section and line-anchored
 * status marking. No SDK imports so tests can exercise it directly.
 *
 * Entry contract (apps/job-ops/modes/_shared.md):
 *   - [ ] {url} | {company} | {role} | {location} | first_seen {date}
 *         [| {comp}] | eval {F}/5 {date} #{NNN} [| {annotation…}]
 * Tick tolerance: any bracket containing x counts as ticked ("[x ]", "[ X]").
 */

export interface PendingEntry {
  /** 0-based line index in the file — the anchor for edits. */
  line: number;
  ticked: boolean;
  url: string;
  company: string;
  role: string;
  location: string;
  firstSeen: string;
  /** Salary segment verbatim, e.g. "$200K – $287.5K", or "". */
  comp: string;
  /** eval score out of 5, null when the entry was never evaluated. */
  score: number | null;
  evalDate: string;
  /** Report id NNN (the #NNN suffix), null when not evaluated. */
  report: number | null;
  /** Trailing segments after eval — "done 2026-08-06", "applied …", notes. */
  annotations: string[];
  raw: string;
}

const TICK_RE = /^- \[([^\]]*)\]\s*/;
const EVAL_RE = /^eval ([0-9.]+)\/5 (\S+) #(\d+)$/;
const FIRST_SEEN_RE = /^first_seen (.+)$/;
const COMP_RE = /[$€£]|\b\d+(?:\.\d+)?K\b/;

/** [startLine, endLineExclusive] of the "## Pending" section body. */
export function pendingBounds(lines: string[]): [number, number] {
  const start = lines.findIndex((l) => /^##\s+Pending\s*$/.test(l));
  if (start === -1) return [-1, -1];
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    if (/^##\s/.test(lines[i])) {
      end = i;
      break;
    }
  }
  return [start + 1, end];
}

export function parsePending(content: string): PendingEntry[] {
  const lines = content.split("\n");
  const [start, end] = pendingBounds(lines);
  if (start === -1) return [];
  const out: PendingEntry[] = [];
  for (let i = start; i < end; i++) {
    const entry = parseEntryLine(lines[i], i);
    if (entry) out.push(entry);
  }
  return out;
}

export function parseEntryLine(line: string, lineNo: number): PendingEntry | null {
  const tick = TICK_RE.exec(line);
  if (!tick) return null;
  const segments = line.slice(tick[0].length).split(" | ").map((s) => s.trim());
  if (segments.length < 3) return null;

  const [url, company, role, location = ""] = segments;
  const entry: PendingEntry = {
    line: lineNo,
    ticked: tick[1].toLowerCase().includes("x"),
    url,
    company,
    role,
    location,
    firstSeen: "",
    comp: "",
    score: null,
    evalDate: "",
    report: null,
    annotations: [],
    raw: line,
  };

  let sawEval = false;
  for (const seg of segments.slice(4)) {
    const fs = FIRST_SEEN_RE.exec(seg);
    if (fs) {
      entry.firstSeen = fs[1];
      continue;
    }
    const ev = EVAL_RE.exec(seg);
    if (ev) {
      entry.score = Number(ev[1]);
      entry.evalDate = ev[2];
      entry.report = Number(ev[3]);
      sawEval = true;
      continue;
    }
    if (!sawEval && !entry.comp && COMP_RE.test(seg)) {
      entry.comp = seg;
      continue;
    }
    entry.annotations.push(seg);
  }
  return entry;
}

/**
 * Terminal actions tick the entry; "filled" is deliberately NON-terminal —
 * the form is filled and parked, but nothing was submitted, so the entry
 * stays open work until the human says otherwise.
 */
export type MarkAction = "applied" | "skipped" | "done" | "filled";

const NON_TICKING: ReadonlySet<MarkAction> = new Set(["filled"]);

/** Open, scored at/above `minScore`, and not already filled+parked. */
export function autopilotCandidates(content: string, minScore: number): PendingEntry[] {
  return parsePending(content)
    .filter((e) => !e.ticked)
    .filter((e) => e.score !== null && e.score >= minScore)
    .filter((e) => !e.annotations.some((a) => a.startsWith("filled")))
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
}

export interface MarkResult {
  changed: boolean;
  reason?: string;
  entry?: PendingEntry;
  updatedLine?: string;
  content?: string;
}

/**
 * Annotate an entry (found by report id) in the Pending section with
 * " | {action} {date}[ — {note}]", ticking it for terminal actions only.
 * Line-anchored, Pending-scoped, idempotent: an entry already carrying this
 * action is left untouched.
 */
export function markEntry(
  content: string,
  report: number,
  action: MarkAction,
  date: string,
  note?: string,
): MarkResult {
  const lines = content.split("\n");
  const [start, end] = pendingBounds(lines);
  if (start === -1) return { changed: false, reason: "no ## Pending section found" };

  for (let i = start; i < end; i++) {
    const entry = parseEntryLine(lines[i], i);
    if (!entry || entry.report !== report) continue;
    if (entry.annotations.some((a) => a.startsWith(action))) {
      return { changed: false, reason: `already marked "${action}"`, entry };
    }
    let line = NON_TICKING.has(action) ? lines[i] : lines[i].replace(TICK_RE, "- [x] ");
    line += ` | ${action} ${date}${note ? ` — ${note}` : ""}`;
    lines[i] = line;
    const updated = lines.join("\n");
    return {
      changed: true,
      entry: parseEntryLine(line, i) ?? entry,
      updatedLine: line,
      content: updated,
    };
  }
  return { changed: false, reason: `no Pending entry with report #${report}` };
}
