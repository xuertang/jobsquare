#!/usr/bin/env python3
"""Measure the churn of two four-level progressions, side by side.

    python3 wrong_path/measure.py

Compares `progression/l{1,2,3,4}.py` (the good path: one record type, one read
chokepoint) against `wrong_path/naive_l{1,2,3,4}.py` (the naive path: parallel
dicts, every method reading them directly). Both progressions pass the same test
suite at the same levels, so a difference in churn is a difference in cost, not
in correctness.

Nothing here imports either implementation. Every file is read as text and
parsed with `ast`, so the numbers describe source and cannot be affected by
runtime behaviour.

IF `progression/` IS ABSENT
---------------------------
The good path is a sibling directory that may be missing, half-written, or on an
older API revision. This script does not require it. Each path is validated
before it is measured -- every file must exist, parse, and expose `timestamp` as
the first parameter of `ContentStore.add_content`, which is the convention the
whole kit is written to. A path that fails any of those checks is reported as
unavailable, with the reason, and dropped from the comparison; the remaining
path is still measured and printed in full. Every table below renders one column
group per available path, so a single-path run is a legal run.

WHAT IS MEASURED

1. Whole-file line churn per transition (L1->L2, L2->L3, L3->L4).
   `difflib.SequenceMatcher` over source lines yields three disjoint buckets,
   using the convention `diff -u` uses:

       added    'insert' lines, plus the surplus new lines of a 'replace' run
       removed  'delete' lines, plus the surplus old lines of a 'replace' run
       changed  the lines of a 'replace' run that were rewritten in place,
                i.e. min(old_run, new_run)

   Churn = added + removed + changed. A one-line edit costs 1, not 2.

2. Rework vs new surface, per transition. Whole-file diffs are sensitive to how
   `difflib` aligns interleaved blocks, so the same transition is also measured
   definition by definition. Every `def` is extracted by `ast` and keyed by
   qualified name (`ContentStore.add_content`, `_Record.alive_at`), then:

       rework        churn inside defs that exist in BOTH files
       new surface   lines of defs that exist only in the later file
       retired       lines of defs that exist only in the earlier file

   This split is alignment-proof and it is the interesting one: rework is what a
   data model charges you for a change of requirements, new surface is what the
   requirement itself costs and would have to be written either way. A rename
   (`_Record.alive_at` -> `_Event.alive_at`) appears as retired + new surface,
   never as rework.

   Note what this measure looks like under the kit's calling convention. Because
   `timestamp` is the first parameter of every public method from Level 1, no
   level introduces a parallel timestamped API and no public signature is ever
   replaced. Almost the entire L2->L3 and L3->L4 diff therefore lands inside
   method *bodies* on both paths, which is exactly where a data-model difference
   shows up and exactly where a signature churn artefact would not.

3. Storage read sites. A file's storage containers are auto-detected as any
   `self._x` assigned a dict literal in `__init__`. A def is a "read site" if it
   loads one of those attributes somewhere that is not the target of an
   assignment or a `del` -- mechanically, the places that reach into the store to
   answer a question, as opposed to the places that only write to it.

   This is the number the comparison turns on. Every read site is a place the
   liveness rule has to be applied when Level 3 lands, and therefore a place it
   can be forgotten. See the failures recorded in `naive_l3_buggy.py`.

4. Liveness-rule sites. The same question asked from the other end: how many
   defs actually spell the `t <= q < t + d` rule out? A def counts if it
   contains an `ast.Compare` whose unparsed text mentions an expiry identifier
   (anything matching "expir"). Duplicated invariants are the failure mode this
   whole comparison is about, and this counts them directly.

WHAT IS EXCLUDED

Module docstrings, from every count, so the comparison is about code rather than
about how much each file explains itself. Method and class docstrings, comments
and blank lines are counted in the primary tables -- they are part of what you
type during the exam.

Because the two progressions comment themselves at different densities, and that
would flatter or penalise a path for reasons unrelated to its data model, every
table is also reported in a CODE-ONLY variant: each file is round-tripped
through `ast.unparse` with all docstrings removed, which deletes comments,
docstrings, blank lines and formatting differences and leaves one canonical line
per statement. If the two variants tell the same story, the story is about the
code.
"""

from __future__ import annotations

import ast
import difflib
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
GOOD_DIR = HERE.parent / "progression"

GOOD_NAME = "good path"
NAIVE_NAME = "naive path"
LEVELS = ("L1", "L2", "L3", "L4")

