# The progression — what `FileSystem` looked like at the end of each level

`l1.py`, `l2.py`, `l3.py` and `l4.py` are four complete, standalone
implementations of the same class. None of them imports from another, none
subclasses another, `solution.py` is not involved, and there is no shared base
module. Each one is exactly what the file contained at the moment that level's
tests went green and before the next level had been read.

That independence is the point of the artifact. Because the files are whole, the
diff between two adjacent ones is the honest bill for that transition:

```bash
diff -u progression/l1.py progression/l2.py
diff -u progression/l2.py progression/l3.py
diff -u progression/l3.py progression/l4.py
```

Each file passes every test up to and including its own level, and no more:

```bash
ICF_IMPL=progression.l1 python3 -m pytest -q -m "level1"                        # 16 passed
ICF_IMPL=progression.l2 python3 -m pytest -q -m "level1 or level2"              # 32 passed
ICF_IMPL=progression.l3 python3 -m pytest -q -m "level1 or level2 or level3"    # 50 passed
ICF_IMPL=progression.l4 python3 -m pytest -q                                    # 68 passed
```

The discipline that makes the exercise worth reading is that no file contains
anything its own level did not ask for. `l1.py` contains zero occurrences of
`move`, `copy`, `_walk_files` or `find_files_by_size` — grep it, including the
prose. `_Node` at Level 1 has `is_dir`, `size` and `children`, and it still has
exactly those three fields at Level 4: this problem never invents a new kind of
thing to store, which is precisely why it cannot be won on storage. Level 2's
`_walk_files` arrives at the level that first needs a subtree enumerated, not
before. Seeding a traversal into Level 1 because you happen to know Level 2
exists would make the files pleasant and the demonstration worthless.

What `l1.py` *does* carry is three private helpers, and the argument that this is
craft rather than clairvoyance is made at length in the file's own docstring and
restated below. It is the whole thesis of this mock, so it is worth being
precise about.

---

## Why this mock is not like the rest of the kit

Every other mock in this kit is won or lost on **storage shape**. Mock 1 is won
by storing a record instead of a string and then an append-only event log
instead of a record; Mock 2 by a sorted interval list; others by a fallback
chain. Their Level 4s all have the same shape of punishment: they ask a question
about the *past*, and an implementation that stored only current state cannot
answer it at any price, because the information was thrown away on write. The
kit's recurring lesson is therefore *keep a log before anything asks you for
one* — or, more defensibly, *store the thing, not a summary of the thing.*

None of that applies here, and it is worth saying plainly rather than pretending
otherwise. Read the spec: `timestamp` is the first argument to all eight public
methods across four levels and is **never read by any of them**. Nothing
expires. Nothing is versioned. No query targets a past instant. There is no
delete, so there is not even a tombstone question. Level 4 does not ask what a
directory used to contain; it asks which files are big *right now*. The data
structure is a tree with a `children` dict, every candidate writes that tree in
the first three minutes, and every candidate is right. If you came into this
problem looking for the storage trick, you will spend ten minutes not finding
it, because it is not there.

What is there instead is **repetition**, and this exam charges for it twice, at
two different scales.

The first scale is the **path walk**. Count what the spec demands: `mkdir`,
`add_file` and `get_file_size` each turn a path string into a node;
`get_dir_size` and `find_largest_file` do it again; `find_files_by_size` does it
once more; `move` and `copy` each do it *twice* — once for the source, once to
prove the destination is free — and additionally split a target into
`(parent, name)`, which four methods need in total. That is eleven walks and six
splits demanded by a spec you read in instalments over ninety minutes. Written
once, that is nine lines. Written eleven times under a timer, it is where the
off-by-one on the root path lives, and the root path is a case with dedicated
tests at every single level: `mkdir(t, "/")` is `False`, `get_dir_size(t, "/")`
on an empty tree is `0` and not `None`, a file under root formats as `/name` and
not `//name`, and root is neither a legal `move` source nor a legal `move`
target.

The second scale is the **subtree walk**, and it is scored at Level 4. Three
methods need "every `(full_path, file_node)` under this node, at any depth, with
the path built as you descend": `get_dir_size` to sum it, `find_largest_file` to
maximise over it, `find_files_by_size` to filter, sort and render it. Two of
those three are visible on the same page at Level 2. The third arrives at minute
seventy.

