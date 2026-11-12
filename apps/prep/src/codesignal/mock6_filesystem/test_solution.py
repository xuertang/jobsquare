"""Test suite for ICF Mock 6 -- FileSystem.

Run everything:        python3 -m pytest -q
Run one level:         python3 -m pytest -q -m level1
Test your own attempt: ICF_IMPL=attempt python3 -m pytest -q -m level1
"""

import importlib
import os

import pytest

_impl = importlib.import_module(os.environ.get("ICF_IMPL", "solution"))
FileSystem = _impl.FileSystem


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

T = 0  # timestamps are semantically unused in Levels 1-3


def snapshot(fs, paths):
    """A public-API-only dump of the tree: every observable fact about `paths`.

    Used to assert that a *failed* mutation left the file system byte-identical.
    """
    return {
        path: (
            fs.get_file_size(0, path),
            fs.get_dir_size(0, path),
            fs.find_largest_file(0, path),
        )
        for path in paths
    }


def build_tree(fs):
    """A small fixed tree used by several levels.

    /
      docs/            (dir)
        work/          (dir)
          b.txt        200
          notes.txt     50
        a.txt          100
        empty/         (dir)
      media/           (dir)
        pic.png        900
      readme.md         10
    """
    fs.mkdir(T, "/docs")
    fs.mkdir(T, "/docs/work")
    fs.mkdir(T, "/docs/empty")
    fs.mkdir(T, "/media")
    fs.add_file(T, "/docs/work/b.txt", 200)
    fs.add_file(T, "/docs/work/notes.txt", 50)
    fs.add_file(T, "/docs/a.txt", 100)
    fs.add_file(T, "/media/pic.png", 900)
    fs.add_file(T, "/readme.md", 10)
    return fs


TREE_PATHS = [
    "/",
    "/docs",
    "/docs/work",
    "/docs/work/b.txt",
    "/docs/work/notes.txt",
    "/docs/a.txt",
    "/docs/empty",
    "/media",
    "/media/pic.png",
    "/readme.md",
    # Paths that must stay absent.
    "/backup",
    "/backup/work",
    "/docs/work/work",
    "/nope.txt",
]


# ======================================================================
# Level 1 -- mkdir, add_file, get_file_size
# ======================================================================


@pytest.mark.level1
def test_mkdir_then_add_file_then_read_size():
    fs = FileSystem()
    assert fs.mkdir(1, "/docs") is True
    assert fs.add_file(2, "/docs/a.txt", 100) is True
    assert fs.get_file_size(3, "/docs/a.txt") == 100


@pytest.mark.level1
def test_mkdir_on_root_returns_false_because_root_already_exists():
    fs = FileSystem()
    assert fs.mkdir(1, "/") is False


@pytest.mark.level1
def test_add_file_at_root_path_returns_false():
    fs = FileSystem()
    assert fs.add_file(1, "/", 10) is False


@pytest.mark.level1
def test_mkdir_duplicate_directory_returns_false():
    fs = FileSystem()
    fs.mkdir(1, "/docs")
    assert fs.mkdir(2, "/docs") is False


@pytest.mark.level1
def test_mkdir_over_an_existing_file_returns_false():
    fs = FileSystem()
    fs.add_file(1, "/a.txt", 5)
    assert fs.mkdir(2, "/a.txt") is False
    assert fs.get_file_size(3, "/a.txt") == 5


@pytest.mark.level1
def test_mkdir_with_missing_parent_returns_false():
    fs = FileSystem()
    assert fs.mkdir(1, "/docs/work") is False
    assert fs.get_file_size(2, "/docs/work") is None


@pytest.mark.level1
def test_mkdir_whose_parent_is_a_file_returns_false():
    fs = FileSystem()
    fs.add_file(1, "/a.txt", 5)
    assert fs.mkdir(2, "/a.txt/inner") is False


@pytest.mark.level1
def test_add_file_duplicate_returns_false_and_does_not_overwrite_the_size():
    fs = FileSystem()
    fs.add_file(1, "/a.txt", 100)
    assert fs.add_file(2, "/a.txt", 999) is False
    assert fs.get_file_size(3, "/a.txt") == 100


@pytest.mark.level1
def test_add_file_over_an_existing_directory_returns_false():
    fs = FileSystem()
    fs.mkdir(1, "/docs")
    assert fs.add_file(2, "/docs", 10) is False


