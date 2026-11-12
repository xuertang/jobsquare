"""`CampaignScheduler` as it stood at the end of Level 1: lifecycle CRUD only.

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
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class _Campaign:
    """The stored state of one campaign."""

    channel: str
    priority: int
    created_at: int
    active: bool = True


class CampaignScheduler:
    """A marketing campaign delivery system: create, pause, resume and delete campaigns."""

    def __init__(self) -> None:
        """Create an empty scheduler."""
        self._campaigns: dict[str, _Campaign] = {}

    # ------------------------------------------------------- #
    # Eligibility -- the one place this question is answered   #
    # ------------------------------------------------------- #

    def _is_eligible(self, campaign: _Campaign) -> bool:
        """Eligible == active."""
        return campaign.active

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
        if campaign is None or not self._is_eligible(campaign):
            return False
        campaign.active = False
        return True

    def resume_campaign(self, timestamp: int, campaign_id: str) -> bool:
        """Resume a paused campaign; False if unknown or already active."""
        campaign = self._campaigns.get(campaign_id)
        if campaign is None or self._is_eligible(campaign):
            return False
        campaign.active = True
        return True

    def delete_campaign(self, timestamp: int, campaign_id: str) -> bool:
        """Remove a campaign; False if unknown."""
        if campaign_id not in self._campaigns:
            return False
        del self._campaigns[campaign_id]
        return True