So the lesson this mock trains is **DRY under time pressure**, and specifically
the judgement call of *when* extracting a helper is justified by evidence
already on the page rather than by a guess about the next page. That is worth
practising precisely because it is the harder discipline of the two. Choosing an
event log at Level 1 is a single, memorable, transferable decision; you either
know the pattern or you don't. Refusing to paste nine lines for the third time
at minute eight — when pasting is faster right now, when you have not yet seen
Level 3, and when the helper looks like over-engineering — is a decision you
have to make correctly under adrenaline, and it is the one that generalises
furthest outside exam conditions. The measurements below are an attempt to put
a number on what it is worth.

---

## Level 1 → Level 2: aggregation, at zero cost to the existing code

Level 2 asked for the total bytes under a directory and the largest file
anywhere beneath it. It said nothing about how the tree is stored, and nothing
about storage changed: `_Node`, `_components`, `_resolve`, `_parent_and_name`
and `_create` are byte for byte what they were in `l1.py`, and — this is the
measured claim, not an impression — **not one of the three Level 1 public
methods was touched**. `mkdir`, `add_file` and `get_file_size` are identical
across the two files.

Both new methods open with `self._resolve(path)` followed by a rejection of
anything that is missing or is not a directory. That is the first visible
dividend from Level 1: the "which node is this?" question and the "is it a
directory?" question are already answered, so `get_dir_size` has a four-line
body and `find_largest_file` a nine-line one.

The one new judgement call at this level is that both methods also *close* the
same way. Each needs every file in a subtree together with its full path, so
that enumeration is a single private generator, `_walk_files`, rather than two
nearly identical recursions. They differ in what they do with the stream —
`get_dir_size` sums the sizes, `find_largest_file` takes a minimum on the key
`(-size, full_path)` — and they do not differ at all in which files are in
scope. Two callers on the same page is the entire justification, and it is
sufficient; nothing here needs to know that Level 4 exists.

It is worth being explicit that this is the *same* argument `l1.py` made about
`_resolve`, one scale up, and that it is available on exactly the same evidence:
two methods in front of you doing identical work. Writing the recursion twice
would have worked identically today. The bill for having written it twice
arrives at Level 4, and is measured below.

`_join` is factored out for a narrower reason: the root case is where path
formatting goes wrong, `"/" + "/" + name` is the bug, and that fact deserves one
assertion rather than one per recursion step. At Level 2 that bug is invisible
even when you have it, because `//pic.png` and `/pic.png` contribute the same
number of bytes to a sum. At Level 4 it prints.

## Level 2 → Level 3: the level the path factoring was insuring against, and still nothing was touched

Level 3 introduced `move` and `copy` with six shared failure conditions, a
deep-copy requirement, a component-wise (not string-prefix) subtree containment
test, and the graded rule that a failed mutation must leave the tree
byte-identical.

**Not one carried-over method changed.** All twelve methods present in `l2.py` —
five public, seven private, including `__init__` — are byte for byte identical in
`l3.py`. The diff is purely additive: two public methods, three private helpers
(`_clone`, `_is_inside`, `_relocatable`), and nothing else.

And this is where the Level 1 decision gets its bill paid. `move` is **8 body
lines** (11 with its signature and docstring); `copy` is **6 body lines** (8
total). They are that short because the six shared refusals live in
`_relocatable`, which is itself short — 13 lines — because each of its six checks
is a call to a primitive that already existed: `_components` for the two root
tests, `_resolve` twice for "src must exist" and "dst must not", and
`_parent_and_name` for "dst's parent exists and is a directory". `move`'s entire
body after validation is three statements: split the source path, unlink,
relink.

`_relocatable` is also what makes the no-op-on-failure rule free rather than
delicate. Every refusal is decided before either method has written a single
byte, so there is no partially detached subtree to unwind and no half-written
clone to delete. The `dst inside src` check in particular *has* to happen before
the recursion starts, or a naive `copy` clones into what it is still traversing
and never terminates. That check is two lines because it is a slice comparison
on component lists, which is the correct way to express it and also the reason
`/ab/moved` is correctly judged not to be inside `/a`.

## Level 3 → Level 4: the same thesis again, one scale up — and again nothing was touched

Level 4 asks for one method: every file in a subtree at or above a size
threshold, sorted by full path, rendered `"path(size)"` and joined with `", "`.