GOOD_FILES = [(label, GOOD_DIR / f"l{i}.py") for i, label in enumerate(LEVELS, 1)]
NAIVE_FILES = [(label, HERE / f"naive_l{i}.py") for i, label in enumerate(LEVELS, 1)]

PATHS = [
    (GOOD_NAME, "progression/l1.py .. l4.py", GOOD_FILES),
    (NAIVE_NAME, "wrong_path/naive_l1.py .. naive_l4.py", NAIVE_FILES),
]


# ----------------------------------------------------------------------
# Availability: a path may be missing, unparsable, or on an older API
# ----------------------------------------------------------------------


def api_signature_ok(tree: ast.Module) -> bool:
    """True if `ContentStore.add_content` takes `timestamp` as its first arg.

    The kit's calling convention puts `timestamp` first on every public method
    from Level 1 onwards. A file that does not do that is from an older
    revision, and diffing against it would produce numbers that describe a
    rename rather than a data model.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "add_content":
            args = [a.arg for a in node.args.args]
            return len(args) >= 2 and args[0] == "self" and args[1] == "timestamp"
    return False


def unavailable_reason(files: list[tuple[str, Path]]) -> Optional[str]:
    """Why this path cannot be measured, or None if it can."""
    missing = [str(p.name) for _, p in files if not p.is_file()]
    if missing:
        directory = files[0][1].parent
        if not directory.is_dir():
            return f"directory {directory.name}/ does not exist"
        return f"missing {', '.join(missing)} in {directory.name}/"
    for label, path in files:
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError as exc:  # pragma: no cover - defensive
            return f"{path.name} does not parse ({exc.msg}, line {exc.lineno})"
        if not api_signature_ok(tree):
            return (
                f"{path.name} is on an older API revision "
                f"(add_content does not take `timestamp` first)"
            )
    return None


# ----------------------------------------------------------------------
# Source loading and normalisation
# ----------------------------------------------------------------------


def _is_docstring(node: ast.AST) -> bool:
    """True for an expression statement that is just a string literal."""
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def strip_module_docstring(text: str) -> str:
    """Return `text` with its module docstring and any trailing blanks removed."""
    tree = ast.parse(text)
    if not tree.body or not _is_docstring(tree.body[0]):
        return text
    first = tree.body[0]
    lines = text.splitlines()
    assert first.end_lineno is not None
    del lines[first.lineno - 1 : first.end_lineno]
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines) + "\n"


class _DropDocstrings(ast.NodeTransformer):
    """Remove the leading string-literal statement from every scope."""

    def _clean(self, node: ast.AST) -> ast.AST:
        self.generic_visit(node)
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and _is_docstring(body[0]):
            body.pop(0)
            if not body:
                body.append(ast.Pass())
        return node

    visit_Module = _clean
    visit_ClassDef = _clean
    visit_FunctionDef = _clean
    visit_AsyncFunctionDef = _clean


def code_only(text: str) -> str:
    """Canonical, comment-free, docstring-free rendering of `text`."""
    tree = _DropDocstrings().visit(ast.parse(text))
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def load(path: Path, *, canonical: bool) -> str:
    """Source of `path`, module docstring stripped; canonicalised on request."""
    text = strip_module_docstring(path.read_text())
    return code_only(text) if canonical else text


# ----------------------------------------------------------------------
# 1. Line churn
# ----------------------------------------------------------------------


class Churn:
    """Line-level diff statistics for one comparison."""

    def __init__(self, added: int = 0, removed: int = 0, changed: int = 0) -> None:
        self.added = added
        self.removed = removed
        self.changed = changed

    def __iadd__(self, other: "Churn") -> "Churn":
        """Accumulate another Churn in place."""
        self.added += other.added
        self.removed += other.removed
        self.changed += other.changed
        return self

    @property
    def total(self) -> int:
        """Total churn: every line written, deleted or rewritten, counted once."""
        return self.added + self.removed + self.changed


def line_churn(before: str, after: str) -> Churn:
    """Added / removed / changed lines between two sources."""
    a = before.splitlines()
    b = after.splitlines()
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    churn = Churn()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old, new = i2 - i1, j2 - j1
        if tag == "insert":
            churn.added += new
        elif tag == "delete":
            churn.removed += old
        elif tag == "replace":
            churn.changed += min(old, new)
            churn.added += max(0, new - old)
            churn.removed += max(0, old - new)
    return churn


# ----------------------------------------------------------------------
# 2. Definitions: rework vs new surface
# ----------------------------------------------------------------------


def definitions(src: str) -> dict[str, str]:
    """Every `def` in `src`, keyed by qualified name, valued by source text."""
    tree = ast.parse(src)
    out: dict[str, str] = {}

    def visit(node: ast.AST, prefix: str) -> None:
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                segment = ast.get_source_segment(src, child) or ""
                out[name] = "\n".join(
                    line.rstrip() for line in segment.splitlines()
                ).strip()
                visit(child, f"{name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")

    visit(tree, "")
    return out


class DefDelta:
    """Rework inside carried-over defs, versus lines of brand-new surface."""

    def __init__(self, before: dict[str, str], after: dict[str, str]) -> None:
        carried = sorted(set(before) & set(after))
        self.gained = sorted(set(after) - set(before))
        self.lost = sorted(set(before) - set(after))
        self.carried_count = len(carried)
        self.changed = [n for n in carried if before[n] != after[n]]
        self.rework = Churn()
        for name in carried:
            self.rework += line_churn(before[name], after[name])
        self.new_surface = sum(len(after[n].splitlines()) for n in self.gained)
        self.retired = sum(len(before[n].splitlines()) for n in self.lost)


# ----------------------------------------------------------------------
# 3. Storage read sites
# ----------------------------------------------------------------------


def storage_containers(tree: ast.Module) -> set[str]:
    """`self._x` attributes assigned a dict literal in any `__init__`."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "__init__":
            continue
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.AnnAssign):
                targets: list[ast.expr] = [stmt.target]
                value = stmt.value
            elif isinstance(stmt, ast.Assign):
                targets, value = list(stmt.targets), stmt.value
            else:
                continue
            if not isinstance(value, ast.Dict):
                continue
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    found.add(target.attr)
    return found