@pytest.mark.level1
def test_add_file_with_missing_parent_returns_false():
    fs = FileSystem()
    assert fs.add_file(1, "/docs/a.txt", 100) is False
    assert fs.get_file_size(2, "/docs/a.txt") is None


@pytest.mark.level1
def test_add_file_whose_parent_is_a_file_returns_false():
    fs = FileSystem()
    fs.add_file(1, "/a.txt", 5)
    assert fs.add_file(2, "/a.txt/b.txt", 5) is False


@pytest.mark.level1
def test_get_file_size_on_missing_path_returns_none():
    fs = FileSystem()
    assert fs.get_file_size(1, "/nope.txt") is None
    assert fs.get_file_size(1, "/a/b/c/nope.txt") is None


@pytest.mark.level1
def test_get_file_size_on_a_directory_is_none_not_zero():
    """Spec decision 3: a directory and a zero-byte file must be distinguishable."""
    fs = FileSystem()
    fs.mkdir(1, "/docs")
    fs.add_file(2, "/empty.txt", 0)
    assert fs.get_file_size(3, "/docs") is None
    assert fs.get_file_size(3, "/empty.txt") == 0
    assert fs.get_file_size(3, "/docs") != fs.get_file_size(3, "/empty.txt")


@pytest.mark.level1
def test_deeply_nested_directories_and_a_file_at_the_bottom():
    fs = FileSystem()
    for depth in range(1, 7):
        path = "/" + "/".join(f"d{level}" for level in range(1, depth + 1))
        assert fs.mkdir(depth, path) is True
    deep = "/d1/d2/d3/d4/d5/d6/leaf.txt"
    assert fs.add_file(10, deep, 42) is True
    assert fs.get_file_size(11, deep) == 42


@pytest.mark.level1
def test_same_name_may_exist_under_different_parents():
    fs = FileSystem()
    fs.mkdir(1, "/left")
    fs.mkdir(1, "/right")
    assert fs.mkdir(2, "/left/shared") is True  # a directory here...
    assert fs.add_file(3, "/right/shared", 77) is True  # ...and a file there
    assert fs.get_file_size(4, "/left/shared") is None
    assert fs.get_file_size(4, "/right/shared") == 77


@pytest.mark.level1
def test_timestamps_are_accepted_but_semantically_unused():
    """Spec decision 12: nothing in Levels 1-3 depends on the timestamp value."""
    fs = FileSystem()
    assert fs.mkdir(10**9, "/docs") is True
    assert fs.add_file(0, "/docs/a.txt", 5) is True
    assert fs.get_file_size(-100, "/docs/a.txt") == 5
    assert fs.get_file_size(10**12, "/docs/a.txt") == 5


# ======================================================================
# Level 2 -- get_dir_size and find_largest_file
# ======================================================================


@pytest.mark.level2
def test_get_dir_size_of_empty_root_is_zero_not_none():
    """Spec decision 4."""
    assert FileSystem().get_dir_size(1, "/") == 0


@pytest.mark.level2
def test_get_dir_size_of_an_empty_subdirectory_is_zero():
    fs = build_tree(FileSystem())
    assert fs.get_dir_size(1, "/docs/empty") == 0


@pytest.mark.level2
def test_get_dir_size_sums_the_whole_subtree_at_any_depth():
    fs = build_tree(FileSystem())
    assert fs.get_dir_size(1, "/docs/work") == 250
    assert fs.get_dir_size(1, "/docs") == 350
    assert fs.get_dir_size(1, "/media") == 900


@pytest.mark.level2
def test_get_dir_size_of_root_counts_every_file_in_the_tree():
    fs = build_tree(FileSystem())
    assert fs.get_dir_size(1, "/") == 1260


@pytest.mark.level2
def test_get_dir_size_on_a_file_returns_none():
    fs = build_tree(FileSystem())
    assert fs.get_dir_size(1, "/docs/a.txt") is None


@pytest.mark.level2
def test_get_dir_size_on_a_missing_path_returns_none():
    fs = build_tree(FileSystem())
    assert fs.get_dir_size(1, "/nope") is None
    assert fs.get_dir_size(1, "/docs/work/nope/deeper") is None


@pytest.mark.level2
def test_get_dir_size_reflects_files_added_later():
    fs = build_tree(FileSystem())
    fs.add_file(2, "/docs/empty/late.txt", 7)
    assert fs.get_dir_size(3, "/docs/empty") == 7
    assert fs.get_dir_size(3, "/docs") == 357


