/**
 * Node side of jobops_fill: drive a real, VISIBLE Chrome over CDP, inject the
 * fill bundle into eligible frames, run the fill, and leave the window open
 * for the human to review and submit.
 *
 * Chrome runs detached with its own user-data-dir (never the person's main
 * profile — Chrome refuses a debug port on it anyway). ATS logins done in
 * that window persist across runs.
 */
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { chromium, type Browser, type Frame, type Page } from "playwright-core";

export interface ChromeOptions {
  chromePath: string;
  userDataDir: string;
  cdpPort: number;
}

export const DEFAULT_CHROME =
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

async function cdpUp(port: number): Promise<boolean> {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/json/version`, {
      signal: AbortSignal.timeout(1_000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function ensureChrome(opts: ChromeOptions): Promise<void> {
  if (await cdpUp(opts.cdpPort)) return;
  if (!existsSync(opts.chromePath)) {
    throw new Error(`jobops: Chrome not found at ${opts.chromePath} — set plugin config { chromePath }`);
  }
  mkdirSync(opts.userDataDir, { recursive: true });
  const child = spawn(
    opts.chromePath,
    [
      `--remote-debugging-port=${opts.cdpPort}`,
      `--user-data-dir=${opts.userDataDir}`,
      "--no-first-run",
      "--no-default-browser-check",
      "about:blank",
    ],
    { detached: true, stdio: "ignore" },
  );
  child.unref();
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (await cdpUp(opts.cdpPort)) return;
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error("jobops: Chrome started but its debug port never came up");
}

/** Shape of the page-side globals installed by dist/fill-bundle.js. */
type JobopsGlobals = {
  __jobopsEligible?: (topHost?: string) => boolean;
  __jobopsFill?: (profile: unknown, settings: unknown) => Promise<FrameFillReport>;
};

export interface FrameFillReport {
  frame: string;
  detected: number;
  filled: number;
  skipped: number;
  failed: number;
  unmatched: string[];
  rows: unknown[];
}

export interface FillRunResult {
  page_url: string;
  page_title: string;
  frames_filled: number;
  frames_skipped_pii_gate: number;
  totals: { detected: number; filled: number; skipped: number; failed: number };
  unmatched: string[];
  reports: FrameFillReport[];
}

/**
 * Open `url` in the managed Chrome and fill every eligible frame. The CDP
 * connection is closed at the end; the browser and the filled page stay open.
 */
export async function openAndFill(
  url: string,
  bundle: string,
  profile: unknown,
  settings: unknown,
  chrome: ChromeOptions,
): Promise<FillRunResult> {
  await ensureChrome(chrome);
  const browser: Browser = await chromium.connectOverCDP(
    `http://127.0.0.1:${chrome.cdpPort}`,
  );
  try {
    const context = browser.contexts()[0] ?? (await browser.newContext());
    const page: Page = await context.newPage();
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(1_500); // SPA settle

    const topHost = new URL(page.url()).hostname;
    const reports: FrameFillReport[] = [];
    let piiGated = 0;

    for (const frame of page.frames()) {
      const report = await fillFrame(frame, bundle, profile, settings, topHost);
      if (report === "gated") piiGated++;
      else if (report) reports.push(report);
    }

    const totals = { detected: 0, filled: 0, skipped: 0, failed: 0 };
    const unmatched: string[] = [];
    for (const r of reports) {
      totals.detected += r.detected;
      totals.filled += r.filled;
      totals.skipped += r.skipped;
      totals.failed += r.failed;
      unmatched.push(...r.unmatched);
    }
    return {
      page_url: page.url(),
      page_title: await page.title().catch(() => ""),
      frames_filled: reports.length,
      frames_skipped_pii_gate: piiGated,
      totals,
      unmatched: [...new Set(unmatched)].slice(0, 25),
      reports,
    };
  } finally {
    // connectOverCDP: close() drops OUR connection; the launched-detached
    // Chrome and its pages stay open for the human.
    await browser.close().catch(() => {});
  }
}

