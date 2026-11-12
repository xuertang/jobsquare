import { execFile } from "node:child_process";
import { existsSync, readdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";

import {
  autopilotCandidates,
  markEntry,
  parsePending,
  type MarkAction,
  type PendingEntry,
} from "./pipeline.js";
import { applyUrl, DEFAULT_CHROME, loadProfile, openAndFill } from "./fill.js";

/**
 * JobOps Pipeline — lets the OpenClaw agent work the jobsquare application
 * queue (apps/job-ops/data/pipeline.md, "## Pending"):
 *
 *   jobops_pending  → what's waiting, filtered/sorted by eval score
 *   jobops_report   → the eval report behind an entry's #NNN
 *   jobops_prepare  → build the application kit (one-page tailored CV PDF /
 *                     match report / interview prep) via the repo's agent CLI
 *   jobops_fill     → open the posting in a visible managed Chrome and fill
 *                     the form from the local apply profile (extension engine)
 *   jobops_mark     → tick + annotate an entry after the human applied/skipped
 *
 * Boundary: jobops_fill fills and STOPS. Nothing here clicks submit, solves
 * CAPTCHAs, logs in, or answers legal/EEO questions the profile doesn't
 * already answer. The filled window stays open for the human to review and
 * submit themselves.
 */

interface JobopsConfig {
  repoRoot?: string;
  python?: string;
  prepareTimeoutMs?: number;
  profilePath?: string;
  chromePath?: string;
  chromeProfileDir?: string;
  cdpPort?: number;
}

function repoRootFrom(config: JobopsConfig): string {
  if (config.repoRoot) {
    if (!existsSync(pipelinePath(config.repoRoot))) {
      throw new Error(
        `jobops: repoRoot "${config.repoRoot}" has no apps/job-ops/data/pipeline.md`,
      );
    }
    return config.repoRoot;
  }
  // Self-locate: works when the plugin runs from its in-repo checkout.
  let dir = path.dirname(fileURLToPath(import.meta.url));
  for (let i = 0; i < 8; i++) {
    if (existsSync(pipelinePath(dir))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error(
    "jobops: can't find the jobsquare checkout — set plugin config { repoRoot }",
  );
}

const pipelinePath = (root: string) => path.join(root, "apps", "job-ops", "data", "pipeline.md");
const reportsDir = (root: string) => path.join(root, "apps", "job-ops", "reports");
const agentPy = (root: string) => path.join(root, "apps", "job-ops", "agent.py");

function pythonFrom(config: JobopsConfig, root: string): string {
  if (config.python) return config.python;
  const venv = path.join(root, ".venv", "bin", "python");
  return existsSync(venv) ? venv : "python3";
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function readPending(root: string): PendingEntry[] {
  return parsePending(readFileSync(pipelinePath(root), "utf8"));
}

/** Compact wire form — keep the model-visible payload small. */
function wire(e: PendingEntry) {
  return {
    report: e.report,
    company: e.company,
    role: e.role,
    location: e.location,
    score: e.score,
    url: e.url,
    first_seen: e.firstSeen,
    ...(e.comp ? { comp: e.comp } : {}),
    ...(e.ticked ? { ticked: true } : {}),
    ...(e.annotations.length ? { annotations: e.annotations } : {}),
  };
}

const configSchema = Type.Object({
  repoRoot: Type.Optional(
    Type.String({ description: "Absolute path to the jobsquare checkout." }),
  ),
  python: Type.Optional(
    Type.String({ description: "Python interpreter for agent.py (default: {repoRoot}/.venv/bin/python)." }),
  ),
  prepareTimeoutMs: Type.Optional(
    Type.Number({ description: "Timeout for jobops_prepare runs (default 900000 = 15 min)." }),
  ),
  profilePath: Type.Optional(
    Type.String({
      description:
        "Apply-profile JSON for jobops_fill (default {repoRoot}/apps/job-ops/config/apply-profile.json).",
    }),
  ),
  chromePath: Type.Optional(
    Type.String({ description: "Chrome binary for jobops_fill (default the macOS app path)." }),
  ),
  chromeProfileDir: Type.Optional(
    Type.String({
      description:
        "Dedicated Chrome user-data-dir for fills (default ~/.openclaw/jobops-chrome). ATS logins persist here.",
    }),
  ),
  cdpPort: Type.Optional(
    Type.Number({ description: "DevTools port for the managed Chrome (default 18999)." }),
  ),
});

export default defineToolPlugin({
  id: "jobops",
  name: "JobOps Pipeline",
  description:
    "Work the jobsquare application queue: list pending roles, read eval reports, prepare tailored CV kits, and record applied/skipped status. Never fills or submits applications.",
  configSchema,
  tools: (tool) => [
    tool({
      name: "jobops_pending",
      label: "Pending positions",
      description:
        "List positions waiting in pipeline.md Pending, best score first. Untackled entries only unless include_done.",
      parameters: Type.Object({
        min_score: Type.Optional(
          Type.Number({ description: "Only entries with eval score >= this (e.g. 4.0)." }),
        ),
        company: Type.Optional(
          Type.String({ description: "Filter to one company slug, e.g. 'netflix'." }),
        ),
        limit: Type.Optional(Type.Number({ description: "Max entries to return (default 15)." })),
        include_done: Type.Optional(
          Type.Boolean({ description: "Also include already-ticked entries." }),
        ),
      }),
      execute: async (params, config) => {
        const root = repoRootFrom(config);
        let entries = readPending(root);
        const total = entries.length;
        if (!params.include_done) entries = entries.filter((e) => !e.ticked);
        if (params.company) {
          const want = params.company.toLowerCase();
          entries = entries.filter((e) => e.company.toLowerCase().includes(want));
        }
        if (params.min_score !== undefined) {
          entries = entries.filter((e) => e.score !== null && e.score >= params.min_score!);
        }
        entries.sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
        const limit = params.limit ?? 15;
        return {
          pending_total: total,
          matching: entries.length,
          shown: Math.min(limit, entries.length),
          entries: entries.slice(0, limit).map(wire),
        };
      },
    }),

    tool({
      name: "jobops_report",
      label: "Eval report",
      description:
        "Read the evaluation report behind a Pending entry's #NNN (rubric scores, gaps, verdict, comp).",
      parameters: Type.Object({
        report: Type.Number({ description: "Report id, the NNN from #NNN." }),
      }),
      execute: async ({ report }, config) => {
        const root = repoRootFrom(config);
        const dir = reportsDir(root);
        if (!existsSync(dir)) return `No reports directory at ${dir}.`;
        const prefix = new RegExp(`^0*${report}-`);
        const file = readdirSync(dir).find((f) => prefix.test(f));
        if (!file) return `No report file found for #${report} in ${dir}.`;
        const full = path.join(dir, file);
        const text = readFileSync(full, "utf8");
        const cap = 48_000;
        return text.length > cap
          ? `${text.slice(0, cap)}\n\n[truncated — full report: ${full}]`
          : text;
      },
    }),

    tool({
      name: "jobops_prepare",
      label: "Prepare application kit",
      description:
        "Run the repo's headless agent for one Pending entry: mode 'pdf' builds the tailored one-page CV PDF, 'match' re-scores against the CV, 'interview-prep' builds the interview intel doc. Slow (minutes) — it drives a full Claude session.",
      optional: true,
      parameters: Type.Object({
        report: Type.Number({ description: "Pending entry's report id (#NNN)." }),
        mode: Type.Optional(
          Type.Union([Type.Literal("pdf"), Type.Literal("match"), Type.Literal("interview-prep")], {
            description: "What to prepare (default pdf).",
          }),
        ),
      }),
      execute: async ({ report, mode }, config, context) => {
        const root = repoRootFrom(config);
        const entry = readPending(root).find((e) => e.report === report);
        if (!entry) return `No Pending entry with report #${report}.`;
        const outputDir = path.join(root, "apps", "job-ops", "output");
        const before = new Set(existsSync(outputDir) ? readdirSync(outputDir) : []);

        const args = [agentPy(root), mode ?? "pdf", entry.url];
        const { code, out } = await run(pythonFrom(config, root), args, {
          cwd: root,
          timeoutMs: config.prepareTimeoutMs ?? 900_000,
          signal: context.signal,
        });

        const produced = (existsSync(outputDir) ? readdirSync(outputDir) : [])
          .filter((f) => !before.has(f))
          .map((f) => path.join(outputDir, f));
        return {
          report,
          company: entry.company,
          role: entry.role,
          mode: mode ?? "pdf",
          exit_code: code,
          new_files: produced,
          log_tail: out.split("\n").slice(-25).join("\n"),
        };
      },
    }),

    tool({
      name: "jobops_fill",
      label: "Fill application form",
      description:
        "Open a Pending entry's posting in a visible managed Chrome and fill the application form from the local apply profile — same engine as the browser extension. Fills only; the window stays open for the human to review and SUBMIT THEMSELVES. Never solves CAPTCHAs or logs in (log in once in the managed window; the session persists). Report which fields were filled/skipped/unmatched.",
      optional: true,
      parameters: Type.Object({
        report: Type.Optional(
          Type.Number({ description: "Pending entry's report id (#NNN). Preferred." }),
        ),
        url: Type.Optional(
          Type.String({ description: "Direct application URL, when the entry's posting URL isn't the form page." }),
        ),
        overwrite_existing: Type.Optional(
          Type.Boolean({ description: "Refill fields that already have values (default false)." }),
        ),
        fill_eeo: Type.Optional(
          Type.Boolean({ description: "Fill voluntary EEO/demographic questions from the profile (default true)." }),
        ),
        fill_salary: Type.Optional(
          Type.Boolean({ description: "Fill desired-salary questions (default true)." }),
        ),
      }),
      execute: async (params, config) => {
        const root = repoRootFrom(config);
        let url = params.url;
        let entry: PendingEntry | undefined;
        if (!url) {
          if (params.report === undefined) {
            return "Pass report (#NNN) or url.";
          }
          entry = readPending(root).find((e) => e.report === params.report);
          if (!entry) return `No Pending entry with report #${params.report}.`;
          url = applyUrl(entry.url);
        }

        const bundlePath = path.join(path.dirname(fileURLToPath(import.meta.url)), "fill-bundle.js");
        if (!existsSync(bundlePath)) {
          return `Fill bundle missing at ${bundlePath} — run \`npm run plugin:build\` in the plugin directory.`;
        }
        const { profile, warnings } = loadProfile(
          config.profilePath ?? path.join(root, "apps", "job-ops", "config", "apply-profile.json"),
        );
        const settings = {
          overwriteExisting: params.overwrite_existing ?? false,
          fillEEO: params.fill_eeo ?? true,
          fillDisability: params.fill_eeo ?? true,
          fillSalary: params.fill_salary ?? true,
          attachFiles: true,
        };
        const result = await openAndFill(url, readFileSync(bundlePath, "utf8"), profile, settings, {
          chromePath: config.chromePath ?? DEFAULT_CHROME,
          userDataDir:
            config.chromeProfileDir ??
            path.join(process.env.HOME ?? "~", ".openclaw", "jobops-chrome"),
          cdpPort: config.cdpPort ?? 18999,
        });
        return {
          ...(entry ? { report: entry.report, company: entry.company, role: entry.role } : {}),
          ...result,
          ...(warnings.length ? { warnings } : {}),
          reports: undefined, // per-frame detail is noise for the model; totals + rows cover it
          rows: result.reports.flatMap((r) => r.rows).slice(0, 80),
          next_step:
            result.totals.filled > 0
              ? "Form filled — the Chrome window is open for the human to review and submit. After they confirm, use jobops_mark."
              : "Nothing filled — the page may need a login in the managed Chrome window, or it isn't the application form (pass url pointing at the form).",
        };
      },
    }),

    tool({
      name: "jobops_autopilot",
      label: "Autopilot: scan, evaluate, fill, park",
      description:
        "Unattended pipeline pass: refresh listings, triage new ones into the queue, evaluate them, then fill the top-scoring applications and PARK them for human review. Submits NOTHING — each filled form waits in the managed Chrome window. Returns a digest of what is ready to submit. Slow (tens of minutes); intended for scheduled runs.",
      optional: true,
      parameters: Type.Object({
        min_score: Type.Optional(
          Type.Number({ description: "Only fill entries scoring >= this (default 4.0)." }),
        ),
        max_fills: Type.Optional(
          Type.Number({ description: "Cap on forms filled per run (default 3)." }),
        ),
        evaluate: Type.Optional(
          Type.Number({ description: "How many newly queued entries to evaluate (default 10, 0 = skip)." }),
        ),
        scrape: Type.Optional(
          Type.Boolean({ description: "Refresh listings from job boards first (default true)." }),
        ),
      }),
      execute: async (params, config) => {
        const root = repoRootFrom(config);
        const py = pythonFrom(config, root);
        const file = pipelinePath(root);
        const steps: { step: string; exit_code: number; log_tail: string }[] = [];
        const runStep = async (step: string, args: string[], timeoutMs: number) => {
          const { code, out } = await run(py, args, { cwd: root, timeoutMs });
          steps.push({ step, exit_code: code, log_tail: out.split("\n").slice(-6).join("\n") });
          return code;
        };

        // 1-3. Refresh → triage → evaluate. Each is an existing headless entry
        // point; a failure is reported but never blocks the rest.
        if (params.scrape !== false) {
          await runStep("scrape", [path.join(root, "apps", "job-ops", "cli.py"),
            "--config", path.join(root, "apps", "job-ops", "sources.yaml")], 900_000);
        }
        await runStep("scan", [agentPy(root), "scan"], 1_800_000);
        const evaluate = params.evaluate ?? 10;
        if (evaluate > 0) {
          await runStep("evaluate", [agentPy(root), "pipeline", String(evaluate)], 3_600_000);
        }

        // 4. Fill the top scorers that haven't been filled yet.
        const minScore = params.min_score ?? 4.0;
        const maxFills = params.max_fills ?? 3;
        const candidates = autopilotCandidates(readFileSync(file, "utf8"), minScore).slice(0, maxFills);

        const bundlePath = path.join(path.dirname(fileURLToPath(import.meta.url)), "fill-bundle.js");
        const bundle = existsSync(bundlePath) ? readFileSync(bundlePath, "utf8") : null;
        const { profile, warnings } = loadProfile(
          config.profilePath ?? path.join(root, "apps", "job-ops", "config", "apply-profile.json"),
        );
        const chrome = {
          chromePath: config.chromePath ?? DEFAULT_CHROME,
          userDataDir:
            config.chromeProfileDir ?? path.join(process.env.HOME ?? "~", ".openclaw", "jobops-chrome"),
          cdpPort: config.cdpPort ?? 18999,
        };
        const settings = {
          overwriteExisting: false,
          fillEEO: true,
          fillDisability: true,
          fillSalary: true,
          attachFiles: true,
        };

        const ready: unknown[] = [];
        for (const entry of candidates) {
          if (!bundle) break;
          try {
            // Fills run one at a time: a single Chrome, and open dropdown
            // menus on two pages interfere with each other.
            const res = await openAndFill(applyUrl(entry.url), bundle, profile, settings, chrome);
            if (res.totals.filled > 0 && entry.report !== null) {
              const marked = markEntry(readFileSync(file, "utf8"), entry.report, "filled", today(),
                `${res.totals.filled} fields`);
              if (marked.changed && marked.content !== undefined) {
                const tmp = `${file}.jobops-${process.pid}.tmp`;
                writeFileSync(tmp, marked.content, "utf8");
                renameSync(tmp, file);
              }
            }
            ready.push({
              report: entry.report, company: entry.company, role: entry.role, score: entry.score,
              url: res.page_url, filled: res.totals.filled, needs_answer: res.unmatched.slice(0, 8),
            });
          } catch (e) {
            ready.push({
              report: entry.report, company: entry.company, role: entry.role,
              error: e instanceof Error ? e.message : String(e),
            });
          }
        }

        const open = autopilotCandidates(readFileSync(file, "utf8"), minScore).length;
        return {
          steps,
          ...(warnings.length ? { profile_warnings: warnings } : {}),
          filled_and_parked: ready,
          still_unfilled_above_threshold: open,
          submitted: 0,
          human_action_required:
            ready.length > 0
              ? `${ready.length} application(s) are filled and waiting in the Chrome window. Nothing was submitted. Review each, answer any 'needs_answer' questions, then submit yourself — and tell me so I can mark them applied.`
              : "Nothing new to fill this run.",
        };
      },
    }),

    tool({
      name: "jobops_mark",
      label: "Mark pipeline entry",
      description:
        "Record the human's outcome on a Pending entry: tick it and append '| applied {date}' / '| skipped {date}' / '| done {date}'. Use ONLY after the person confirms they handled it.",
      parameters: Type.Object({
        report: Type.Number({ description: "Pending entry's report id (#NNN)." }),
        action: Type.Union(
          [Type.Literal("applied"), Type.Literal("skipped"), Type.Literal("done")],
          { description: "What happened." },
        ),
        note: Type.Optional(
          Type.String({ description: "Short reason/context, e.g. 'via referral' or 'comp too low'." }),
        ),
      }),
      execute: async ({ report, action, note }, config) => {
        const root = repoRootFrom(config);
        const file = pipelinePath(root);
        const result = markEntry(readFileSync(file, "utf8"), report, action as MarkAction, today(), note);
        if (!result.changed || result.content === undefined) {
          return { changed: false, reason: result.reason, entry: result.entry && wire(result.entry) };
        }
        // Atomic same-dir replace so a concurrent reader never sees a torn file.
        const tmp = `${file}.jobops-${process.pid}.tmp`;
        writeFileSync(tmp, result.content, "utf8");
        renameSync(tmp, file);
        return { changed: true, line: result.updatedLine, entry: result.entry && wire(result.entry) };
      },
    }),
  ],
});

function run(
  cmd: string,
  args: string[],
  opts: { cwd: string; timeoutMs: number; signal?: AbortSignal },
): Promise<{ code: number; out: string }> {
  return new Promise((resolve, reject) => {
    const child = execFile(
      cmd,
      args,
      {
        cwd: opts.cwd,
        timeout: opts.timeoutMs,
        maxBuffer: 8 * 1024 * 1024,
        signal: opts.signal,
        env: { ...process.env },
      },
      (error, stdout, stderr) => {
        const out = [stdout, stderr].filter(Boolean).join("\n");
        if (error && (error as NodeJS.ErrnoException).code === "ENOENT") {
          reject(new Error(`jobops: interpreter not found: ${cmd}`));
          return;
        }
        resolve({ code: child.exitCode ?? (error ? 1 : 0), out });
      },
    );
  });
}