@pytest.mark.level2
def test_find_largest_file_returns_a_full_path_from_the_whole_subtree():
    fs = build_tree(FileSystem())
    assert fs.find_largest_file(1, "/") == "/media/pic.png"
    assert fs.find_largest_file(1, "/docs") == "/docs/work/b.txt"
    assert fs.find_largest_file(1, "/docs/work") == "/docs/work/b.txt"


@pytest.mark.level2
def test_find_largest_file_is_scoped_to_the_given_subtree():
    fs = build_tree(FileSystem())
    # /media/pic.png is the biggest overall but invisible from inside /docs/work.
    assert fs.find_largest_file(1, "/docs/work") == "/docs/work/b.txt"


@pytest.mark.level2
def test_find_largest_file_of_a_root_level_file_has_a_single_slash():
    fs = FileSystem()
    fs.add_file(1, "/solo.txt", 3)
    assert fs.find_largest_file(2, "/") == "/solo.txt"


@pytest.mark.level2
def test_find_largest_file_ties_break_on_the_full_path_not_the_file_name():
    """Spec decision 5: the naive 'smallest file name' tie-break is wrong."""
    fs = FileSystem()
    fs.mkdir(1, "/a")
    fs.mkdir(1, "/b")
    fs.add_file(2, "/a/z.txt", 100)
    fs.add_file(2, "/b/a.txt", 100)
    # Smallest *name* would be "a.txt" -> "/b/a.txt". Smallest *path* wins.
    assert fs.find_largest_file(3, "/") == "/a/z.txt"


@pytest.mark.level2
def test_find_largest_file_ties_break_across_different_depths():
    fs = FileSystem()
    fs.mkdir(1, "/x")
    fs.mkdir(1, "/x/deep")
    fs.add_file(2, "/x/deep/aaa.txt", 500)
    fs.add_file(2, "/x/zzz.txt", 500)
    assert fs.find_largest_file(3, "/x") == "/x/deep/aaa.txt"


@pytest.mark.level2
def test_find_largest_file_on_an_empty_directory_returns_none():
    fs = build_tree(FileSystem())
    assert fs.find_largest_file(1, "/docs/empty") is None


@pytest.mark.level2
def test_find_largest_file_on_an_empty_file_system_returns_none():
    assert FileSystem().find_largest_file(1, "/") is None


@pytest.mark.level2
def test_find_largest_file_on_a_file_or_missing_path_returns_none():
    fs = build_tree(FileSystem())
    assert fs.find_largest_file(1, "/docs/a.txt") is None
    assert fs.find_largest_file(1, "/nope") is None


@pytest.mark.level2
def test_find_largest_file_still_reports_zero_byte_files():
    fs = FileSystem()
    fs.mkdir(1, "/z")
    fs.add_file(2, "/z/b.txt", 0)
    fs.add_file(2, "/z/a.txt", 0)
    assert fs.find_largest_file(3, "/z") == "/z/a.txt"


# ======================================================================
# Level 3 -- move and copy
# ======================================================================


@pytest.mark.level3
def test_move_a_file_to_a_new_name_in_another_directory():
    fs = build_tree(FileSystem())
    assert fs.move(1, "/docs/a.txt", "/media/renamed.txt") is True
    assert fs.get_file_size(2, "/docs/a.txt") is None
    assert fs.get_file_size(2, "/media/renamed.txt") == 100
    assert fs.get_dir_size(2, "/docs") == 250
    assert fs.get_dir_size(2, "/media") == 1000


@pytest.mark.level3
def test_move_a_directory_relocates_its_whole_subtree():
    fs = build_tree(FileSystem())
    assert fs.move(1, "/docs/work", "/media/work") is True
    assert fs.get_file_size(2, "/media/work/b.txt") == 200
    assert fs.get_file_size(2, "/docs/work/b.txt") is None
    assert fs.get_dir_size(2, "/docs") == 100
    assert fs.get_dir_size(2, "/media") == 1150
    assert fs.get_dir_size(2, "/docs/work") is None


@pytest.mark.level3
def test_move_a_directory_upward_to_the_root():
    fs = build_tree(FileSystem())
    assert fs.move(1, "/docs/work", "/work") is True
    assert fs.find_largest_file(2, "/work") == "/work/b.txt"
    assert fs.get_dir_size(2, "/") == 1260


@pytest.mark.level3
def test_move_of_a_missing_source_returns_false():
    fs = build_tree(FileSystem())
    assert fs.move(1, "/nope.txt", "/docs/nope.txt") is False


