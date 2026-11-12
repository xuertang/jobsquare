"""Reference solution for ICF Mock 2: CampaignScheduler.

FORMAT NOTE
-----------
Every public method takes `timestamp` as its first argument, from Level 1
onwards, even where the level's semantics do not use it. That is the ICF
house style, and it is a hint, not noise: the parameter you are handed and
told to ignore at Level 1 is the parameter Level 3 builds a sliding window
out of. Methods that return a collection return one `", "`-joined string,
never a list.

KEY DESIGN DECISION
-------------------
Every mutation is an immutable `_Event` appended to a single append-only log.
Nothing mutates `self._campaigns` except `_apply()`, which replays one event
*unconditionally*. Public methods only VALIDATE and then delegate. This split --
"validate in the command handler, mutate only in the applier" -- is what makes
Levels 3 and 4 nearly free:

  * Level 3 (budgets + sliding-window rate limit) adds two event kinds and two
    validation clauses. The `serve` impression log is not bookkeeping bolted on
    the side; it IS the replayed log, so it can never drift from the budget.
  * Level 4 (snapshot/restore/history) needs no new state at all.
    `history(id)` = filter the log. `snapshot(name)` = a shallow copy of the
    log. `restore(name)` = swap the log back in and replay from empty.

WHY A SHALLOW COPY IS SAFE (the deep-copy tradeoff)
--------------------------------------------------
`_Event` is a frozen dataclass, so `tuple(self._log)` is *structural sharing*:
O(n) pointers, zero object copying, and still a true point-in-time snapshot --
immutability is what buys correctness here. The obvious alternative, deep-copying
the materialized `_campaigns` dict, is O(state) rather than O(history) and looks
cheaper, but it is correct only as long as you remember to copy every mutable
field you ever add (that per-campaign `impressions` list is exactly the field
people forget, and the bug only shows up as a rate limit that survives a
restore). Storing a bare integer log *offset* is tempting and even cheaper --
but it breaks the moment you restore an early snapshot and then restore a later
one, because the log has been truncated out from under that offset. Snapshot the
prefix, not the position.

Cost model: snapshot O(n) pointers, restore O(n) replay, every query O(1)/O(k)
against materialized state. For an interview-scale problem that is the right
trade; a production system would checkpoint the materialized state periodically
and replay only the tail.

THE OTHER LESSON: ONE ELIGIBILITY PREDICATE
-------------------------------------------
Level 2 defines "eligible" as *active*; Level 3 silently widens it to *active
and not budget-exhausted*. Because `list_by_channel`, `top_campaigns` and
`count_active` all route through `_is_eligible`, that widening is a two-line
edit to one private method and those three public methods are byte-identical
between the Level 2 and Level 3 versions of this file. Inline the `active`
check into all three and Level 3 costs you three edits and a missed one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Sentinel stored in `_Campaign.budget` meaning "no budget cap configured".
UNLIMITED: int = -1


@dataclass(frozen=True, slots=True)
class _Event:
    """One immutable, already-validated state change."""

    kind: str  # create | pause | resume | delete | set_budget | serve
    campaign_id: str
    channel: str | None = None
    priority: int | None = None
    amount: int | None = None
    timestamp: int | None = None
    cost: int | None = None

    def describe(self) -> str:
        """Render this event as the audit-trail entry Level 4 returns."""
        if self.kind == "create":
            return f"create(channel={self.channel}, priority={self.priority})"
        if self.kind == "set_budget":
            return f"set_budget({self.amount})"
        if self.kind == "serve":
            return f"serve(t={self.timestamp}, cost={self.cost})"
        return self.kind  # pause | resume | delete


@dataclass(slots=True)
class _Campaign:
    """Materialized state for one campaign; derived entirely from the log."""

    channel: str
    priority: int
    active: bool = True
    budget: int = UNLIMITED
    impressions: list[int] = field(default_factory=list)


class CampaignScheduler:
    """A marketing campaign delivery system with budgets, rate limits and snapshots."""

    def __init__(self, window: int = 60, max_impressions_per_window: int = 5) -> None:
        """Create an empty scheduler with a per-campaign sliding-window rate limit."""
        if window < 1:
            raise ValueError("window must be a positive integer")
        if max_impressions_per_window < 1:
            raise ValueError("max_impressions_per_window must be a positive integer")
        self._window = window
        self._max_impressions = max_impressions_per_window
        self._log: list[_Event] = []
        self._snapshots: dict[str, tuple[_Event, ...]] = {}
        self._campaigns: dict[str, _Campaign] = {}

    # ------------------------------------------------------------------ #
    # Event plumbing -- the only place `self._campaigns` is ever mutated. #
    # ------------------------------------------------------------------ #

    def _apply(self, ev: _Event) -> None:
        """Mutate materialized state for one already-validated event."""
        if ev.kind == "create":
            self._campaigns[ev.campaign_id] = _Campaign(
                channel=ev.channel, priority=ev.priority  # type: ignore[arg-type]
            )
            return

        campaign = self._campaigns[ev.campaign_id]
        if ev.kind == "pause":
            campaign.active = False
        elif ev.kind == "resume":
            campaign.active = True
        elif ev.kind == "delete":
            del self._campaigns[ev.campaign_id]
        elif ev.kind == "set_budget":
            campaign.budget = ev.amount  # type: ignore[assignment]
        elif ev.kind == "serve":
            if campaign.budget != UNLIMITED:
                campaign.budget -= ev.cost  # type: ignore[operator]
            campaign.impressions.append(ev.timestamp)  # type: ignore[arg-type]
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unknown event kind: {ev.kind!r}")

    def _record(self, ev: _Event) -> None:
        """Append an event to the log and fold it into materialized state."""
        self._log.append(ev)
        self._apply(ev)

    def _rebuild(self) -> None:
        """Recompute all materialized state by replaying the log from empty."""
        self._campaigns = {}
        for ev in self._log:
            self._apply(ev)

    # ------------------------------------------------------- #
    # Level 1 -- lifecycle CRUD                                #
    # ------------------------------------------------------- #
    # `timestamp` is part of every signature from here on. Levels 1 and 2
    # never read it; Level 3 turns it into the sliding window.

    def create_campaign(
        self, timestamp: int, campaign_id: str, channel: str, priority: int
    ) -> bool:
        """Register a new active campaign; False if the id is already taken."""
        if campaign_id in self._campaigns:
            return False
        self._record(_Event("create", campaign_id, channel=channel, priority=priority))
        return True

    def get_campaign(self, timestamp: int, campaign_id: str) -> str | None:
        """Return "id(channel=C, priority=P, status=S)" or None if unknown."""
        campaign = self._campaigns.get(campaign_id)
        if campaign is None:
            return None
        status = "active" if campaign.active else "paused"
        return (
            f"{campaign_id}(channel={campaign.channel}, "
            f"priority={campaign.priority}, status={status})"
        )

    def pause_campaign(self, timestamp: int, campaign_id: str) -> bool:
        """Pause an active campaign; False if unknown or already paused."""
        campaign = self._campaigns.get(campaign_id)
        if campaign is None or not campaign.active:
            return False
        self._record(_Event("pause", campaign_id))
        return True

    def resume_campaign(self, timestamp: int, campaign_id: str) -> bool:
        """Resume a paused campaign; False if unknown or already active."""
        campaign = self._campaigns.get(campaign_id)
        if campaign is None or campaign.active:
            return False
        self._record(_Event("resume", campaign_id))
        return True

    def delete_campaign(self, timestamp: int, campaign_id: str) -> bool:
        """Remove a campaign; False if unknown. Audit history is retained."""
        if campaign_id not in self._campaigns:
            return False
        self._record(_Event("delete", campaign_id))
        return True

    # ------------------------------------------------------- #
    # Level 2 -- querying, ranking, aggregation                #
    # ------------------------------------------------------- #

    def _is_eligible(self, campaign: _Campaign) -> bool:
        """Eligible == active and not budget-exhausted (Level 3 widened this).

        This is the whole Level 2 -> Level 3 diff for the three listing
        methods: they call this and are otherwise untouched.
        """
        if not campaign.active:
            return False
        return campaign.budget == UNLIMITED or campaign.budget > 0

    def _eligible_ids(self, channel: str | None = None) -> list[str]:
        """Ids of eligible campaigns, ranked by priority desc then id asc."""
        ids = [
            cid
            for cid, campaign in self._campaigns.items()
            if self._is_eligible(campaign)
            and (channel is None or campaign.channel == channel)
        ]
        ids.sort(key=lambda cid: (-self._campaigns[cid].priority, cid))
        return ids

    def _format_ranked(self, campaign_id: str) -> str:
        """Render the ranked-listing form: "id(priority=P)"."""
        return f"{campaign_id}(priority={self._campaigns[campaign_id].priority})"

    def list_by_channel(self, timestamp: int, channel: str) -> str:
        """Eligible campaigns on `channel`, ranked, as "a(priority=1), b(priority=0)"."""
        return ", ".join(self._format_ranked(cid) for cid in self._eligible_ids(channel))

    def top_campaigns(self, timestamp: int, n: int) -> str:
        """Up to `n` top-ranked eligible campaigns across all channels, joined."""
        if n <= 0:
            return ""
        return ", ".join(
            self._format_ranked(cid) for cid in self._eligible_ids()[:n]
        )

    def count_active(self, timestamp: int) -> int:
        """Number of eligible campaigns across all channels."""
        return len(self._eligible_ids())

    # ------------------------------------------------------- #
    # Level 3 -- budgets and sliding-window rate limiting      #
    # ------------------------------------------------------- #

    def set_budget(self, timestamp: int, campaign_id: str, amount: int) -> bool:
        """Set remaining budget to exactly `amount`; False if unknown or negative."""
        if campaign_id not in self._campaigns or amount < 0:
            return False
        self._record(_Event("set_budget", campaign_id, amount=amount))
        return True

    def remaining_budget(self, timestamp: int, campaign_id: str) -> int | None:
        """Remaining budget, -1 when uncapped, None if the campaign is unknown."""
        campaign = self._campaigns.get(campaign_id)
        return None if campaign is None else campaign.budget

    def _impressions_in_window(self, campaign: _Campaign, timestamp: int) -> int:
        """Count impressions falling in the half-open window (t - W, t].

        Note that this filters the *whole* recorded log against the timestamp
        it was handed. Nothing is ever pruned, so a serve whose timestamp moves
        backwards is judged against its own window, and an impression sitting
        at a higher timestamp is simply out of range rather than gone.
        """
        low = timestamp - self._window
        return sum(1 for ts in campaign.impressions if low < ts <= timestamp)

    def serve(self, timestamp: int, campaign_id: str, cost: int) -> bool:
        """Deliver one impression if active, funded and under the rate limit."""
        campaign = self._campaigns.get(campaign_id)
        if campaign is None or not campaign.active:
            return False
        if cost < 1:
            return False
        if campaign.budget != UNLIMITED and campaign.budget < cost:
            return False
        if self._impressions_in_window(campaign, timestamp) >= self._max_impressions:
            return False
        self._record(_Event("serve", campaign_id, timestamp=timestamp, cost=cost))
        return True

    # ------------------------------------------------------- #
    # Level 4 -- snapshot, restore, audit trail                #
    # ------------------------------------------------------- #

    def snapshot(self, timestamp: int, name: str) -> bool:
        """Capture the whole system state under `name`, overwriting any prior one."""
        if not name:
            return False
        # `_Event` is frozen, so sharing the objects is safe: this tuple can
        # never be mutated by later activity on the live log.
        self._snapshots[name] = tuple(self._log)
        return True

    def restore(self, timestamp: int, name: str) -> bool:
        """Roll the system back to snapshot `name`; False if no such snapshot."""
        saved = self._snapshots.get(name)
        if saved is None:
            return False
        self._log = list(saved)
        self._rebuild()
        return True

    def history(self, timestamp: int, campaign_id: str) -> str:
        """Ordered audit trail of state-changing events, joined by ", "."""
        return ", ".join(
            ev.describe() for ev in self._log if ev.campaign_id == campaign_id
        )