**Zero carried-over methods out of seventeen changed.** Not one public method,
not one private helper, not `__init__`, not `_Node`. Strip the docstrings from
both files and the entire L3 → L4 code diff is a **single hunk of eight lines
appended at the end of the class** — the new method and the blank line before
it. This is the third transition in a row with no rework, and it is the one that
would have been expensive under a different Level 2.

The reason is that Level 4 is **a second instance of this exam's own thesis, at
a different scale**. Level 2 already forced "enumerate every
`(full_path, file_node)` in this subtree" twice — once to sum for
`get_dir_size`, once to maximise for `find_largest_file`. A candidate who named
that walk `_walk_files` at minute twenty-five, on the strength of two callers
visible on the same page, gets Level 4 as a filter, a sort and a `", ".join`:

```python
node = self._resolve(path)
if node is None or not node.is_dir:
    return ""
matches = [(p, f.size) for p, f in self._walk_files(node, path) if f.size >= threshold]
matches.sort(key=lambda match: match[0])
return ", ".join(f"{p}({size})" for p, size in matches)
```

**10 body lines**, 18 including signature and docstring. `_walk_files` was
**used exactly as it stood** — not one character of it changed to serve its
third caller, and it needed no new parameter, because the two things it already
yields are the two things this level needs: the path to print and the node to
read a size off. The `_resolve`-then-reject opening is the same four lines every
query at Levels 1–3 opens with.

A candidate who instead wrote two ad-hoc recursions at Level 2 — each
accumulating into its own local, each re-deriving the child path with its own
`"/" + name` — writes the subtree walk a **third** time at minute seventy. And
the root-path join bug that Level 2 hid inside a sum (`//pic.png` contributes
the same byte count as `/pic.png`, so a wrong join is invisible to
`get_dir_size`) now prints straight into the graded output string, where the
grader compares it character by character. The spec's own edge-case list says
so out loud: *"the same root-join trap as Level 2, except here a wrong join is
visible in the output string instead of being swallowed by a sum."*

So the exam asks the same question twice, at two scales: **how many times did
you write the path walk, and how many times did you write the subtree walk.**
Level 3 grades the first. Level 4 grades the second. The counterfactual measured
below puts a number on the second.

### Two details in the new method that are not free

Neither is a factoring question; both are places to lose points with a perfect
design.

The **return type has no `None`.** `path` missing and `path` being a file both
return `""`, which is the same value a directory with nothing big enough
returns. Everywhere else in this exam those situations are `None`. The
inconsistency is in the signature, not in your reading of it, and the third case
falls out of `", ".join([])` for free.

**Sort the path, then format.** The sort key is `match[0]`, applied before
rendering. Sorting the finished `"path(size)"` strings is a genuinely different
order: `(` is `0x28`, below `/` (`0x2F`) and below every letter and digit, so
`/media/hero` and `/media/hero!2.jpg` sort one way by path and the other way by
rendered entry. With names drawn only from letters, digits, `.`, `-` and `_` the
two orders always agree — which is exactly why writing it the wrong way round is
invisible until it isn't. Sorting the field costs nothing and is right in both
cases.

---

## Measured

Produced by a throwaway `difflib`/`ast` script, since deleted. Two sets of
numbers are given because the module docstrings differ substantially between
files and are a large fraction of each file. "Whole file" is what `diff -u`
prints. "Code only" is the same comparison after every module, class and method
docstring has been stripped and the AST re-emitted, so it measures the code.
"Carried-over methods changed" is an AST comparison of every method present in
both files, and is the authoritative number.

| Transition | whole file | `diff -u` | code only | code `diff` | public added | private added | carried-over methods changed |
|---|---|---|---|---|---|---|---|
| L1 → L2 | 143 → 172 | +67 / −38, 4 hunks | 58 → 86 | +29 / −1, 4 hunks | 2 | 2 | **0 of 8** (0 of 3 public) |
| L2 → L3 | 172 → 252 | +100 / −20, 3 hunks | 86 → 131 | +45 / −0, 2 hunks | 2 | 3 | **0 of 12** (0 of 5 public) |
| L3 → L4 | 252 → 282 | +67 / −37, 2 hunks | 131 → 139 | **+8 / −0, 1 hunk** | 1 | 0 | **0 of 17** (0 of 7 public) |

Three notes on that table, because two of the numbers look worse than they are.

The single `−1` in the L1 → L2 code-only column is `from typing import Optional`
widening to `from typing import Iterator, Optional`. That is the only line
removed across all three transitions in the code-only view; L2 → L3 and L3 → L4
remove nothing at all.