@pytest.mark.level3
def test_move_onto_an_existing_destination_returns_false():
    fs = build_tree(FileSystem())
    assert fs.move(1, "/docs/a.txt", "/media/pic.png") is False
    assert fs.get_file_size(2, "/docs/a.txt") == 100
    assert fs.get_file_size(2, "/media/pic.png") == 900


@pytest.mark.level3
def test_move_to_the_same_path_returns_false():
    """Spec decision 6: src == dst means dst already exists."""
    fs = build_tree(FileSystem())
    assert fs.move(1, "/docs/a.txt", "/docs/a.txt") is False
    assert fs.move(1, "/docs", "/docs") is False
    assert fs.get_file_size(2, "/docs/a.txt") == 100


@pytest.mark.level3
def test_move_whose_destination_parent_is_missing_returns_false():
    fs = build_tree(FileSystem())
    assert fs.move(1, "/docs/a.txt", "/backup/a.txt") is False
    assert fs.get_file_size(2, "/docs/a.txt") == 100


@pytest.mark.level3
def test_move_whose_destination_parent_is_a_file_returns_false():
    """Spec decision 9."""
    fs = build_tree(FileSystem())
    assert fs.move(1, "/docs/a.txt", "/readme.md/a.txt") is False
    assert fs.move(1, "/docs/work", "/readme.md/work") is False
    assert fs.get_file_size(2, "/readme.md") == 10


@pytest.mark.level3
def test_move_of_root_or_onto_root_returns_false():
    """Spec decision 10."""
    fs = build_tree(FileSystem())
    assert fs.move(1, "/", "/docs/root") is False
    assert fs.move(1, "/docs", "/") is False
    assert fs.get_dir_size(2, "/") == 1260


@pytest.mark.level3
def test_move_a_directory_into_its_own_subtree_returns_false_and_changes_nothing():
    """Spec decision 7: the no-mutation half matters as much as the return value."""
    fs = build_tree(FileSystem())
    before = snapshot(fs, TREE_PATHS)
    assert fs.move(1, "/docs", "/docs/work/docs") is False
    assert fs.move(1, "/docs/work", "/docs/work/inner") is False
    assert snapshot(fs, TREE_PATHS) == before


@pytest.mark.level3
def test_every_failing_move_leaves_the_tree_byte_identical():
    fs = build_tree(FileSystem())
    before = snapshot(fs, TREE_PATHS)
    assert fs.move(1, "/nope.txt", "/docs/x.txt") is False
    assert fs.move(1, "/docs/a.txt", "/media/pic.png") is False
    assert fs.move(1, "/docs/a.txt", "/backup/a.txt") is False
    assert fs.move(1, "/docs/a.txt", "/readme.md/a.txt") is False
    assert fs.move(1, "/", "/docs/root") is False
    assert fs.move(1, "/docs", "/") is False
    assert snapshot(fs, TREE_PATHS) == before


@pytest.mark.level3
def test_copy_a_file_leaves_the_original_in_place():
    fs = build_tree(FileSystem())
    assert fs.copy(1, "/docs/a.txt", "/media/a-copy.txt") is True
    assert fs.get_file_size(2, "/docs/a.txt") == 100
    assert fs.get_file_size(2, "/media/a-copy.txt") == 100
    assert fs.get_dir_size(2, "/") == 1360


@pytest.mark.level3
def test_copy_a_deep_subtree_duplicates_every_file():
    fs = build_tree(FileSystem())
    assert fs.mkdir(1, "/backup") is True
    assert fs.copy(2, "/docs", "/backup/docs") is True
    assert fs.get_file_size(3, "/backup/docs/work/b.txt") == 200
    assert fs.get_file_size(3, "/backup/docs/work/notes.txt") == 50
    assert fs.get_file_size(3, "/backup/docs/a.txt") == 100
    assert fs.get_dir_size(3, "/backup/docs/empty") == 0  # empty dirs are cloned too
    assert fs.get_dir_size(3, "/backup") == 350


