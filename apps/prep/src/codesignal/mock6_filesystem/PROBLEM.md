# Mock 6 — `FileSystem`

**Industry Coding Framework practice exam · 90 minutes · 4 progressive levels · 600 points**
**Language:** Python 3.11
*Theme: Airbnb Media Pipeline — the in-memory asset tree that holds listing photos, host guides and generated documents before they are flushed to object storage.*

> **Provenance.** All four levels are reproduced from a real circulating CodeSignal ICF problem. Every method signature and every contract below comes from that source; what this document adds is tightened wording, worked examples, and the pinned answers to the corners the source leaves ambiguous (see [Spec decisions](#spec-decisions)).

---

## How to take this exam

1. Set a **90-minute timer**. Do not stop it between levels. Budget: **L1 10 min · L2 20 min · L3 30 min · L4 30 min.**
2. `cp starter.py attempt.py` and work only in `attempt.py`. **`starter.py` contains the Level 1 methods only.** Every later level lists its own method signatures in this document; when you reach a level, copy its signatures into your class and implement them there. That is how the real CodeSignal editor behaves — the next level's methods appear only once you have submitted the current one.
3. **Reveal one level at a time.** Read Level *N*, implement it, run its tests, and only then scroll to Level *N+1*. Reading ahead defeats the entire point of the format — the exam is testing whether your Level 1 design survives Level 3.
4. Run the tests for the level you just finished:
   ```bash
   ICF_IMPL=attempt python3 -m pytest -q -m level1     # then -m level2, -m level3, -m level4
   ```
5. **Backward compatibility is graded.** After Level 4, `-m level1`, `-m level2` and `-m level3` must still pass. At the end run the whole suite:
   ```bash
   ICF_IMPL=attempt python3 -m pytest -q
   ```
6. If you are over budget on a level, move on. Partial credit across four levels beats a perfect Level 2.
7. Do not read `solution.py` until the timer is done. There is a consolidated **[Spec decisions](#spec-decisions)** section at the bottom of this document; it spans all four levels, so consult only the entry for the level you are currently on.

### Global conventions (true for every level)

- The class is named `FileSystem`. `FileSystem()` starts with **root already existing** — root is `"/"` and is always a directory.
- **Paths are absolute.** They always start with `"/"`, they never have a trailing slash (except root itself, which is exactly `"/"`), and every component between slashes is non-empty. Malformed paths (`"docs/a.txt"`, `"/docs/"`, `"//docs"`, `""`) are **out of contract** — you will not be tested on them and you should not spend time defending against them.
- A **directory** holds named children, each of which is a file or another directory. A **file** holds a non-negative integer `size`. Names are unique within their parent, but the same name may appear under different parents — and it may be a directory in one place and a file in another.
- Every method takes `timestamp: int` as its **first** argument. Timestamps arrive non-decreasing. **They are semantically unused** — nothing in this problem expires, is versioned, or is read as-of a past instant. The parameter is there so the signatures stay consistent with the ICF framework. Accept it and ignore it. (Yes, really; do not go looking for the trick.)
- **Nothing raises.** Failed mutations return `False`; absent things read back as `None`.
- **A failed mutation changes nothing.** Every `False`/`None` return in this problem is a no-op: the tree afterwards is byte-for-byte what it was before. This is graded.
- `size` is a non-negative integer; `0` is a legal file size and is **not** the same as "missing".

---

# Level 1 — Core operations

**~10 minutes · 100 points**

Build the tree and read a file's size back out.

### Methods

```python
mkdir(timestamp: int, path: str) -> bool
add_file(timestamp: int, path: str, size: int) -> bool
get_file_size(timestamp: int, path: str) -> Optional[int]
```

### Contracts

| Method | Returns |
|---|---|
| `mkdir` | `True` if a new empty directory was created at `path`. `False` if `path` already exists (as a file **or** a directory), if the parent directory does not exist, or if the parent exists but is a **file**. |
| `add_file` | `True` if a new file of `size` bytes was created at `path`. `False` under exactly the same three conditions as `mkdir` — path taken, parent missing, parent is a file. A duplicate `add_file` **does not overwrite** the existing size. |
| `get_file_size` | The `size` of the file at `path`. `None` if nothing exists at `path`, **and `None` if `path` is a directory.** |

Neither creator is recursive: `mkdir` creates **one** level. Creating `/docs/work` requires `/docs` to exist already.

### Edge cases

- `mkdir(t, "/")` → `False`. Root already exists.
- `add_file(t, "/", size)` → `False`. Root is a directory and its path is taken.
- `get_file_size` on a **directory** is `None`; on a **zero-byte file** it is `0`. These two are different answers and both are tested. Do not collapse them with a falsy check.
- Any path whose walk passes *through* a file (`/a.txt/b.txt`) fails, because a file has no children.

### Worked examples

```python
fs = FileSystem()

fs.mkdir(1, '/docs')                        # -> True
fs.mkdir(2, '/docs/work')                   # -> True
fs.add_file(3, '/docs/work/b.txt', 200)     # -> True
fs.get_file_size(4, '/docs/work/b.txt')     # -> 200

fs.mkdir(5, '/docs')                        # -> False  (already exists)
fs.mkdir(6, '/')                            # -> False  (root always exists)
fs.add_file(7, '/', 10)                     # -> False  (root is taken, and is a dir)
fs.mkdir(8, '/nope/deeper')                 # -> False  (parent missing; not recursive)
fs.add_file(9, '/nope/a.txt', 1)            # -> False  (parent missing)
fs.add_file(10, '/docs/work/b.txt', 999)    # -> False  (taken)
fs.get_file_size(11, '/docs/work/b.txt')    # -> 200    (999 was NOT written)
```

```python
fs = FileSystem()
fs.mkdir(1, '/docs')                        # -> True
fs.add_file(2, '/empty.txt', 0)             # -> True

fs.get_file_size(3, '/empty.txt')           # -> 0      a real, empty file
fs.get_file_size(3, '/docs')                # -> None   a directory
fs.get_file_size(3, '/ghost.txt')           # -> None   nothing there

fs.add_file(4, '/empty.txt/child.txt', 5)   # -> False  parent is a file
fs.mkdir(5, '/empty.txt')                   # -> False  path taken by a file
fs.add_file(6, '/docs', 5)                  # -> False  path taken by a directory
```

---

# Level 2 — Aggregation over the tree

**~20 minutes · 150 points**

The Level 1 methods keep working unchanged. Add two queries that summarise a whole subtree.

### Methods

```python
get_dir_size(timestamp: int, path: str) -> Optional[int]
find_largest_file(timestamp: int, path: str) -> Optional[str]
```

### Contracts

| Method | Returns |
|---|---|
| `get_dir_size` | The **sum of the sizes of every file in the subtree rooted at `path`**, at any depth. An empty directory is `0`. `None` if `path` does not exist **or is a file**. |
| `find_largest_file` | The **full absolute path** of the largest file anywhere in the subtree rooted at `path`. `None` if `path` does not exist, is a file, or its subtree contains no files at all. |

**Tie-break for `find_largest_file`:** among files of equal maximum size, return the **lexicographically smallest full path** — not the smallest file *name*. `"/a/z.txt"` beats `"/b/a.txt"` because `"/a/z.txt" < "/b/a.txt"` as strings, even though `a.txt < z.txt`.

### Edge cases

- `get_dir_size(t, "/")` on a brand-new `FileSystem()` → `0`, **not** `None`. Root exists and is empty.
- `get_dir_size` on a file path → `None`. It is a directory query; a file is not a directory. (If you want a file's size, that is `get_file_size`.)
- Directories contribute no bytes themselves; only files have sizes.
- `find_largest_file` searches the **entire subtree**, not just the immediate children.
- A file directly under root formats as `"/name"` — one slash, not two. Watch the join when the base path is `"/"`.
- Zero-byte files still count as files: a directory containing only zero-byte files returns one of them, not `None`.

### Worked examples

The tree used below:

```
/
├── docs/
│   ├── work/
│   │   ├── b.txt      200
│   │   └── notes.txt   50
│   ├── a.txt          100
│   └── empty/
├── media/
│   └── pic.png        900
└── readme.md           10
```

```python
fs.get_dir_size(3, '/docs/work')     # -> 250     200 + 50
fs.get_dir_size(3, '/docs')          # -> 350     250 + 100, /docs/empty adds nothing
fs.get_dir_size(3, '/')              # -> 1260    every file in the tree
fs.get_dir_size(3, '/docs/empty')    # -> 0       empty directory, not None
fs.get_dir_size(3, '/docs/a.txt')    # -> None    that is a file
fs.get_dir_size(3, '/nope')          # -> None    missing

FileSystem().get_dir_size(0, '/')    # -> 0       empty file system
```

```python
fs.find_largest_file(3, '/')            # -> '/media/pic.png'
fs.find_largest_file(3, '/docs')        # -> '/docs/work/b.txt'   two levels down
fs.find_largest_file(3, '/docs/empty')  # -> None                 no files
fs.find_largest_file(3, '/docs/a.txt')  # -> None                 not a directory
fs.find_largest_file(3, '/nope')        # -> None
```

```python
# The tie-break is on the FULL PATH, not the file name.
fs = FileSystem()
fs.mkdir(1, '/a')
fs.mkdir(1, '/b')
fs.add_file(2, '/a/z.txt', 100)
fs.add_file(2, '/b/a.txt', 100)

fs.find_largest_file(3, '/')            # -> '/a/z.txt'
# Picking the smallest file NAME would have answered '/b/a.txt'. That is wrong.
```

---

# Level 3 — Move and copy

**~30 minutes · 150 points**

Levels 1 and 2 keep working unchanged. Assets get reorganised: relocate and duplicate arbitrary parts of the tree.

### Methods

```python
move(timestamp: int, src: str, dst: str) -> bool
copy(timestamp: int, src: str, dst: str) -> bool
```

### Contracts

| Method | Returns |
|---|---|
| `move` | `True` if `src` (a file or a directory, with its **entire subtree**) was relocated so that its new full path is exactly `dst`. `src` no longer exists afterwards. `False` otherwise. |
| `copy` | `True` if a **deep copy** of `src` was created at `dst`, leaving `src` in place. The clone shares nothing with the original: later changes on either side are invisible to the other. `False` otherwise. |

`dst` is the **new full path of the thing being moved**, not the directory to move it into. `move(t, "/docs/a.txt", "/media/renamed.txt")` produces `/media/renamed.txt`, not `/media/renamed.txt/a.txt`.

### Both methods return `False` when

1. `src` does not exist.
2. `dst` **already** exists (as a file or a directory). There is no implicit overwrite and no auto-rename. **This is also why `src == dst` fails** — `dst` exists.
3. `dst`'s parent directory does not exist. Like `mkdir`, this is not recursive.
4. `dst`'s parent exists but is a **file**.
5. `src` is root (`"/"`), or `dst` is root. Root cannot be relocated, duplicated, or replaced.
6. `dst` lies **inside the subtree of `src`**. Moving `/docs` to `/docs/work/docs` would detach the tree from itself; copying it would recurse forever. Both are `False`.

Note that "inside the subtree" is a **component-wise** test, not a string-prefix test: `/ab/moved` is *not* inside `/a`, even though `"/ab/moved".startswith("/a")`.

And, restating the global rule because it is where the points are: **a `False` from `move` or `copy` must leave the file system completely unchanged.** No partially detached subtree, no half-written clone.

### Where the time goes

`move` and `copy` each resolve **two** paths and split a target into `(parent directory, final name)`. If you wrote that walk inline in each of `mkdir`, `add_file` and `get_file_size` at Level 1, you are now writing it for the fifth and sixth time, at minute fifty, with a timer running. If you extracted `_resolve(path)` and `_parent_and_name(path)` at Level 1, each of these methods is about six lines. That is the whole exam.

### Worked examples

Starting from the Level 2 tree each time.

```python
fs.move(3, '/docs/a.txt', '/media/renamed.txt')   # -> True
fs.get_file_size(4, '/docs/a.txt')                # -> None    gone from the old place
fs.get_file_size(4, '/media/renamed.txt')         # -> 100     with its size intact

fs.move(5, '/docs/work', '/work')                 # -> True    the subtree travels
fs.get_file_size(6, '/work/b.txt')                # -> 200
fs.get_dir_size(6, '/docs')                       # -> 0       only /docs/empty is left
fs.get_dir_size(6, '/docs/work')                  # -> None    no longer a directory
fs.get_dir_size(6, '/')                           # -> 1260    a move conserves bytes
```

```python
fs.mkdir(3, '/backup')                            # -> True
fs.copy(4, '/docs', '/backup/docs')               # -> True
fs.get_file_size(5, '/backup/docs/work/b.txt')    # -> 200
fs.get_dir_size(5, '/backup/docs')                # -> 350
fs.get_dir_size(5, '/backup/docs/empty')          # -> 0       empty dirs are cloned too

# The clone is deep: writing into it does not touch the original.
fs.add_file(6, '/backup/docs/work/extra.txt', 5000)   # -> True
fs.get_dir_size(7, '/backup/docs')                    # -> 5350
fs.get_dir_size(7, '/docs')                           # -> 350   unchanged
fs.get_file_size(7, '/docs/work/extra.txt')           # -> None
```

```python
# Every failure mode, and the proof that none of them touched the tree.
fs.move(3, '/docs/a.txt', '/docs/a.txt')      # -> False   src == dst, so dst exists
fs.move(3, '/docs/a.txt', '/media/pic.png')   # -> False   dst exists
fs.move(3, '/docs/a.txt', '/backup/a.txt')    # -> False   dst parent missing
fs.move(3, '/docs/a.txt', '/readme.md/a.txt') # -> False   dst parent is a file
fs.move(3, '/', '/docs/root')                 # -> False   cannot move root
fs.move(3, '/docs', '/')                      # -> False   cannot move onto root
fs.move(3, '/docs', '/docs/work/docs')        # -> False   into its own subtree
fs.copy(3, '/docs', '/docs/work/docs')        # -> False   same rule for copy
fs.move(3, '/ghost.txt', '/docs/g.txt')       # -> False   src missing

fs.get_dir_size(4, '/')                       # -> 1260    nothing moved
fs.get_dir_size(4, '/docs')                   # -> 350
fs.get_file_size(4, '/docs/a.txt')            # -> 100
```

---

# Level 4 — Backward-compatible export

**~30 minutes · 200 points**

**Levels 1, 2 and 3 keep working unchanged.** One report method: every file in a subtree at or above a size threshold, rendered as a single string.

### Methods

```python
find_files_by_size(timestamp: int, path: str, threshold: int) -> str
```

### Output format

The return value is a **string**, not a list:

```
"path1(size1), path2(size2), ..."
```

Each entry is the file's **full absolute path** immediately followed by its size in parentheses, with **no space inside the entry**. Entries are separated by a **comma and a space**. There is no trailing separator, no enclosing brackets, no quoting.

```
"/docs/a.txt(100), /media/pic.png(900)"
```

### Contracts

| Method | Returns |
|---|---|
| `find_files_by_size` | Every file in the subtree rooted at `path` whose size is **`>= threshold`**, at **any** depth, sorted by **full path ascending**, each rendered `"path(size)"` and joined with `", "`. The **empty string** `""` if no file in the subtree matches, if `path` does not exist, or if `path` exists but **is a file**. |

### The return type has no `None` — every failure is `""`

This is the one place where this level looks inconsistent with the rest of the exam, and it is deliberate. Everywhere else, "not a directory" reads back as `None`: `get_dir_size(t, "/readme.md")` is `None`, `find_largest_file(t, "/readme.md")` is `None`. Here the declared return type is `str`, so there is nowhere for a `None` to go, and **all three failure modes collapse onto the same value**:

| Situation | `get_dir_size` | `find_files_by_size` |
|---|---|---|
| `path` does not exist | `None` | `""` |
| `path` is a **file** | `None` | `""` |
| `path` is a directory with no matching files | `0` | `""` |

So `""` is genuinely ambiguous — "no such directory" and "directory with nothing big enough" are the same answer. Do not invent a distinction the signature cannot carry. Return `""` and move on.

### Edge cases

- The threshold is **inclusive**: a file of exactly `threshold` bytes is in; `threshold - 1` bytes is out.
- `threshold <= 0` matches **every** file in the subtree, zero-byte files included. Negative thresholds are legal and behave exactly like `0`.
- Files at **any depth** count, not just direct children — same subtree rule as `get_dir_size`.
- A directory containing only subdirectories, all of them empty of files, is `""`.
- `find_files_by_size(t, "/", 0)` on a brand-new `FileSystem()` is `""`. Compare `get_dir_size(t, "/")`, which is `0` there.
- Sorting is on the **full path**, not the file name and not the size — the same rule as the Level 2 tie-break. `"/a/z.txt"` comes before `"/b/a.txt"`.
- **Sort the paths, then format.** Sorting the rendered `"path(size)"` strings is a different ordering. `(` is `0x28`; every letter, every digit, `.`, `-`, `_` (smallest of those is `-`, `0x2D`) and `/` (`0x2F`) are all **above** it, so with ordinary file names the two orders happen to agree — which is exactly why getting this wrong is invisible until it is not. They come apart when one file's path is a proper prefix of another's and the longer one continues with a character **below** `0x28` — a space, `!`, `"`, `#`, `$`, `%`, `&`, `'`. `/media/hero` and `/media/hero!2.jpg` are such a pair: by path the short one sorts first, by rendered string it sorts second. Sort the path field and format afterwards; it is right in both cases and costs nothing.
- A file directly under root renders as `"/name(size)"` — one slash. The same root-join trap as Level 2, except here a wrong join is visible in the output string instead of being swallowed by a sum.
- `timestamp` is still semantically unused. It is unused at every level of this problem, this one included.

### Where the time goes

Nowhere, if Level 2 was factored. `get_dir_size` and `find_largest_file` both need "every `(full_path, file)` in this subtree"; if you wrote that once as a generator, this level is a filter, a sort and a `", ".join` over it. If you instead wrote two ad-hoc recursions that each accumulate into their own local, you are writing the subtree walk a third time at minute seventy — and this time the path-join bug shows up in the graded string.

### Worked examples

The Level 2 tree again:

```
/
├── docs/
│   ├── work/
│   │   ├── b.txt      200
│   │   └── notes.txt   50
│   ├── a.txt          100
│   └── empty/
├── media/
│   └── pic.png        900
└── readme.md           10
```

```python
fs.find_files_by_size(3, '/', 100)
# -> '/docs/a.txt(100), /docs/work/b.txt(200), /media/pic.png(900)'

fs.find_files_by_size(3, '/', 0)
# -> '/docs/a.txt(100), /docs/work/b.txt(200), /docs/work/notes.txt(50), /media/pic.png(900), /readme.md(10)'

fs.find_files_by_size(3, '/docs', 50)
# -> '/docs/a.txt(100), /docs/work/b.txt(200), /docs/work/notes.txt(50)'
fs.find_files_by_size(3, '/docs', 51)
# -> '/docs/a.txt(100), /docs/work/b.txt(200)'
fs.find_files_by_size(3, '/docs/work', 200)   # -> '/docs/work/b.txt(200)'   inclusive

fs.find_files_by_size(3, '/', 901)            # -> ''    nothing is that big
fs.find_files_by_size(3, '/docs/empty', 0)    # -> ''    a directory with no files
fs.find_files_by_size(3, '/docs/a.txt', 0)    # -> ''    that is a file, not a directory
fs.find_files_by_size(3, '/nope', 0)          # -> ''    missing

FileSystem().find_files_by_size(0, '/', 0)    # -> ''    empty file system
```

```python
# The threshold is inclusive, and threshold <= 0 takes everything.
fs = FileSystem()
fs.mkdir(1, '/logs')
fs.add_file(2, '/logs/a.log', 100)
fs.add_file(3, '/logs/b.log', 99)
fs.add_file(4, '/logs/c.log', 0)

fs.find_files_by_size(5, '/logs', 100)   # -> '/logs/a.log(100)'                       exactly at
fs.find_files_by_size(5, '/logs', 101)   # -> ''                                       one above
fs.find_files_by_size(5, '/logs', 99)    # -> '/logs/a.log(100), /logs/b.log(99)'      one below
fs.find_files_by_size(5, '/logs', 0)     # -> '/logs/a.log(100), /logs/b.log(99), /logs/c.log(0)'
fs.find_files_by_size(5, '/logs', -1)    # -> '/logs/a.log(100), /logs/b.log(99), /logs/c.log(0)'
```

```python
# Sorting is on the full path -- exactly the Level 2 tie-break rule.
fs = FileSystem()
fs.mkdir(1, '/a')
fs.mkdir(1, '/b')
fs.add_file(2, '/a/z.txt', 100)
fs.add_file(2, '/b/a.txt', 100)

fs.find_files_by_size(3, '/', 100)       # -> '/a/z.txt(100), /b/a.txt(100)'
# Sorting by file NAME would have answered '/b/a.txt(100), /a/z.txt(100)'. That is wrong.
```

```python
# It must agree with Level 3: report the CURRENT paths, and both sides of a copy.
fs = <the Level 2 tree>
fs.move(4, '/docs/work', '/work')             # -> True
fs.find_files_by_size(5, '/', 100)
# -> '/docs/a.txt(100), /media/pic.png(900), /work/b.txt(200)'
#    b.txt is reported at its NEW path, and '/docs/work/b.txt' appears nowhere.
fs.find_files_by_size(5, '/work', 0)          # -> '/work/b.txt(200), /work/notes.txt(50)'
fs.find_files_by_size(5, '/docs', 0)          # -> '/docs/a.txt(100)'

fs = <the Level 2 tree>
fs.mkdir(4, '/backup')                        # -> True
fs.copy(5, '/docs', '/backup/docs')           # -> True
fs.find_files_by_size(6, '/', 100)
# -> '/backup/docs/a.txt(100), /backup/docs/work/b.txt(200), /docs/a.txt(100), /docs/work/b.txt(200), /media/pic.png(900)'
#    Both the clone and the original are reported, each at its own path.
```

---

<a id="spec-decisions"></a>
## Spec decisions

The source statement leaves these underspecified. This exam pins them down; every one is enforced by at least one test. The level column tells you when it becomes relevant.

| # | L | Decision |
|---|---|---|
| 1 | — | **Path format.** Paths are always absolute, always start with `"/"`, and never have a trailing slash except root itself, which is exactly `"/"`. Components are non-empty. Malformed paths are out of contract and are not tested; do not write defensive parsing for them. |
| 2 | 1 | **Root cannot be re-created.** `mkdir(t, "/")` → `False` (it already exists). `add_file(t, "/", size)` → `False`. |
| 3 | 1 | **Directory vs empty file.** `get_file_size` on a directory is `None`; on a zero-byte file it is `0`. Both cases exist and must be distinguishable — a truthiness check conflates them. |
| 4 | 2 | **Empty root has size 0.** `get_dir_size(t, "/")` on a fresh `FileSystem()` is `0`, not `None`. Root exists; it is merely empty. |
| 5 | 2 | **Largest-file tie-break is the full path.** `find_largest_file` considers files at **any** depth in the subtree, and ties on size are broken by the lexicographically smallest **full path**, not the smallest file name. `/a/z.txt` beats `/b/a.txt`. |
| 6 | 3 | **`move(t, p, p)` is `False`**, because `dst` already exists. There is no "no-op success". |
| 7 | 3 | **A directory cannot be moved into its own subtree** → `False`, **and the tree is unchanged afterwards**. Detaching the subtree and only then discovering the problem is a failure even if the return value is right. |
| 8 | 3 | **`copy` into the source's own subtree is `False` too** — "same constraints as `move`". Stated explicitly because a naive recursive copy would otherwise clone into what it is still traversing and never terminate. |
| 9 | 3 | **`dst`'s parent existing is not enough — it must be a directory.** If `dst`'s parent is a file, `move` and `copy` both return `False`. |
| 10 | 3 | **Root is not relocatable.** `move`/`copy` with `src == "/"` → `False`; with `dst == "/"` → `False` (it exists). |
| 11 | 3 | **A copy is deep.** After `copy`, mutating the clone must not affect the source and vice versa. Adding a file under the copied directory must leave the original's `get_dir_size` unchanged. |
| 12 | all | **`timestamp` is accepted by every method and is semantically unused** — Level 4 included. Nothing expires, nothing is versioned, no read targets a past instant. Timestamps arrive non-decreasing; the parameter exists only to keep the signatures consistent with the ICF framework. There is no hidden time trick. |
| 13 | 4 | **Every `find_files_by_size` failure is `""`.** The declared return type is `str`, so there is no `None` to return: a missing `path` is `""` **and a `path` that is a file is `""`**, even though the same two situations are `None` for `get_dir_size` and `find_largest_file`. The inconsistency is in the signature, not in your reading of it. |
| 14 | 4 | **The threshold is inclusive.** The predicate is `size >= threshold`. A file of exactly `threshold` bytes is included; one byte below is not. |
| 15 | 4 | **`threshold <= 0` matches every file in the subtree**, zero-byte files included. Negative thresholds are legal and behave exactly like `0`. |
| 16 | 4 | **Results are sorted by full path ascending**, plain Python string ordering — not by file name, not by size, not by insertion order. Same rule as decision 5. |
| 17 | 4 | **Sort the path, then format.** Sorting the rendered `"path(size)"` strings is a genuinely different order, not a hypothetical one: `(` is `0x28`, below `/` (`0x2F`) and below every letter and digit, so when one file path is a proper prefix of another and the longer one continues with a character below `0x28` (space, `!`, `"`, `#`, `$`, `%`, `&`, `'`), the two orders disagree — e.g. `/media/hero(100)` vs `/media/hero!2.jpg(50)`. With names drawn only from letters, digits, `.`, `-` and `_` the orders always agree, which is exactly why this one is easy to get wrong and never notice. |
| 18 | 4 | **The separator is `", "` — comma *and* space**, with no trailing separator and no brackets. An empty result is the empty string, not `"()"`, not `" "`, not `"[]"`. |
| 19 | 4 | **Files at any depth are included**, not just the direct children of `path`. Same subtree semantics as `get_dir_size`. |
| 20 | 4 | **No files means `""`.** An empty file system, an empty directory, and a directory whose subtree holds only other directories all return `""` — as does a subtree whose files are all below the threshold. |

Level 4 changes nothing about Levels 1–3: `find_files_by_size` is a pure query. After a `move` it must report files at their **new** paths; after a `copy` it must report the original **and** the clone.

---

## Scoring

| Level | Points | Target time |
|---|---|---|
| 1 — Core operations | 100 | 10 min |
| 2 — Aggregation over the tree | 150 | 20 min |
| 3 — Move and copy | 150 | 30 min |
| 4 — Backward-compatible export | 200 | 30 min |
| **Total** | **600** | **90 min** |

Every earlier level must still be green at the end. A Level 3 that breaks Level 1 scores 250, not 400. The passing bar for a senior offer is roughly **all of L1–L3 plus a working L4**.

## After the exam

Read the module docstring at the top of `solution.py` before you read its code.

This mock's lesson is deliberately different from the rest of the kit. The other mocks are won by picking the right *storage* shape at Level 1 — an event log, an interval list, a fallback chain — and their Level 4s punish you for having stored current state where a history was needed. There is nothing like that here: no time dimension, no history, no expiry. The tree is the obvious tree and nobody loses on the data structure.

You lose this one on **repetition**, and there are two separate repetitions to lose it on.

The first is **path resolution**. Eight public methods all begin by turning a path string into a node, and four of them also need to split a target into `(parent, name)`. If you extracted `_resolve(path)` and `_parent_and_name(path)` before you finished `mkdir`, Level 3 is two short methods. If you inlined `path.split("/")` into all three Level 1 methods because it was only four lines, you write that walk for the fifth and sixth time at minute fifty, and the off-by-one on the root path finds you there.

The second is **the subtree walk**, and Level 4 is where it is scored. `get_dir_size` and `find_largest_file` both need "every `(full_path, file)` under this node, at any depth, with the full path built as you descend". Write that once as `_walk_files(node, path)` at minute twenty-five and `find_files_by_size` is a filter, a sort and a `", ".join` on top of it — ten lines, no new traversal. Write two ad-hoc recursions instead, each accumulating into its own local, each re-deriving the child path with its own `"/" + name` join, and Level 4 is a third recursion at minute seventy — with the root-join bug now printing `"//pic.png"` straight into the graded output string instead of quietly disappearing into a sum.

So the question to ask yourself afterwards is not "did I pick the right structure" — it is **how many times did I write the same eight lines**, and at what point in the ninety minutes did I write them for the last time.