The L3 → L4 **whole-file** figure of `+67 / −37` is almost entirely the module
docstring. `l4.py`'s header explains the subtree-walk argument at length and
`l3.py`'s explained the path-walk one; strip both and what remains is `+8 / −0`
in one hunk. The whole-file number measures this artifact's prose, not the exam.

`_Node` is unchanged in all three transitions — `is_dir`, `size`, `children` at
Level 1 and the same three fields at Level 4. No transition in this exam adds a
field to the stored representation, which is the measured form of "this problem
is not won on storage".

Rework only — the cost inside methods that already existed, excluding every new
method, banner comment, import and docstring:

| Transition | carried-over methods changed | added | removed | which ones |
|---|---|---|---|---|
| L1 → L2 | 0 | +0 | −0 | none — purely additive |
| L2 → L3 | 0 | +0 | −0 | none — purely additive |
| L3 → L4 | 0 | +0 | −0 | none — purely additive |

All three transitions were purely additive. That is not a claim that a good
Level 1 design makes later levels free — Level 4 still costs ten lines that have
to be right — but it is the measured claim that none of those ten lines had to
be spent editing something that already worked.

What Levels 3 and 4 cost, which is where the spec itself points:

| Method | body lines | with signature and docstring |
|---|---|---|
| `move` (`l3.py`) | 8 | 11 |
| `copy` (`l3.py`) | 6 | 8 |
| `_relocatable` (shared by both) | 13 | 20 |
| `_walk_files` (`l2.py`, unchanged through `l4.py`) | 5 | 12 |
| `find_files_by_size` (`l4.py`) | **10** | 18 |

## Counterfactual 1: the path walk inlined (what Level 3 costs)

The claim that the Level 1 helpers are what made `move` and `copy` short is
testable, so it was tested rather than asserted. A throwaway `_cf_l3.py` was
written: the same tree, the same `_Node`, the same semantics, passing the same
**50** Level 1–3 tests, differing only in that the path walk and the
`(parent, name)` split are written inline in each method that needs them.
`_resolve`, `_parent_and_name`, `_create`, `_relocatable` and `_is_inside` do not
exist in it. `_join`, `_walk_files` and `_clone` were left byte-identical to
`l3.py`, so the measurement isolates the path walk and nothing else. It has since
been deleted.

| | `l3.py` | inlined `_cf_l3.py` | ratio |
|---|---|---|---|
| `move`, body lines | 8 | 42 | 5.3× |
| `copy`, body lines | 6 | 38 | 6.3× |
| all seven L1–L3 public methods, body lines | 33 | 151 | 4.6× |
| whole file, code only (docstrings stripped) | 131 | 199 | 1.5× |
| distinct `path.split("/")` sites | 1 | 9 | 9× |
| distinct `node.children.get(...)` sites | 1 | 11 | 11× |

One line of that table needs an honest caveat. Measured as raw file length,
`_cf_l3.py` is **shorter** than `l3.py` — 217 lines against 252 — and if you
stopped there you would conclude the factoring cost lines rather than saving
them. That comparison is an artefact of this artifact: `l3.py`'s five private
helpers each carry an explanatory docstring written for a reader, which no
candidate produces in an exam. Strip docstrings from both and the direction
reverses decisively, 131 against 199. The 5.3× and 6.3× figures for `move` and
`copy` are unaffected by the caveat either way, because both files' Level 3
methods were counted the same way.

The number to take away is not really any of the ratios, though. It is the last
two rows. In the inlined world you write `path.split("/")` and then a nine-line
walk over `children.get(...)` nine separate times, and the last two of those
nine are `move` and `copy`, written at roughly minute fifty of ninety with two
levels of accumulated fatigue and no tests yet green for them. Each of those two
methods walks *two* paths and needs to distinguish "dst does not exist"
(required) from "dst's parent does not exist" (a refusal) — which in the inlined
version is the awkward `existing = None; break` dance you can see costing four
lines twice over. Every one of those nine copies is a fresh chance to get the
root case wrong, and the root case has dedicated tests at every level.

## Counterfactual 2: the subtree walk inlined (what Level 4 costs)