@pytest.mark.level3
def test_the_copy_is_deep_so_mutating_it_does_not_touch_the_source():
    """Spec decision 11."""
    fs = build_tree(FileSystem())
    fs.mkdir(1, "/backup")
    fs.copy(2, "/docs", "/backup/docs")
    assert fs.add_file(3, "/backup/docs/work/extra.txt", 5000) is True
    assert fs.get_dir_size(4, "/backup/docs") == 5350
    assert fs.get_dir_size(4, "/docs") == 350  # untouched
    assert fs.get_file_size(4, "/docs/work/extra.txt") is None
    # ...and the other direction too.
    fs.add_file(5, "/docs/work/only-original.txt", 1)
    assert fs.get_file_size(6, "/backup/docs/work/only-original.txt") is None


@pytest.mark.level3
def test_copy_into_the_sources_own_subtree_returns_false():
    """Spec decision 8: a naive recursive copy would recurse forever here."""
    fs = build_tree(FileSystem())
    before = snapshot(fs, TREE_PATHS)
    assert fs.copy(1, "/docs", "/docs/work/docs") is False
    assert fs.copy(1, "/docs/work", "/docs/work/work") is False
    assert snapshot(fs, TREE_PATHS) == before


@pytest.mark.level3
def test_every_failing_copy_leaves_the_tree_byte_identical():
    fs = build_tree(FileSystem())
    before = snapshot(fs, TREE_PATHS)
    assert fs.copy(1, "/nope.txt", "/docs/x.txt") is False
    assert fs.copy(1, "/docs/a.txt", "/media/pic.png") is False  # dst exists
    assert fs.copy(1, "/docs/a.txt", "/docs/a.txt") is False  # src == dst
    assert fs.copy(1, "/docs/a.txt", "/backup/a.txt") is False  # parent missing
    assert fs.copy(1, "/docs/a.txt", "/readme.md/a.txt") is False  # parent is a file
    assert fs.copy(1, "/", "/docs/root") is False
    assert fs.copy(1, "/docs", "/") is False
    assert snapshot(fs, TREE_PATHS) == before


@pytest.mark.level3
def test_move_then_copy_compose_normally():
    fs = build_tree(FileSystem())
    assert fs.move(1, "/docs/work", "/work") is True
    assert fs.copy(2, "/work", "/docs/work") is True
    assert fs.get_dir_size(3, "/work") == 250
    assert fs.get_dir_size(3, "/docs/work") == 250
    assert fs.find_largest_file(3, "/") == "/media/pic.png"
    assert fs.get_dir_size(3, "/") == 1510


@pytest.mark.level3
def test_a_sibling_prefix_is_not_treated_as_a_subtree():
    fs = FileSystem()
    fs.mkdir(1, "/a")
    fs.mkdir(1, "/ab")
    fs.add_file(2, "/a/f.txt", 1)
    # "/ab/moved" is not inside "/a" even though "/ab" starts with "/a".
    assert fs.move(3, "/a", "/ab/moved") is True
    assert fs.get_file_size(4, "/ab/moved/f.txt") == 1


# ======================================================================
# Level 4 -- find_files_by_size
# ======================================================================


@pytest.mark.level4
def test_find_files_by_size_lists_matching_files_sorted_by_path():
    """Spec decisions 16, 18: full-path ascending, joined with a comma and a space."""
    fs = build_tree(FileSystem())
    assert fs.find_files_by_size(1, "/", 100) == (
        "/docs/a.txt(100), /docs/work/b.txt(200), /media/pic.png(900)"
    )


@pytest.mark.level4
def test_find_files_by_size_is_scoped_to_the_subtree_and_reaches_any_depth():
    """Spec decision 19: files at any depth, but only inside `path`."""
    fs = build_tree(FileSystem())
    # /docs/work/* is two levels down and still reported; /media/pic.png is not.
    assert fs.find_files_by_size(1, "/docs", 0) == (
        "/docs/a.txt(100), /docs/work/b.txt(200), /docs/work/notes.txt(50)"
    )
    assert fs.find_files_by_size(1, "/docs/work", 0) == (
        "/docs/work/b.txt(200), /docs/work/notes.txt(50)"
    )
    assert "pic.png" not in fs.find_files_by_size(1, "/docs", 0)


@pytest.mark.level4
def test_the_threshold_is_inclusive():
    """Spec decision 14: the predicate is size >= threshold, not size > threshold."""
    fs = FileSystem()
    fs.mkdir(1, "/logs")
    fs.add_file(2, "/logs/a.log", 100)
    fs.add_file(3, "/logs/b.log", 99)
    assert fs.find_files_by_size(4, "/logs", 100) == "/logs/a.log(100)"  # exactly at
    assert fs.find_files_by_size(4, "/logs", 101) == ""  # one above the largest
    assert fs.find_files_by_size(4, "/logs", 99) == (  # one below
        "/logs/a.log(100), /logs/b.log(99)"
    )