async function fillFrame(
  frame: Frame,
  bundle: string,
  profile: unknown,
  settings: unknown,
  topHost: string,
): Promise<FrameFillReport | "gated" | null> {
  try {
    const u = frame.url();
    if (!/^https?:/.test(u)) return null;
    // Inject code first (harmless), ask the canonical gate, and only send
    // profile data where it says yes.
    await frame.evaluate(bundle);
    const eligible = await frame.evaluate(
      // eslint-disable-next-line no-undef
      (host) => (globalThis as JobopsGlobals).__jobopsEligible?.(host) === true,
      topHost,
    );
    if (!eligible) return "gated";
    const hasFields = await frame.evaluate(
      () => (globalThis as { document?: { querySelectorAll(s: string): { length: number } } })
        .document!.querySelectorAll("input, textarea, select").length > 0,
    );
    if (!hasFields) return null;
    return (await frame.evaluate(
      ({ p, s }) => (globalThis as JobopsGlobals).__jobopsFill!(p, s),
      { p: profile, s: settings },
    )) as FrameFillReport;
  } catch {
    return null; // detached/navigated frames mid-run
  }
}

/**
 * Pipeline entries store the POSTING url; some ATSes keep the form on a
 * sub-route. Normalize the known ones (idempotent, others untouched).
 */
export function applyUrl(url: string): string {
  try {
    const u = new URL(url);
    const parts = u.pathname.split("/").filter(Boolean);
    if (u.hostname === "jobs.ashbyhq.com" && parts.length === 2) {
      u.pathname += "/application";
      return u.toString();
    }
    if (u.hostname === "jobs.lever.co" && parts.length === 2) {
      u.pathname += "/apply";
      return u.toString();
    }
    return url;
  } catch {
    return url;
  }
}

// --- profile loading ---------------------------------------------------------

const DOC_TYPES: Record<string, string> = {
  ".pdf": "application/pdf",
  ".doc": "application/msword",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};

export interface LoadedProfile {
  profile: Record<string, unknown>;
  warnings: string[];
}

/** Extension-shaped profile from a local JSON file; resumePath/coverLetterPath
 * become embedded data-URL documents like the extension stores. Non-document
 * files (a .md resume) are skipped with a warning instead of failing the fill
 * or attaching something ATS upload fields reject. */
export function loadProfile(profilePath: string): LoadedProfile {
  if (!existsSync(profilePath)) {
    throw new Error(
      `jobops: no apply profile at ${profilePath} — copy apply-profile.example.json there and fill it in`,
    );
  }
  const raw = JSON.parse(readFileSync(profilePath, "utf8")) as Record<string, unknown>;
  const warnings: string[] = [];
  for (const [pathKey, slot] of [
    ["resumePath", "resume"],
    ["coverLetterPath", "coverLetterFile"],
  ] as const) {
    const p = raw[pathKey];
    delete raw[pathKey];
    if (typeof p !== "string" || !p) continue;
    const full = path.isAbsolute(p) ? p : path.join(path.dirname(profilePath), p);
    if (!existsSync(full)) {
      warnings.push(`${pathKey} points at missing file ${full} — nothing attached`);
      continue;
    }
    const type = DOC_TYPES[path.extname(full).toLowerCase()];
    if (!type) {
      warnings.push(
        `${pathKey} (${path.basename(full)}) isn't a .pdf/.doc/.docx — ATS upload fields reject it, so nothing was attached. Point it at a PDF (e.g. one built by jobops_prepare).`,
      );
      continue;
    }
    const buf = readFileSync(full);
    raw[slot] = {
      name: path.basename(full),
      type,
      size: buf.length,
      dataUrl: `data:${type};base64,${buf.toString("base64")}`,
    };
  }
  raw.customAnswers ??= [];
  raw.experience ??= [];
  raw.education ??= [];
  return { profile: raw, warnings };
}