def _is_container_attr(node: ast.AST, containers: set[str]) -> bool:
    """True for a `self.<container>` attribute node."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr in containers
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def read_sites(src: str) -> list[str]:
    """Defs that read a storage container rather than only writing to it."""
    tree = ast.parse(src)
    containers = storage_containers(tree)

    # A container attribute reached through an assignment or `del` target is a
    # write, not a read. Node identity is used, so two syntactically identical
    # occurrences inside one method are told apart.
    written: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = list(node.targets)
        else:
            continue
        for target in targets:
            for sub in ast.walk(target):
                if _is_container_attr(sub, containers):
                    written.add(id(sub))

    sites: list[str] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                if any(
                    _is_container_attr(sub, containers) and id(sub) not in written
                    for sub in ast.walk(child)
                ):
                    sites.append(name)
                visit(child, f"{name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")

    visit(tree, "")
    return sites


# ----------------------------------------------------------------------
# 4. Liveness-rule sites
# ----------------------------------------------------------------------

EXPIRY_TOKEN = "expir"


def liveness_sites(src: str) -> dict[str, int]:
    """Defs spelling out the expiry rule, mapped to how many comparisons each has.

    A comparison counts when its source text mentions an expiry identifier, so
    this finds the places that *test* liveness rather than the places that merely
    compute or store an expiry instant.
    """
    tree = ast.parse(src)
    found: dict[str, int] = {}

    def visit(node: ast.AST, prefix: str) -> None:
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                count = sum(
                    1
                    for sub in ast.walk(child)
                    if isinstance(sub, ast.Compare)
                    and EXPIRY_TOKEN in ast.unparse(sub)
                )
                if count:
                    found[name] = count
                visit(child, f"{name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")

    visit(tree, "")
    return found


# ----------------------------------------------------------------------
# Assembly
# ----------------------------------------------------------------------


def measure(files: list[tuple[str, Path]], *, canonical: bool) -> dict:
    """Every statistic for one progression."""
    sources = [(label, load(p, canonical=canonical)) for label, p in files]
    transitions = []
    for (before_label, before), (after_label, after) in zip(sources, sources[1:]):
        transitions.append(
            {
                "name": f"{before_label}->{after_label}",
                "churn": line_churn(before, after),
                "defs": DefDelta(definitions(before), definitions(after)),
            }
        )
    return {
        "lengths": {label: len(src.splitlines()) for label, src in sources},
        "transitions": transitions,
        "read_sites": {label: read_sites(src) for label, src in sources},
        "liveness": {label: liveness_sites(src) for label, src in sources},
        "containers": {
            label: sorted(storage_containers(ast.parse(src)))
            for label, src in sources
        },
    }


# ----------------------------------------------------------------------
# Reporting
#
# Every table renders one column group per available path, so the report is
# legal with one path or with two.
# ----------------------------------------------------------------------

WIDTH = 78


def rule(char: str = "-") -> str:
    """A horizontal rule."""
    return char * WIDTH


def length_table(measured: list[tuple[str, dict]]) -> str:
    """File length in lines."""
    header = f"{'level':<7} " + "".join(f"| {name:>10} " for name, _ in measured)
    if len(measured) == 2:
        header += "| naive - good"
    rows = [header, rule()]
    for label in LEVELS:
        row = f"{label:<7} " + "".join(
            f"| {data['lengths'][label]:>10} " for _, data in measured
        )
        if len(measured) == 2:
            a, b = (data["lengths"][label] for _, data in measured)
            row += f"| {b - a:>+12}"
        rows.append(row)
    return "\n".join(rows)


def churn_table(measured: list[tuple[str, dict]]) -> str:
    """Whole-file added / removed / changed / churn, per path."""
    rows = [
        f"{'':<11}" + "".join(f"|{'  ' + name:^31}" for name, _ in measured),
        f"{'transition':<11}"
        + "".join(
            f"|{'added':>7}{'removed':>8}{'changed':>8}{'churn':>8}" for _ in measured
        ),
        rule(),
    ]
    totals = [0] * len(measured)
    count = len(measured[0][1]["transitions"])
    for index in range(count):
        cells = ""
        name = measured[0][1]["transitions"][index]["name"]
        for column, (_, data) in enumerate(measured):
            churn = data["transitions"][index]["churn"]
            totals[column] += churn.total
            cells += (
                f"|{churn.added:>7}{churn.removed:>8}"
                f"{churn.changed:>8}{churn.total:>8}"
            )
        rows.append(f"{name:<11}{cells}")
    rows.append(rule())
    rows.append(
        f"{'TOTAL':<11}"
        + "".join(f"|{'':>7}{'':>8}{'':>8}{total:>8}" for total in totals)
    )
    return "\n".join(rows)


def rework_table(measured: list[tuple[str, dict]]) -> str:
    """Rework inside carried-over defs vs lines of brand-new surface."""
    rows = [
        f"{'':<11}" + "".join(f"|{'  ' + name:^31}" for name, _ in measured),
        f"{'transition':<11}"
        + "".join(
            f"|{'methods':>8}{'rework':>8}{'new':>7}{'retired':>8}" for _ in measured
        ),
        rule(),
    ]
    totals = [0] * len(measured)
    count = len(measured[0][1]["transitions"])
    for index in range(count):
        cells = ""
        name = measured[0][1]["transitions"][index]["name"]
        for column, (_, data) in enumerate(measured):
            defs = data["transitions"][index]["defs"]
            totals[column] += defs.rework.total
            ratio = f"{len(defs.changed)}/{defs.carried_count}"
            cells += (
                f"|{ratio:>8}{defs.rework.total:>8}"
                f"{defs.new_surface:>7}{defs.retired:>8}"
            )
        rows.append(f"{name:<11}{cells}")
    rows.append(rule())
    rows.append(
        f"{'TOTAL':<11}"
        + "".join(f"|{'':>8}{total:>8}{'':>7}{'':>8}" for total in totals)
    )
    rows.append("")
    rows.append("  methods = defs present in BOTH files whose source differs, over")
    rows.append("            the number of defs present in both. Renames excluded.")
    rows.append("  rework  = churn INSIDE those carried-over defs (alignment-proof).")
    rows.append("  new     = lines of defs that exist only in the later file.")
    return "\n".join(rows)


def read_site_table(measured: list[tuple[str, dict]]) -> str:
    """Storage read sites per level."""
    rows = [
        f"{'level':<7} " + "".join(f"| {name:>10} " for name, _ in measured),
        rule(),
    ]
    for label in LEVELS:
        rows.append(
            f"{label:<7} "
            + "".join(
                f"| {len(data['read_sites'][label]):>10} " for _, data in measured
            )
        )
    return "\n".join(rows)


def liveness_table(measured: list[tuple[str, dict]]) -> str:
    """Defs spelling out the liveness rule, and how many comparisons in total."""
    rows = [
        f"{'':<7} " + "".join(f"|{'  ' + name:^19}" for name, _ in measured),
        f"{'level':<7} " + "".join(f"|{'defs':>9}{'compares':>10}" for _ in measured),
        rule(),
    ]
    for label in LEVELS:
        cells = ""
        for _, data in measured:
            sites = data["liveness"][label]
            cells += f"|{len(sites):>9}{sum(sites.values()):>10}"
        rows.append(f"{label:<7} {cells}")
    rows.append("")
    for label in ("L3", "L4"):
        for name, data in measured:
            sites = data["liveness"][label]
            rendered = ", ".join(f"{k}({v})" for k, v in sites.items()) or "none"
            rows.append(f"  {label} {name}: {rendered}")
    return "\n".join(rows)


def read_site_detail(measured: list[tuple[str, dict]]) -> str:
    """The named Level 3 read sites and the containers behind them."""
    rows = [
        "The Level 3 read sites, named. These are the distinct call sites that",
        "had to be visited and taught the liveness rule when expiry landed:",
        "",
    ]
    for name, data in measured:
        rows.append(f"  {name} ({len(data['read_sites']['L3'])}):")
        rows += [f"    {site}" for site in data["read_sites"]["L3"]]
    rows += ["", "Storage containers detected at Level 3:"]
    for name, data in measured:
        rows.append(f"  {name}: {', '.join(data['containers']['L3'])}")
    return "\n".join(rows)


def detail(name: str, data: dict) -> str:
    """Per-transition method-level detail for one progression."""
    rows = [name, rule()]
    for t in data["transitions"]:
        churn, defs = t["churn"], t["defs"]
        rows.append(
            f"  {t['name']}: +{churn.added} -{churn.removed} ~{churn.changed} "
            f"(churn {churn.total}) | rework {defs.rework.total} in "
            f"{len(defs.changed)} of {defs.carried_count} carried-over defs"
        )
        if defs.changed:
            rows.append(f"    changed: {', '.join(defs.changed)}")
        if defs.gained:
            rows.append(f"    added:   {', '.join(defs.gained)}")
        if defs.lost:
            rows.append(f"    removed: {', '.join(defs.lost)}")
    return "\n".join(rows)


def report(available: list[tuple[str, str, list[tuple[str, Path]]]], canonical: bool) -> None:
    """Print every table for one normalisation setting."""
    measured = [
        (name, measure(files, canonical=canonical)) for name, _, files in available
    ]

    banner = (
        "CODE-ONLY VARIANT -- all docstrings, comments, blank lines and\n"
        "formatting differences removed by round-tripping through ast.unparse.\n"
        "One canonical line per statement."
        if canonical
        else "AS WRITTEN -- module docstrings excluded; method docstrings,\n"
        "comments and blank lines included."
    )
    print(rule("="))
    print(banner)
    print(rule("="))
    print()
    print("FILE LENGTH (lines)")
    print(rule())
    print(length_table(measured))
    print()
    print("WHOLE-FILE CHURN PER TRANSITION")
    print(rule())
    print(churn_table(measured))
    print()
    print("REWORK VS NEW SURFACE PER TRANSITION")
    print(rule())
    print(rework_table(measured))
    print()
    print("STORAGE READ SITES PER LEVEL")
    print(rule())
    print(read_site_table(measured))
    print()
    print("LIVENESS-RULE SITES PER LEVEL (defs that spell the rule out)")
    print(rule())
    print(liveness_table(measured))
    print()
    if not canonical:
        print(read_site_detail(measured))
        print()
        print("PER-TRANSITION DETAIL")
        print(rule("="))
        for name, data in measured:
            print(detail(name, data))
            print()


def main() -> None:
    """Print the full side-by-side report, both normalisations."""
    print(rule("="))
    print("ICF Mock 1 -- ContentStore: good path vs naive path, measured")
    print(rule("="))
    print()

    available = []
    for name, blurb, files in PATHS:
        reason = unavailable_reason(files)
        if reason is None:
            available.append((name, blurb, files))
            print(f"  {name + ':':<12} {blurb}")
        else:
            print(f"  {name + ':':<12} UNAVAILABLE -- {reason}")

    if not available:
        print()
        print("Neither progression is available; there is nothing to measure.")
        return

    if len(available) < len(PATHS):
        print()
        print("Only one progression is available, so this run is a single-path")
        print("measurement rather than a comparison. Every table below still")
        print("holds; the columns for the missing path are simply absent. Re-run")
        print("once the other directory is in place to get the side-by-side.")

    print()
    print("Module docstrings are excluded from every count below, so the")
    print("comparison is about code rather than about how much each file")
    print("explains itself.")
    print()
    report(available, canonical=False)
    report(available, canonical=True)


if __name__ == "__main__":
    main()