@pytest.mark.level4
def test_threshold_of_zero_or_negative_matches_every_file_including_zero_byte_ones():
    """Spec decision 15: threshold <= 0 takes the whole subtree."""
    fs = FileSystem()
    fs.mkdir(1, "/logs")
    fs.add_file(2, "/logs/a.log", 100)
    fs.add_file(3, "/logs/b.log", 99)
    fs.add_file(4, "/logs/c.log", 0)  # a real, empty file -- it is still a match
    everything = "/logs/a.log(100), /logs/b.log(99), /logs/c.log(0)"
    assert fs.find_files_by_size(5, "/logs", 0) == everything
    assert fs.find_files_by_size(5, "/logs", -1) == everything
    assert fs.find_files_by_size(5, "/logs", -10**9) == everything


@pytest.mark.level4
def test_nothing_above_the_threshold_returns_the_empty_string():
    """Spec decision 20: a populated subtree with no match is still ''."""
    fs = build_tree(FileSystem())
    assert fs.find_files_by_size(1, "/", 901) == ""
    assert fs.find_files_by_size(1, "/", 1000) == ""
    assert fs.find_files_by_size(1, "/docs", 201) == ""


@pytest.mark.level4
def test_a_missing_path_returns_the_empty_string():
    """Spec decision 13: no None to return, so a missing directory is ''."""
    fs = build_tree(FileSystem())
    assert fs.find_files_by_size(1, "/nope", 0) == ""
    assert fs.find_files_by_size(1, "/docs/work/nope/deeper", 0) == ""
    assert fs.find_files_by_size(1, "/readme.md/inner", 0) == ""  # walks through a file


@pytest.mark.level4
def test_a_file_path_returns_the_empty_string_where_get_dir_size_returns_none():
    """Spec decision 13: the deliberate inconsistency between the two return types.

    `get_dir_size` says None for a non-directory; `find_files_by_size` is declared
    `-> str`, so the same situation has to collapse onto "". Both are asserted here
    side by side so the contrast is impossible to misread.
    """
    fs = build_tree(FileSystem())
    assert fs.get_dir_size(1, "/docs/a.txt") is None
    assert fs.find_files_by_size(1, "/docs/a.txt", 0) == ""
    assert fs.find_files_by_size(1, "/docs/a.txt", 100) == ""  # not "/docs/a.txt(100)"
    assert fs.find_files_by_size(1, "/readme.md", 0) == ""


@pytest.mark.level4
def test_an_empty_filesystem_and_a_files_free_subtree_return_the_empty_string():
    """Spec decision 20: '' for an empty root, an empty dir, and dirs-only subtrees."""
    assert FileSystem().find_files_by_size(0, "/", 0) == ""
    fs = build_tree(FileSystem())
    assert fs.find_files_by_size(1, "/docs/empty", 0) == ""
    # A directory holding only (empty) subdirectories, at two levels.
    fs.mkdir(2, "/shell")
    fs.mkdir(3, "/shell/inner")
    fs.mkdir(4, "/shell/inner/deeper")
    assert fs.find_files_by_size(5, "/shell", 0) == ""
    assert fs.find_files_by_size(5, "/shell", -1) == ""


@pytest.mark.level4
def test_sorting_is_on_the_full_path_not_the_file_name():
    """Spec decision 16 -- the same shape as the Level 2 tie-break."""
    fs = FileSystem()
    fs.mkdir(1, "/a")
    fs.mkdir(1, "/b")
    fs.add_file(2, "/a/z.txt", 100)
    fs.add_file(2, "/b/a.txt", 100)
    # By file name this would be "/b/a.txt(100), /a/z.txt(100)". By path it is not.
    assert fs.find_files_by_size(3, "/", 100) == "/a/z.txt(100), /b/a.txt(100)"


