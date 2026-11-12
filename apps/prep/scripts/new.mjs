#!/usr/bin/env node
// Scaffold a new practice problem from a template.
//
//   ./new react memory-game
//   ./new react memory-game --js        JS instead of the default TypeScript
//   ./new ui autocomplete
//   ./new js debounce
//   ./new algo two-pointers/container-with-most-water
//   ./new ds lru-cache
//   ./new codesignal parking-lot
//   ./new system backend/url-shortener
//   ./new                               list types and their destinations
//
// Copies the matching template, renames the placeholder headings to the problem name,
// and prints the command to run or test it.

import { cpSync, existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = resolve(ROOT, "..", "..");

// Print the "next" command the way the caller would have to type it: `./run foo` for
// someone already sitting in apps/prep, `./prep run foo` from the repo root. A hint that
// only works from a directory you aren't in is worse than no hint.
const inPrep = process.cwd() === ROOT;
const rootCli = () => {
  const rel = relative(process.cwd(), join(REPO, "prep"));
  return rel.startsWith(".") ? rel : `./${rel}`;
};
const cli = (cmd) => (inPrep ? `./${cmd}` : `${rootCli()} ${cmd}`);

// `group` means the type is filed under a subfolder — a pattern for algo, a track for
// system design. Valid values are read off the directories that already exist, so adding
// a new algo pattern is just mkdir, not an edit here.
const TYPES = {
  react: {
    template: "fe-react-ts",
    jsTemplate: "fe-react",
    dest: "src/fe/react",
    run: (rel, name) => cli(`run ${name}`),
  },
  ui: { template: "fe-ui", dest: "src/fe/ui", run: (rel, name) => cli(`run ${name}`) },
  js: { template: "fe-js", dest: "src/fe/js", run: () => (inPrep ? "pnpm test" : cli("vitest")) },
  algo: {
    template: "algo",
    dest: "src/algo",
    group: "pattern",
    run: (rel, name) => cli(`pytest ${name}`),
  },
  ds: { template: "ds", dest: "src/ds", run: (rel, name) => cli(`pytest ${name}`) },
  codesignal: {
    template: "codesignal",
    dest: "src/codesignal",
    run: (rel, name) => cli(`pytest ${name}`),
  },
  system: { template: "system", dest: "src/system", group: "track", run: () => null },
};

const ALIASES = {
  tsx: "react",
  jsx: "react",
  vanilla: "ui",
  dom: "ui",
  utils: "js",
  cs: "codesignal",
  sd: "system",
  design: "system",
};

const TEXT = /\.(md|py|js|jsx|ts|tsx|html|css|json)$/;
const KEBAB = /^[a-z0-9]+(-[a-z0-9]+)*$/;

const groups = (type) => {
  const abs = join(ROOT, TYPES[type].dest);
  if (!existsSync(abs)) return [];
  return readdirSync(abs, { withFileTypes: true })
    .filter((e) => e.isDirectory() && !e.name.startsWith("."))
    .map((e) => e.name)
    .sort();
};

function usage() {
  console.log("Usage: ./new <type> <name>\n");
  const rows = Object.entries(TYPES).map(([type, cfg]) => {
    const g = cfg.group ? `<${cfg.group}>/` : "";
    return `  ${type.padEnd(11)} ${(cfg.dest + "/" + g + "<name>").padEnd(34)} from _templates/${cfg.template}`;
  });
  console.log(rows.join("\n"));
  console.log("\nExamples:\n");
  console.log("  ./new react memory-game            # TypeScript by default; --js for JS");
  console.log("  ./new algo two-pointers/two-sum");
  console.log("  ./new system backend/url-shortener");
  console.log(`\nalgo patterns: ${groups("algo").join(", ")}`);
  console.log(`system tracks: ${groups("system").join(", ")}\n`);
}

function fail(msg) {
  console.error(`${msg}\n`);
  process.exit(1);
}

// Words that read wrong title-cased: "Lru Cache", "Url Shortener".
const ACRONYMS = new Set([
  "ai", "api", "cdn", "cli", "css", "csv", "dns", "dom", "html", "http", "id", "io",
  "json", "jwt", "lfu", "lru", "os", "rpc", "sql", "ttl", "ui", "url", "uuid", "xss",
]);

const word = (w) => (ACRONYMS.has(w) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1));

