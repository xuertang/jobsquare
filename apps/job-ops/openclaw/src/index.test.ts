import { describe, expect, it } from "vitest";
import entry from "./index.js";
import { getToolPluginMetadata } from "openclaw/plugin-sdk/tool-plugin";
import { applyUrl } from "./fill.js";
import { autopilotCandidates, markEntry, parsePending } from "./pipeline.js";

describe("jobops", () => {
  it("declares tool metadata", () => {
    expect(getToolPluginMetadata(entry)?.tools.map((tool) => tool.name)).toEqual([
      "jobops_pending",
      "jobops_report",
      "jobops_prepare",
      "jobops_fill",
      "jobops_autopilot",
      "jobops_mark",
    ]);
  });

  it("exposes no tool that can submit an application", () => {
    const names = getToolPluginMetadata(entry)?.tools.map((t) => t.name) ?? [];
    expect(names.some((n) => /submit|send|post/i.test(n))).toBe(false);
    // The two autonomous tools must advertise that they never submit.
    const descs = Object.fromEntries(
      (getToolPluginMetadata(entry)?.tools ?? []).map((t) => [t.name, t.description ?? ""]),
    );
    expect(descs.jobops_fill).toMatch(/never|NEVER|SUBMIT THEMSELVES|not.*submit/i);
    expect(descs.jobops_autopilot).toMatch(/Submits NOTHING/);
  });
});

describe("autopilotCandidates", () => {
  const base = FIXTURE;

  it("selects open, scored, unfilled entries best-first", () => {
    const got = autopilotCandidates(base, 4.0).map((e) => e.report);
    expect(got).toEqual([590, 508]); // 589 ticked, 542 ticked, newco unscored
  });

  it("respects the score floor", () => {
    expect(autopilotCandidates(base, 4.2).map((e) => e.report)).toEqual([590]);
  });

  it("skips entries already filled, so repeat runs don't refill", () => {
    const once = markEntry(base, 590, "filled", "2026-08-13", "9 fields");
    expect(autopilotCandidates(once.content!, 4.0).map((e) => e.report)).toEqual([508]);
  });

  it("'filled' annotates WITHOUT ticking — parked is not done", () => {
    const res = markEntry(base, 590, "filled", "2026-08-13", "9 fields");
    expect(res.updatedLine).toMatch(/^- \[ \] /);
    expect(res.updatedLine).toContain("| filled 2026-08-13 — 9 fields");
    const reparsed = parsePending(res.content!).find((e) => e.report === 590)!;
    expect(reparsed.ticked).toBe(false);
  });

  it("terminal actions still tick a filled entry", () => {
    const filled = markEntry(base, 590, "filled", "2026-08-13");
    const applied = markEntry(filled.content!, 590, "applied", "2026-08-14");
    expect(applied.updatedLine).toMatch(/^- \[x\] /);
    expect(applied.updatedLine).toContain("| filled 2026-08-13");
    expect(applied.updatedLine).toContain("| applied 2026-08-14");
  });
});

// Fixture lines lifted from the real pipeline.md (shape, not content).
const FIXTURE = `# jobsquare — offer pipeline

Inbox fed by \`/jobsquare scan\`.

## Pending
- [x] https://jobs.ashbyhq.com/snowflake/a61420af | snowflake | Senior Software Engineer - Warehouse | US-CA-Menlo Park | first_seen 2026-08-06 | $200K – $287.5K | eval 4.2/5 2026-08-06 #589
- [ ] https://careers.toasttab.com/jobs?gh_jid=7870945 | toast | Senior Software Engineer | Remote, USA | first_seen 2026-08-06 | eval 4.2/5 2026-08-06 #590
- [ ] https://mlp.eightfold.ai/careers/job/755957837780 | millennium | Software Engineer - Efficiency | Miami, Florida | first_seen 2026-08-01 | eval 4.1/5 2026-08-02 #508
- [ X] https://job-boards.greenhouse.io/discord/jobs/8675277002 | discord | Senior Software Engineer, Enterprise Platform | SF Bay Area | first_seen 2026-08-04 | eval 4.0/5 2026-08-04 #542 | done 2026-08-05
- [ ] https://example.com/unevaled | newco | Some Role | Remote | first_seen 2026-08-07

## Done
- [ ] https://example.com/done-section | notpending | Should Never Match | X | first_seen 2026-01-01 | eval 4.9/5 2026-01-01 #111
`;