The Level 4 claim deserves the same treatment, and it is cheap to build, so it
was built rather than asserted. Two more throwaway files, `cf_l3.py` and
`cf_l4.py`, were written and have since been deleted. They are byte-identical to
`l3.py` and `l4.py` except in one respect: **`_walk_files` does not exist**, and
neither does `_join`, which had no other caller. `get_dir_size` and
`find_largest_file` each carry their own ad-hoc recursion, and each recursion
that needs paths re-derives the child path with its own root-conditional join.
`_resolve`, `_parent_and_name`, `_create`, `_relocatable`, `_is_inside` and
`_clone` are byte-identical to the real files, so the measurement isolates the
subtree walk and nothing else. Both counterfactuals pass their full suites — 50
for `cf_l3.py`, **68** for `cf_l4.py` — so this compares two working exams, not
a working one against a broken one.

The headline is narrower than Counterfactual 1's, and saying so is the point of
measuring:

| | shared `_walk_files` | inlined recursions | ratio |
|---|---|---|---|
| `find_files_by_size`, body lines | 10 | 15 | 1.5× |
| L3 → L4 code-only diff | +8 / −0 | +18 / −0 | 2.3× |
| `get_dir_size` + `find_largest_file` + `_walk_files`, body lines | 4 + 9 + 5 = **18** | 13 + 17 + 0 = **30** | 1.7× |
| all eight L1–L4 public methods, body lines | 43 | 65 | 1.5× |
| whole file at L4, code only | 139 | 157 | 1.1× |
| distinct file-enumeration recursions | **1** | **3** | 3× |
| distinct child-path join sites | **1** | **2** | 2× |

The honest reading: inlining the subtree walk is **not** the catastrophe that
inlining the path walk is. `find_files_by_size` goes from 10 lines to 15, not
from 6 to 38. If all you care about is line count, Level 4 in the inlined world
costs ten extra lines and you would still finish it.

The cost is in the last two rows, and it is a correctness cost rather than a
volume one. In the inlined world there are **three** independent recursions over
`children` that enumerate files, and **two** independent hand-written answers to
"what is the path of this child, given that the parent might be `/`". In the
shared world there is one of each, and the one join site is `_join`, which was
written at Level 2 and has been exercised by every `get_dir_size` and
`find_largest_file` test since — several hundred assertions' worth of evidence
that it handles root correctly, all of it collected before Level 4 was read.

The third recursion in the inlined world is written at minute seventy, by a
tired candidate, and its join is the only one of the three whose output is
compared as a string. `get_dir_size` cannot tell you whether your join is right:
`//pic.png` and `/pic.png` add the same 900 bytes. `find_largest_file` can, but
only if a test happens to put the largest file directly under root.
`find_files_by_size(t, "/", 0)` on the spec's own worked example prints every
file in the tree, two of them directly under root, and compares the whole string.
So the inlined candidate arrives at the one method that will catch the bug
having had no prior opportunity to find it — with a freshly written join, at the
worst moment on the clock.

That is the difference the ratios understate. The shared world does not just
write fewer lines at Level 4; it writes **zero new lines of traversal**, and the
traversal it reuses has been under test for forty-five minutes.

## The decision that paid for all of it

It was not the tree. The tree is `is_dir`, `size` and a `children` dict, it was
obvious at minute two, and it never changed across four levels — `_Node` has the
same three fields in `l4.py` that it has in `l1.py`. It was two extractions,
made at two different moments, on the same kind of evidence.

The first is the nine lines of `l1.py` that say `_resolve(path)`, written before
`mkdir` was finished, at a moment when the only evidence for them was that three
Level 1 methods were about to open with the same loop. The second is the five
lines of `l2.py` that say `_walk_files(node, path)`, written at minute
twenty-five, when the only evidence was that the two methods on the page were
about to close with the same recursion.

Three callers, and then two, are thin-looking justifications for a helper when
you are eight and then twenty-five minutes into a ninety-minute exam and pasting
would be faster. They are also completely sufficient, and each required knowing
nothing whatsoever about the levels that had not been revealed yet — which is
the entire point, because at those moments you have not read them. The measured
consequence is that **all three transitions were purely additive with zero
carried-over methods touched**, that `move` and `copy` cost 8 and 6 body lines
against a measured counterfactual of 42 and 38, and that Level 4 — a whole
level, two hundred points — cost **ten lines and one hunk**, over a traversal
that had been passing tests for forty-five minutes.

The question this mock leaves you with is therefore not "did I pick the right
structure" — everyone picks the same structure and everyone is right. It is
**how many times did I write the path walk, how many times did I write the
subtree walk, and what time was it when I wrote each of them for the last time.**