@pytest.mark.level4
def test_sorting_is_on_the_path_field_not_the_rendered_string():
    """Spec decision 17: sort the paths, then format. The trap is real, not invented.

    Checked exhaustively rather than assumed: "(" is 0x28, below "/" (0x2F) and below
    every letter, digit, ".", "-" and "_" (the smallest of which is "-", 0x2D). So for
    names drawn from that ordinary alphabet, sorting the rendered "path(size)" strings
    and sorting the paths always agree -- the first assertion below pins that
    equivalence. They diverge in exactly one situation: one file path is a proper
    prefix of another and the longer one continues with a character *below* 0x28
    (space, "!", '"', "#", "$", "%", "&", "'"). "/media/hero" and "/media/hero!2.jpg"
    are such a pair, and the second assertion below fails for any implementation that
    sorts the formatted strings.
    """
    ordinary = build_tree(FileSystem())
    rendered_sort = ", ".join(
        sorted(["/docs/a.txt(100)", "/docs/work/b.txt(200)", "/media/pic.png(900)"])
    )
    assert ordinary.find_files_by_size(1, "/", 100) == rendered_sort  # they agree here

    fs = FileSystem()
    fs.mkdir(1, "/media")
    fs.add_file(2, "/media/hero", 100)
    fs.add_file(3, "/media/hero!2.jpg", 50)
    assert "/media/hero" < "/media/hero!2.jpg"  # path order
    assert "/media/hero!2.jpg(50)" < "/media/hero(100)"  # rendered order -- reversed
    assert fs.find_files_by_size(4, "/media", 0) == (
        "/media/hero(100), /media/hero!2.jpg(50)"
    )


@pytest.mark.level4
def test_the_rendered_format_is_exact():
    """Spec decision 18: "path(size)" joined by ", " -- no brackets, no trailing sep."""
    fs = FileSystem()
    fs.mkdir(1, "/d")
    fs.add_file(2, "/a.txt", 500)
    fs.add_file(3, "/b.txt", 10)
    fs.add_file(4, "/d/c.txt", 900)
    out = fs.find_files_by_size(5, "/", 0)
    # Path order, which here is neither ascending nor descending by size.
    assert out == "/a.txt(500), /b.txt(10), /d/c.txt(900)"
    assert out.count(", ") == 2
    assert not out.endswith(",") and not out.endswith(" ")
    assert "[" not in out and "'" not in out and '"' not in out
    # Files directly under root take one slash, not two -- the root-join trap.
    assert "//" not in out
    assert fs.find_files_by_size(6, "/", 500) == "/a.txt(500), /d/c.txt(900)"


@pytest.mark.level4
def test_timestamp_is_unused_at_level_4_too():
    """Spec decision 12: still no time semantics anywhere."""
    fs = build_tree(FileSystem())
    expected = "/docs/a.txt(100), /docs/work/b.txt(200), /media/pic.png(900)"
    assert fs.find_files_by_size(0, "/", 100) == expected
    assert fs.find_files_by_size(-5, "/", 100) == expected
    assert fs.find_files_by_size(10**12, "/", 100) == expected


# ---------------------------------------------------------------- #
# Backward compatibility: Level 4 must agree with Levels 1-3.       #
# ---------------------------------------------------------------- #


@pytest.mark.level4
def test_after_a_move_files_are_reported_at_their_new_paths_only():
    fs = build_tree(FileSystem())
    assert fs.move(1, "/docs/work", "/work") is True
    out = fs.find_files_by_size(2, "/", 100)
    assert out == "/docs/a.txt(100), /media/pic.png(900), /work/b.txt(200)"
    assert "/docs/work" not in out  # the old path is gone, not merely unreachable
    assert fs.find_files_by_size(2, "/docs/work", 0) == ""
    assert fs.find_files_by_size(2, "/docs", 0) == "/docs/a.txt(100)"
    # A single file move renames its entry in place.
    assert fs.move(3, "/media/pic.png", "/media/hero.png") is True
    assert fs.find_files_by_size(4, "/media", 0) == "/media/hero.png(900)"


@pytest.mark.level4
def test_after_a_copy_both_the_original_and_the_clone_are_reported():
    fs = build_tree(FileSystem())
    assert fs.mkdir(1, "/backup") is True
    assert fs.copy(2, "/docs", "/backup/docs") is True
    assert fs.find_files_by_size(3, "/", 100) == (
        "/backup/docs/a.txt(100), /backup/docs/work/b.txt(200), "
        "/docs/a.txt(100), /docs/work/b.txt(200), /media/pic.png(900)"
    )
    assert fs.find_files_by_size(3, "/backup", 0) == (
        "/backup/docs/a.txt(100), /backup/docs/work/b.txt(200), "
        "/backup/docs/work/notes.txt(50)"
    )
    # The clone is independent: a later write shows up on one side only.
    assert fs.add_file(4, "/backup/docs/extra.txt", 7) is True
    assert "extra.txt" in fs.find_files_by_size(5, "/backup", 0)
    assert fs.find_files_by_size(5, "/docs", 0) == (
        "/docs/a.txt(100), /docs/work/b.txt(200), /docs/work/notes.txt(50)"
    )


