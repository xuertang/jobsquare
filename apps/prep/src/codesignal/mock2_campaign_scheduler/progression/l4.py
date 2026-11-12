"""`CampaignScheduler` as it stood at the end of Level 4: rollback and audit trail.

Three habits are exercised here, and only three. All are ordinary craft,
defensible without any knowledge of what a later level will ask for:

1.  Campaign state lives in one small record (`_Campaign`) rather than in
    several parallel dicts keyed by id. Parallel dicts drift out of step the
    moment a third field appears; a record cannot.
2.  The question "may this campaign be selected?" is answered in exactly one
    place, `_is_eligible`. Every method that gates on it calls the predicate
    instead of reading the flag inline.
3.  The `timestamp` every method is handed is kept, as `created_at` on the
    record `create_campaign` builds. Nothing at this level reads it.

That third habit is the one worth defending, because the spec is explicit that
`timestamp` is unused here. Keeping it is not a prediction about later levels;
it is the difference between *recording a value the caller explicitly put in
your hands* and *inventing state nobody has mentioned*. The first is
bookkeeping. The second is guessing, and guessing right is still guessing.

Note the asymmetry the rule produces. This file has a `created_at` because a
caller supplied one on every call. It has no spend cap, no delivery accounting
and no rollback machinery, because no caller has supplied or asked for any of
those, and adding them would mean writing code against requirements that do not
exist yet. A level pays for what it needs when it needs it.

Level 2 added three public read methods and exactly one helper. `_ranked` is the
only place in the file that filters, the only place that sorts and the only
place that renders an entry; the three public methods are thin wrappers that
join, slice or count what it returns. None of them re-answers the question
`_is_eligible` already answers.

Level 3 is where the model actually changed. `_Campaign` grew two fields,
`__init__` grew two defaulted parameters, and `_is_eligible` widened from
"active" to "active and not exhausted" -- which pulled the new exclusion rule
through `_ranked` and out into all three Level 2 methods without any of them
being edited. The widening was not free, and it cost exactly where the predicate
had been over-applied: `pause_campaign` and `resume_campaign` had been asking it
a question it no longer answers -- an exhausted campaign is still lifecycle-
active, and must still be pausable -- so both now read the flag they own.

Level 4 is a genuine refactor, and calling it anything else would be dishonest.
Mutable state that has been overwritten in place cannot say what it used to be
or what happened to it, and no chokepoint written at Level 1 makes that free.
So every mutation became an immutable `_Event` appended to one append-only
`self._log`, `self._campaigns` became *derived* state that only `_apply` may
touch, and every public mutator became validate-then-delegate: it no longer
assigns. Seven mutators were rewritten that way. With the log in place Level 4
needed no new state at all -- `history` filters the log, `snapshot` copies it,
`restore` swaps it back in and replays from empty.

Why a shallow copy is safe, and why the obvious alternative is not: `_Event` is
frozen, so `tuple(self._log)` is structural sharing -- O(n) pointers, no object
copying, and still a true point-in-time capture that later activity cannot reach
into. Deep-copying the materialized `_campaigns` dict is O(state) rather than
O(history) and needs no `_Event` class at all, but it is correct only for as long
as you remember to copy every mutable field you ever add. `_Campaign.impressions`
is exactly the field people forget: a `dict(self._campaigns)` or a hand-rolled
`_Campaign(**vars(c))` copies the budget integer correctly and *shares the
impressions list*, so budgets roll back, statuses roll back, `get_campaign` and
`count_active` all look right, and the single symptom is a rate limit that
survives a rollback it was supposed to erase. Storing a bare integer log offset
is cheaper still and wrong for a different reason: restore an early capture and
then a later one, and the offset indexes a log that has been truncated out from
under it. Capture the prefix, not the position.

`created_at` remains unread by every level. It cost one field, one keyword
argument in `_apply`, and one keyword argument on the create event -- and bought
nothing. It was inert, not wrong: the discipline it illustrates is what stopped
`budget` from appearing in `l1.py`, which would have been wrong.
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
    timestamp: int
    channel: str | None = None
    priority: int | None = None
    amount: int | None = None
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
    created_at: int
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
                channel=ev.channel,  # type: ignore[arg-type]
                priority=ev.priority,  # type: ignore[arg-type]
                created_at=ev.timestamp,
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
            campaign.impressions.append(ev.timestamp)
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
    # Eligibility -- the one place this question is answered   #
    # ------------------------------------------------------- #

    def _is_eligible(self, campaign: _Campaign) -> bool:
        """Eligible == active and not budget-exhausted (Level 3 widened this).

        This is the whole Level 2 -> Level 3 diff for the three listing methods:
        they route through `_ranked`, `_ranked` calls this, and none of the four
        needed a line changed. Throttling deliberately plays no part -- a
        rate-limited campaign is still eligible.
        """
        if not campaign.active:
            return False
        return campaign.budget == UNLIMITED or campaign.budget > 0

    # ------------------------------------------------------- #
    # Level 1 -- lifecycle CRUD                                #
    # ------------------------------------------------------- #
    # Every public method takes `timestamp` first. Nothing here reads it
    # except `create_campaign`, which files it on the record and moves on.

    def create_campaign(
        self, timestamp: int, campaign_id: str, channel: str, priority: int
    ) -> bool:
        """Register a new active campaign; False if the id is already taken."""
        if campaign_id in self._campaigns:
            return False
        self._record(
            _Event("create", campaign_id, timestamp, channel=channel, priority=priority)
        )
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
        self._record(_Event("pause", campaign_id, timestamp))
        return True

    def resume_campaign(self, timestamp: int, campaign_id: str) -> bool:
        """Resume a paused campaign; False if unknown or already active."""
        campaign = self._campaigns.get(campaign_id)
        if campaign is None or campaign.active:
            return False
        self._record(_Event("resume", campaign_id, timestamp))
        return True

    def delete_campaign(self, timestamp: int, campaign_id: str) -> bool:
        """Remove a campaign; False if unknown. Audit history is retained."""
        if campaign_id not in self._campaigns:
            return False
        self._record(_Event("delete", campaign_id, timestamp))
        return True

    # ------------------------------------------------------- #
    # Level 2 -- querying, ranking, aggregation                #
    # ------------------------------------------------------- #

    def _ranked(self, channel: str | None = None) -> list[str]:
        """Rendered entries for the eligible campaigns, priority desc then id asc."""
        chosen = [
            (cid, campaign)
            for cid, campaign in self._campaigns.items()
            if self._is_eligible(campaign)
            and (channel is None or campaign.channel == channel)
        ]
        chosen.sort(key=lambda pair: (-pair[1].priority, pair[0]))
        return [f"{cid}(priority={campaign.priority})" for cid, campaign in chosen]

    def list_by_channel(self, timestamp: int, channel: str) -> str:
        """Eligible campaigns on `channel`, ranked, joined by ", "; "" if none."""
        return ", ".join(self._ranked(channel))

    def top_campaigns(self, timestamp: int, n: int) -> str:
        """The top `n` eligible campaigns across all channels, joined by ", "."""
        if n <= 0:
            return ""
        return ", ".join(self._ranked()[:n])

    def count_active(self, timestamp: int) -> int:
        """Number of eligible campaigns across all channels."""
        return len(self._ranked())

    # ------------------------------------------------------- #
    # Level 3 -- budgets and sliding-window rate limiting      #
    # ------------------------------------------------------- #

    def set_budget(self, timestamp: int, campaign_id: str, amount: int) -> bool:
        """Set remaining budget to exactly `amount`; False if unknown or negative."""
        campaign = self._campaigns.get(campaign_id)
        if campaign is None or amount < 0:
            return False
        self._record(_Event("set_budget", campaign_id, timestamp, amount=amount))
        return True

    def remaining_budget(self, timestamp: int, campaign_id: str) -> int | None:
        """Remaining budget, -1 when uncapped, None if the campaign is unknown."""
        campaign = self._campaigns.get(campaign_id)
        return None if campaign is None else campaign.budget

    def _impressions_in_window(self, campaign: _Campaign, timestamp: int) -> int:
        """Count impressions falling in the half-open window (t - W, t].

        This filters the *whole* recorded list against the timestamp it was
        handed. Nothing is ever pruned, so a serve whose timestamp moves
        backwards is judged against its own window, and an impression sitting at
        a higher timestamp is simply out of range rather than gone -- it will
        block again when a serve near it arrives.
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
        self._record(_Event("serve", campaign_id, timestamp, cost=cost))
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