describe("applyUrl", () => {
  it("routes known ATSes to their form page, idempotently", () => {
    expect(applyUrl("https://jobs.ashbyhq.com/applied/341f8193")).toBe(
      "https://jobs.ashbyhq.com/applied/341f8193/application",
    );
    expect(applyUrl("https://jobs.ashbyhq.com/applied/341f8193/application")).toBe(
      "https://jobs.ashbyhq.com/applied/341f8193/application",
    );
    expect(applyUrl("https://jobs.lever.co/spotify/5b977d60")).toBe(
      "https://jobs.lever.co/spotify/5b977d60/apply",
    );
    expect(applyUrl("https://job-boards.greenhouse.io/affirm/jobs/7812982003")).toBe(
      "https://job-boards.greenhouse.io/affirm/jobs/7812982003",
    );
  });
});

describe("parsePending", () => {
  const entries = parsePending(FIXTURE);

  it("parses only the Pending section", () => {
    expect(entries).toHaveLength(5);
    expect(entries.map((e) => e.company)).not.toContain("notpending");
  });

  it("extracts fields per the entry contract", () => {
    const toast = entries.find((e) => e.report === 590)!;
    expect(toast.company).toBe("toast");
    expect(toast.role).toBe("Senior Software Engineer");
    expect(toast.location).toBe("Remote, USA");
    expect(toast.firstSeen).toBe("2026-08-06");
    expect(toast.score).toBe(4.2);
    expect(toast.ticked).toBe(false);
    expect(toast.comp).toBe("");
  });

  it("captures comp when present and keeps it out of annotations", () => {
    const snow = entries.find((e) => e.report === 589)!;
    expect(snow.comp).toBe("$200K – $287.5K");
    expect(snow.annotations).toEqual([]);
    expect(snow.ticked).toBe(true);
  });

  it("tolerates sloppy ticks and trailing annotations", () => {
    const discord = entries.find((e) => e.report === 542)!;
    expect(discord.ticked).toBe(true); // "[ X]"
    expect(discord.annotations).toEqual(["done 2026-08-05"]);
  });

  it("keeps unevaluated entries with null score/report", () => {
    const newco = entries.find((e) => e.company === "newco")!;
    expect(newco.score).toBeNull();
    expect(newco.report).toBeNull();
  });
});

describe("markEntry", () => {
  it("ticks and annotates the addressed line only", () => {
    const res = markEntry(FIXTURE, 590, "applied", "2026-08-07", "via referral");
    expect(res.changed).toBe(true);
    expect(res.updatedLine).toMatch(/^- \[x\] /);
    expect(res.updatedLine).toContain("| applied 2026-08-07 — via referral");
    const before = FIXTURE.split("\n");
    const after = res.content!.split("\n");
    expect(after.length).toBe(before.length);
    const diff = after.filter((l, i) => l !== before[i]);
    expect(diff).toHaveLength(1);
  });

  it("is idempotent per action", () => {
    const once = markEntry(FIXTURE, 590, "applied", "2026-08-07");
    const twice = markEntry(once.content!, 590, "applied", "2026-08-08");
    expect(twice.changed).toBe(false);
    expect(twice.reason).toContain("already marked");
  });

  it("never touches entries outside Pending", () => {
    const res = markEntry(FIXTURE, 111, "done", "2026-08-07");
    expect(res.changed).toBe(false);
    expect(res.reason).toContain("no Pending entry");
  });

  it("round-trips through the parser", () => {
    const res = markEntry(FIXTURE, 508, "skipped", "2026-08-07", "comp too low");
    const reparsed = parsePending(res.content!);
    const mill = reparsed.find((e) => e.report === 508)!;
    expect(mill.ticked).toBe(true);
    expect(mill.annotations).toEqual(["skipped 2026-08-07 — comp too low"]);
    expect(mill.role).toBe("Software Engineer - Efficiency");
  });
});
