#!/usr/bin/env node
// Run the Python problem tests, from anywhere in the repo.
//
//   ./pytest                      every problem that has tests
//   ./pytest ledger               fuzzy match against src/ (exact folder name wins)
//   ./pytest codesignal           every problem whose path matches, all 5 of them
//   ./pytest ledger -m level1     unknown args go straight through to pytest
//   ./pytest _templates/codesignal
//   ./pytest --list
//
// Test your own attempt instead of the reference solution:
//
//   ICF_IMPL=attempt ./pytest ledger -m level1
//
// Each problem folder gets its own pytest process, with cwd set to that folder. One
// process over the whole tree cannot work: every problem names its tests
// `test_solution.py` and imports a bare `solution`, so pytest collides on the module
// name ("import file mismatch") and picks up the wrong pytest.ini.
// Running from inside the folder is also exactly how you'd run it by hand, so the
// `markers`/`testpaths` in each problem's pytest.ini apply unchanged.

import { existsSync, readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { basename, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = resolve(ROOT, "..", "..");

const SKIP = new Set(["node_modules", "__pycache__", ".pytest_cache"]);
const IS_TEST = /^test_.*\.py$/;

// pytest's "no tests were collected" exit code. A template with an empty suite is not
// a failure, but it shouldn't be counted as a pass either.
const NO_TESTS = 5;

const hasTests = (dir) => readdirSync(dir).some((f) => IS_TEST.test(f));

// A folder with tests is a problem; anything above one is just shelving. Stopping the
// walk at the first folder with tests keeps `progression/` and friends out of the list.
function walk(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (!e.isDirectory() || e.name.startsWith(".") || SKIP.has(e.name)) continue;
    const abs = join(dir, e.name);
    if (hasTests(abs)) out.push(abs);
    else walk(abs, out);
  }
  return out;
}

const entry = (abs) => ({ name: basename(abs), rel: relative(ROOT, abs), dir: abs });

// _templates isn't walked: its suites are stubs that pass vacuously, so a bare ./pytest
// shouldn't report them. You can still target one by path.
const problems = () => walk(join(ROOT, "src")).map(entry);

function list() {
  const all = problems();
  if (!all.length) {
    console.log("No Python problems yet. Start one:\n");
    console.log("  ./new codesignal parking-lot");
    console.log("  ./new ds lru-cache\n");
    return;
  }
  console.log("Testable problems:\n");
  for (const p of all) console.log(`  ${p.rel}`);
  console.log();
}

function resolveTargets(query) {
  // Resolved against the caller's cwd too, so a path tab-completed from the repo root
  // (apps/prep/src/codesignal/ledger) works as well as one relative to apps/prep.
  for (const base of [ROOT, process.cwd()]) {
    const direct = resolve(base, query);
    if (existsSync(direct) && hasTests(direct)) return [entry(direct)];
  }

  const all = problems();
  const q = query.toLowerCase();
  const exact = all.filter((p) => p.name.toLowerCase() === q);
  const hits = exact.length ? exact : all.filter((p) => p.rel.toLowerCase().includes(q));

  if (!hits.length) {
    console.error(`No problem matching "${query}".\n`);
    list();
    process.exit(1);
  }
  return hits;
}

// The repo venv first: it's the one with pytest installed, and picking it up here is what
// lets ./pytest work without an activated shell.
function interpreter() {
  const candidates = [
    process.env.PREP_PYTHON,
    join(REPO, ".venv/bin/python"),
    join(ROOT, ".venv/bin/python"),
  ];
  for (const c of candidates) if (c && existsSync(c)) return c;
  return "python3";
}

const argv = process.argv.slice(2);

if (argv.includes("--list") || argv.includes("-l")) {
  list();
  process.exit(0);
}

// First bare word is the problem; everything else belongs to pytest. Flags before the
// problem name are fine: `./pytest -q ledger` and `./pytest ledger -q` are the same.
const query = argv.find((a) => !a.startsWith("-"));
const passthrough = argv.filter((a) => a !== query);

const targets = query ? resolveTargets(query) : problems();
if (!targets.length) {
  list();
  process.exit(0);
}

const PY = interpreter();
const probe = spawnSync(PY, ["-c", "import pytest"], { stdio: "ignore" });
if (probe.error || probe.status !== 0) {
  console.error(`No pytest for ${PY}.\n`);
  console.error(`  ${PY} -m pip install pytest\n`);
  console.error("Or point at another interpreter with PREP_PYTHON=/path/to/python.\n");
  process.exit(1);
}

const many = targets.length > 1;
// Quiet by default when sweeping several problems. The per-folder headers are the
// structure you want then, not five full pytest reports.
const args = passthrough.length ? passthrough : many ? ["-q"] : [];

const failed = [];
const empty = [];

for (const t of targets) {
  if (many) console.log(`\n── ${t.rel}`);
  const { status, error } = spawnSync(PY, ["-m", "pytest", ...args], {
    cwd: t.dir,
    stdio: "inherit",
  });
  if (error) {
    console.error(`\n${t.rel}: ${error.message}`);
    failed.push(t.rel);
  } else if (status === NO_TESTS) empty.push(t.rel);
  else if (status !== 0) failed.push(t.rel);
}

if (many) {
  const passed = targets.length - failed.length - empty.length;
  const parts = [`${passed} passed`];
  if (failed.length) parts.push(`${failed.length} failed`);
  if (empty.length) parts.push(`${empty.length} with no tests`);
  console.log(`\n${parts.join(", ")} of ${targets.length} problems`);
  for (const f of failed) console.log(`  FAIL  ${f}`);
  for (const e of empty) console.log(`  ----  ${e}`);
  console.log();
}

process.exit(failed.length ? 1 : 0);
