"""Naive Level 1 -- the shortest thing that passes, and nothing more.

This is the counterfactual to `progression/l1.py`. It is not a strawman. Level 1
asks for four operations on a keyed store holding two values per key, and two
parallel dicts is the most direct expression of that. It is shorter than the
record version, it needs no imports beyond `Optional`, and `get_content` is a
single line -- `self._bodies.get(content_id)` -- where the record version needs
three.

THE ARGUMENT ABOUT `timestamp`
------------------------------
Every one of the four signatures takes `timestamp` first. Nothing in Level 1
reads it: nothing expires, mutations arrive in non-decreasing order, and the
spec's own worked example shows `get_content(2, "home-hero")` returning what
`add_content(1, ...)` stored. So this file accepts the parameter because the
signature demands it and then never mentions it again.

That deserves a real defence rather than a shrug, because it is the decision the
whole comparison turns on.

The defence is this. You cannot implement a requirement that has not been
stated, and you should not manufacture state on a hunch. Storing a value you
have no use for is speculative generality -- the thing every code review, style
guide and engineering culture tells you not to do. A field that nothing reads is
a field that nothing keeps correct; it is a comment that will eventually be
wrong. YAGNI is not a slogan here, it is the correct default, and at Level 1 it
points at exactly this file. A reviewer handed only Levels 1 and 2 would be
right to ask why a `timestamp` was being written down when no method could
justify reading it back.

The counter-argument -- the one `progression/l1.py` makes -- is narrower than it
first looks, and it is worth stating fairly. It is not "guess that TTLs are
coming." It is that *keeping a value you were handed* and *inventing a value
nobody gave you* are different acts. Nothing here has to invent an expiry field
or a version counter; the caller is pushing `timestamp` through the door on
every single call. Discarding it is not the absence of speculation, it is a
deliberate destructive act, and it is the only one of the four arguments this
file treats that way. `body` gets stored. `size` gets stored. `content_id` gets
stored. `timestamp` gets dropped.

Which of those two readings is right is not decidable from Level 1. It is
decidable from Level 3, and by then the decision is forty minutes old.

The other two omissions are cheaper and less interesting:

1. No `_Record` dataclass. Two dicts is less machinery than a class plus a
   container of it, and nothing in Level 1 asks the store to hold a third
   attribute.

2. No private read accessor. Each of the four public methods asks the dict its
   own question directly, in one line, and a helper that wraps `dict.get` would
   be indirection with no reader. "Do not add abstraction until you have two
   callers that need it" is real advice, and here it points this way.

The cost of all three is zero at Level 1, small at Level 2, and it arrives in
full at Level 3. See `WRONG_PATH.md` for the measurement.
"""

from __future__ import annotations

from typing import Optional


class ContentStore:
    """A CMS-style content repository keyed by `content_id`."""

    def __init__(self) -> None:
        """Initialise an empty store."""
        self._bodies: dict[str, str] = {}
        self._sizes: dict[str, int] = {}

    def add_content(
        self, timestamp: int, content_id: str, body: str, size: int
    ) -> bool:
        """Store new content under `content_id`; False if that id is taken."""
        if content_id in self._bodies:
            return False
        self._bodies[content_id] = body
        self._sizes[content_id] = size
        return True

    def get_content(self, timestamp: int, content_id: str) -> Optional[str]:
        """Read the body stored under `content_id`, or None if there is none."""
        return self._bodies.get(content_id)

    def update_content(
        self, timestamp: int, content_id: str, body: str, size: int
    ) -> bool:
        """Overwrite the body and size of existing content; False if absent."""
        if content_id not in self._bodies:
            return False
        self._bodies[content_id] = body
        self._sizes[content_id] = size
        return True

    def delete_content(self, timestamp: int, content_id: str) -> bool:
        """Remove `content_id` from the store; False if it was absent."""
        if content_id not in self._bodies:
            return False
        del self._bodies[content_id]
        del self._sizes[content_id]
        return True
