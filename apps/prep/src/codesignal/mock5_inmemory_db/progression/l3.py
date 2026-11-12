"""Level 3 snapshot -- TTLs, which the model absorbs rather than survives.

Level 3 adds one method, `set_with_ttl`, and then quietly redefines the whole
program: a field written at `t` with lifetime `d` is readable only on the
half-open interval `[t, t + d)`, and an expired field must be invisible to
`get`, to `delete`, to `scan` and to `scan_by_prefix` alike. The spec says as
much itself -- "the rest of this level is a refactor, and it is the real work".

Here it is not a refactor, and the reason is worth stating precisely, because it
is not that Level 1 saw this coming. Level 1 stored a `_Field` record instead of
a bare string, and routed every read through `_field`. Those two decisions do
not anticipate expiry; what they do is leave a *place* for it. So the entire
semantic change lands in two edits:

* `_Field` grows one attribute, `expires_at`, and one predicate, `alive_at`,
  holding the liveness rule and nothing else. `None` means permanent, which is
  the honest encoding of "no expiry instant exists" and is why plain `set` needs
  no special-casing anywhere downstream.
* `_field` consults that predicate. One condition, in the one accessor every
  read already went through.

`_items` is byte-identical to Level 2 -- not because it was written to be, but
because it asks `_field` about each field name instead of reading the dict, so
it inherited the new definition of "readable" without being reopened. `scan` and
`scan_by_prefix` are likewise untouched, and so are `set`, `get`, `_format` and
`__init__`. `_write` gains a defaulted `expires_at` parameter, which is what
keeps `set` byte-identical too: `set` is `set_with_ttl` with an infinite
lifespan, so "no argument" and "permanent" are the same statement.

Exactly one existing public method changed body, and it is `delete`. That is not
a failure of the chokepoint; it is that `delete` stopped being a pure read.
The spec requires an expired field to answer `False` *and* to be purged, so that
no stale entry can be resurrected by anything later. "Was it live?" and "is it
present?" are two different questions at Level 3 where at Level 2 they were one,
and `delete` is the only method that has to ask both.

`ttl <= 0` needs no branch: `expires_at = timestamp + ttl <= timestamp` and the
half-open rule makes `[t, t + ttl)` empty, so the field is dead on arrival by
arithmetic rather than by a guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class _Field:
    """One stored field: its value, plus the instant it stops being readable."""

    value: str
    expires_at: Optional[int] = None  # None means "never expires"

    def alive_at(self, when: int) -> bool:
        """The single liveness rule: alive for `t <= when < expires_at`."""
        return self.expires_at is None or when < self.expires_at


class InMemoryDB:
    """A record store mapping each `key` to a set of `field -> value` pairs."""

    def __init__(self) -> None:
        """Initialise an empty database."""
        # key -> field -> _Field. A record with no fields left is dropped, so
        # "the key exists" and "the key has a field" never disagree.
        self._db: dict[str, dict[str, _Field]] = {}

    # ------------------------------------------------------------------
    # Internal primitives -- every read in the class goes through these
    # ------------------------------------------------------------------

    def _write(
        self, key: str, field: str, value: str, expires_at: Optional[int] = None
    ) -> None:
        """Create or overwrite `field` on `key`, replacing value and lifespan.

        The single write chokepoint. Both writers are this call with a different
        `expires_at`, so there is no such thing as inheriting or extending a
        previous lifespan -- a write replaces the whole record.
        """
        self._db.setdefault(key, {})[field] = _Field(value, expires_at)

    def _field(self, timestamp: int, key: str, field: str) -> Optional[_Field]:
        """The field at `key`/`field` if it is live at `timestamp`, else None.

        Single chokepoint for reads. Everything that can make a field
        unreadable -- no such key, no such field, expired -- is decided here and
        collapses to `None` at the boundary, so no public method owns a second
        opinion about what "readable" means.
        """
        record = self._db.get(key)
        if record is None:
            return None
        entry = record.get(field)
        if entry is None or not entry.alive_at(timestamp):
            return None
        return entry

    def _items(
        self, timestamp: int, key: str, prefix: str = ""
    ) -> list[tuple[str, _Field]]:
        """Readable `(field, entry)` pairs of `key` matching `prefix`, sorted.

        The single chokepoint for record-wide reads, and the sibling of
        `_field`. It asks `_field` about each candidate name rather than reading
        the dict itself, so it inherits readability for free instead of forming
        a second opinion about it. Sorting is plain lexicographic on the field
        name, per the spec: `f1`, `f10`, `f2`.
        """
        record = self._db.get(key)
        if not record:
            return []
        matches = []
        for name in record:
            if not name.startswith(prefix):
                continue
            entry = self._field(timestamp, key, name)
            if entry is not None:
                matches.append((name, entry))
        matches.sort(key=lambda item: item[0])
        return matches

    @staticmethod
    def _format(items: list[tuple[str, _Field]]) -> str:
        """Render pairs as `f1(v1), f2(v2)`; the empty selection renders as ``."""
        return ", ".join(f"{name}({entry.value})" for name, entry in items)

    # ------------------------------------------------------------------
    # Level 1 -- core operations
    # ------------------------------------------------------------------

    def set(self, timestamp: int, key: str, field: str, value: str) -> None:
        """Set `field` on `key` to `value`, creating or overwriting it."""
        self._write(key, field, value)

    def get(self, timestamp: int, key: str, field: str) -> Optional[str]:
        """The value at `key`/`field`, or None if there is nothing there.

        `""` is a legal value and a hit; only the miss returns `None`.
        """
        entry = self._field(timestamp, key, field)
        return None if entry is None else entry.value

    def delete(self, timestamp: int, key: str, field: str) -> bool:
        """Remove `key`/`field`; True only if it was live at `timestamp`."""
        record = self._db.get(key)
        if record is None or field not in record:
            return False
        was_live = record[field].alive_at(timestamp)
        # Purge unconditionally. An expired field answers False, but it is also
        # removed, so no later operation can observe or resurrect a stale entry.
        del record[field]
        if not record:
            del self._db[key]
        return was_live

    # ------------------------------------------------------------------
    # Level 2 -- scan and aggregation
    # ------------------------------------------------------------------

    def scan(self, timestamp: int, key: str) -> str:
        """Every field of `key`, field-ascending, as `f1(v1), f2(v2)`."""
        return self.scan_by_prefix(timestamp, key, "")

    def scan_by_prefix(self, timestamp: int, key: str, prefix: str) -> str:
        """Fields of `key` whose name starts with `prefix`, field-ascending."""
        return self._format(self._items(timestamp, key, prefix))

    # ------------------------------------------------------------------
    # Level 3 -- TTL
    # ------------------------------------------------------------------

    def set_with_ttl(
        self, timestamp: int, key: str, field: str, value: str, ttl: int
    ) -> None:
        """Set `key`/`field`, alive for `timestamp <= q < timestamp + ttl`."""
        self._write(key, field, value, expires_at=timestamp + ttl)