@pytest.mark.level4
def test_a_query_rooted_at_a_directory_that_was_itself_just_moved():
    fs = build_tree(FileSystem())
    assert fs.move(1, "/docs/work", "/media/work") is True
    assert fs.find_files_by_size(2, "/media/work", 0) == (
        "/media/work/b.txt(200), /media/work/notes.txt(50)"
    )
    assert fs.find_files_by_size(2, "/media", 100) == (
        "/media/pic.png(900), /media/work/b.txt(200)"
    )
    # ...and again after a second hop, back up to the root.
    assert fs.move(3, "/media/work", "/work") is True
    assert fs.find_files_by_size(4, "/work", 51) == "/work/b.txt(200)"
    assert fs.find_files_by_size(4, "/media/work", 0) == ""


@pytest.mark.level4
def test_backward_compat_level1_alongside_find_files_by_size():
    fs = FileSystem()
    assert fs.mkdir(1, "/docs") is True
    assert fs.mkdir(2, "/docs") is False
    assert fs.mkdir(3, "/") is False
    assert fs.add_file(4, "/docs/a.txt", 100) is True
    assert fs.add_file(5, "/docs/a.txt", 999) is False
    assert fs.get_file_size(6, "/docs/a.txt") == 100
    assert fs.get_file_size(6, "/docs") is None
    assert fs.get_file_size(6, "/nope") is None
    assert fs.add_file(7, "/missing/a.txt", 1) is False
    assert fs.add_file(8, "/zero.txt", 0) is True
    # The duplicate add_file did not overwrite, and the zero-byte file is real.
    assert fs.find_files_by_size(9, "/", 0) == "/docs/a.txt(100), /zero.txt(0)"


@pytest.mark.level4
def test_backward_compat_level2_alongside_find_files_by_size():
    fs = build_tree(FileSystem())
    assert fs.get_dir_size(1, "/") == 1260
    assert fs.get_dir_size(1, "/docs") == 350
    assert fs.get_dir_size(1, "/docs/empty") == 0
    assert fs.get_dir_size(1, "/docs/a.txt") is None
    assert fs.get_dir_size(1, "/nope") is None
    assert fs.find_largest_file(1, "/") == "/media/pic.png"
    assert fs.find_largest_file(1, "/docs") == "/docs/work/b.txt"
    assert fs.find_largest_file(1, "/docs/empty") is None
    # The three queries agree with each other on the same tree.
    everything = fs.find_files_by_size(1, "/", 0)
    assert everything.startswith("/docs/a.txt(100)")
    assert everything.endswith("/readme.md(10)")
    assert f"{fs.find_largest_file(1, '/')}(900)" in everything
    assert sum(int(entry.split("(")[1][:-1]) for entry in everything.split(", ")) == 1260


@pytest.mark.level4
def test_backward_compat_level3_alongside_find_files_by_size():
    fs = build_tree(FileSystem())
    before = snapshot(fs, TREE_PATHS)
    before_export = fs.find_files_by_size(1, "/", 0)
    assert fs.move(2, "/docs", "/docs/work/docs") is False
    assert fs.copy(2, "/docs", "/docs/work/docs") is False
    assert fs.move(2, "/", "/x") is False
    assert fs.copy(2, "/docs/a.txt", "/media/pic.png") is False
    assert fs.move(2, "/docs/a.txt", "/backup/a.txt") is False
    assert snapshot(fs, TREE_PATHS) == before
    assert fs.find_files_by_size(3, "/", 0) == before_export  # failures changed nothing

    assert fs.move(4, "/docs/work", "/work") is True
    assert fs.copy(5, "/work", "/media/work") is True
    assert fs.get_dir_size(6, "/media/work") == 250
    assert fs.get_file_size(6, "/docs/work/b.txt") is None
    assert fs.find_files_by_size(7, "/", 200) == (
        "/media/pic.png(900), /media/work/b.txt(200), /work/b.txt(200)"
    )
    fs.add_file(8, "/media/work/extra.txt", 1)
    assert fs.get_dir_size(9, "/work") == 250  # the clone is independent
    assert fs.find_files_by_size(9, "/work", 0) == (
        "/work/b.txt(200), /work/notes.txt(50)"
    )