// container-with-most-water -> Container With Most Water
const titleize = (name) => name.split("-").map(word).join(" ");
// lru-cache -> LRUCache
const pascalize = (name) => name.split("-").map(word).join("");

function rewrite(dir, title, className) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const abs = join(dir, entry.name);
    if (entry.isDirectory()) {
      rewrite(abs, title, className);
      continue;
    }
    if (!TEXT.test(entry.name)) continue;
    const before = readFileSync(abs, "utf8");
    const after = before
      .replace(/<(?:Problem|Component|Service|System|Utility) Name>/g, title)
      .replace(/\b(?:Component|Problem) Name\b/g, title)
      .replace(/<ClassName>/g, className);
    if (after !== before) writeFileSync(abs, after);
  }
}

const argv = process.argv.slice(2);
const flags = argv.filter((a) => a.startsWith("-"));
const [rawType, rawName, ...extra] = argv.filter((a) => !a.startsWith("-"));

if (!rawType) {
  usage();
  process.exit(0);
}

const type = ALIASES[rawType] ?? rawType;
if (!TYPES[type]) {
  console.error(`Unknown type "${rawType}". Known: ${Object.keys(TYPES).join(", ")}\n`);
  usage();
  process.exit(1);
}
const cfg = TYPES[type];

if (!rawName) fail(`./new ${rawType} needs a name, e.g. ./new ${rawType} my-problem`);
if (extra.length) fail(`Unexpected extra argument "${extra[0]}".`);

// Split "two-pointers/container-with-most-water" into group + name.
const parts = rawName.split("/").filter(Boolean);
let group = null;
let name = parts[0];

if (cfg.group) {
  if (parts.length !== 2) {
    fail(
      `./new ${type} needs <${cfg.group}>/<name>, e.g. ./new ${type} ${groups(type)[0] ?? "some-" + cfg.group}/my-problem\n` +
        `Available ${cfg.group}s: ${groups(type).join(", ")}`,
    );
  }
  [group, name] = parts;
  if (!groups(type).includes(group)) {
    fail(
      `No ${cfg.group} "${group}" under ${cfg.dest}.\n` +
        `Available: ${groups(type).join(", ")}\n` +
        `(Adding one is just: mkdir ${cfg.dest}/${group})`,
    );
  }
} else if (parts.length !== 1) {
  fail(`./new ${type} takes a plain name, not a path — got "${rawName}".`);
}

if (!KEBAB.test(name)) {
  fail(`"${name}" should be kebab-case: lowercase words joined by hyphens.`);
}

const useJs = flags.includes("--js");
if (useJs && !cfg.jsTemplate) fail(`--js doesn't apply to ./new ${type}.`);

const templateDir = join(ROOT, "_templates", useJs ? cfg.jsTemplate : cfg.template);
if (!existsSync(templateDir)) fail(`Missing template: ${relative(ROOT, templateDir)}`);

const destDir = join(ROOT, cfg.dest, ...(group ? [group] : []), name);
if (existsSync(destDir) && statSync(destDir).isDirectory() && readdirSync(destDir).length) {
  fail(`${relative(ROOT, destDir)} already exists and isn't empty — refusing to overwrite.`);
}

// Templates are runnable in place (`./pytest _templates/codesignal`), which leaves
// caches next to the files. A blind recursive copy carries them into the new problem.
const JUNK = new Set(["__pycache__", ".pytest_cache", ".DS_Store", "node_modules"]);
cpSync(templateDir, destDir, { recursive: true, filter: (src) => !JUNK.has(basename(src)) });
rewrite(destDir, titleize(name), pascalize(name));

const rel = relative(ROOT, destDir);
console.log(`\nCreated ${rel}${sep}`);
for (const f of readdirSync(destDir).sort()) console.log(`  ${f}`);

const cmd = cfg.run(rel, name);
console.log("\nNext:");
console.log(`  Read ${rel}/README.md, fill in the prompt, then solve it cold.`);
if (cmd) console.log(`  ${cmd}`);
console.log();
