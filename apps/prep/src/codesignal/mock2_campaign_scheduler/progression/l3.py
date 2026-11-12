"""`CampaignScheduler` as it stood at the end of Level 3: budgets and throttling.

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

`created_at` is still unread. So is the observation that the `timestamp` Level 1
was told to ignore is the same integer `serve` now builds a sliding window out
of; the parameter carried meaning, the stored field did not.

State here is plain mutable state, which is the honest shape for what Level 3
asks for. Nothing at this level needs to know what happened, only what is true,
so nothing here keeps a history of anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Sentinel stored in `_Campaign.budget` meaning "no budget cap configured".
UNLIMITED: int = -1


@dataclass(slots=True)
class _Campaign:
    """The stored state of one campaign."""

    channel: str
    priority: int
    created_at: int
    active: bool = True
    budget: int = UNLIMITED
    impressions: list[int] = field(default_factory=list)


class CampaignScheduler:
    """A marketing campaign delivery system with budgets and per-campaign rate limits."""

    def __init__(self, window: int = 60, max_impressions_per_window: int = 5) -> None:
        """Create an empty scheduler with a per-campaign sliding-window rate limit."""
        if window < 1:
            raise ValueError("window must be a positive integer")
        if max_impressions_per_window < 1:
            raise ValueError("max_impressions_per_window must be a positive integer")
        self._window = window
        self._max_impressions = max_impressions_per_window
        self._campaigns: dict[str, _Campaign] = {}

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
        self._campaigns[campaign_id] = _Campaign(
            channel=channel, priority=priority, created_at=timestamp
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
        campaign.active = False
        return True

    def resume_campaign(self, timestamp: int, campaign_id: str) -> bool:
        """Resume a paused campaign; False if unknown or already active."""
        campaign = self._campaigns.get(campaign_id)
        if campaign is None or campaign.active:
            return False
        campaign.active = True
        return True

    def delete_campaign(self, timestamp: int, campaign_id: str) -> bool:
        """Remove a campaign; False if unknown."""
        if campaign_id not in self._campaigns:
            return False
        del self._campaigns[campaign_id]
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
        campaign.budget = amount
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
        if campaign.budget != UNLIMITED:
            campaign.budget -= cost
        campaign.impressions.append(timestamp)
        return True
