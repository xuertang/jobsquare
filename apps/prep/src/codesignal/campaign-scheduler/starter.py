"""ICF Mock 2 starter file. Copy this to attempt.py and implement.

HOW THIS FILE WORKS
-------------------
This skeleton contains **Level 1 only**. That is deliberate: the drill is about
absorbing a requirement you could not see coming, so the later levels are not
spoiled here. When you reach Level 2, 3 or 4, `PROBLEM.md` gives you that
level's method signatures and you add them to the class yourself -- exactly as
the real CodeSignal editor works, where each level appears only once you get
there.

Run one level at a time:  ICF_IMPL=attempt python3 -m pytest -q -m level1
"""

from __future__ import annotations


class CampaignScheduler:
    """A marketing campaign delivery system: create, pause, resume and delete campaigns."""

    def __init__(self) -> None:
        """Create an empty scheduler."""
        raise NotImplementedError

    def create_campaign(self, campaign_id: str, channel: str, priority: int) -> bool:
        """Register a new active campaign; False if the id is already taken."""
        raise NotImplementedError

    def get_campaign(self, campaign_id: str) -> str | None:
        """Return "id(channel=C, priority=P, status=S)" or None if unknown."""
        raise NotImplementedError

    def pause_campaign(self, campaign_id: str) -> bool:
        """Pause an active campaign; False if unknown or already paused."""
        raise NotImplementedError

    def resume_campaign(self, campaign_id: str) -> bool:
        """Resume a paused campaign; False if unknown or already active."""
        raise NotImplementedError

    def delete_campaign(self, campaign_id: str) -> bool:
        """Remove a campaign; False if unknown."""
        raise NotImplementedError
