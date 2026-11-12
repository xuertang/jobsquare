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
from dataclasses import dataclass
from typing import Optional


@dataclass
class Campaign:

    channel: Optional[str] = None
    priority: Optional[int] = None
    status: str = 'active'


class CampaignScheduler:
    """A marketing campaign delivery system: create, pause, resume and delete campaigns."""

    def __init__(self) -> None:
        """Create an empty scheduler."""
        self.campaigns: dict[str, Campaign] = {}

    @staticmethod
    def _format(self, campaign_id: str, campaign: Campaign):
        return f"{campaign_id}(channel={campaign.channel}, priority={campaign.priority}, status={campaign.status})"

    def create_campaign(self, campaign_id: str, channel: str, priority: int) -> bool:
        """Register a new active campaign; False if the id is already taken."""
        if campaign_id in self.campaigns:
            return False
        campaign = Campaign(channel=channel, priority=priority)
        self.campaigns[campaign_id] = campaign
        return True

    def get_campaign(self, campaign_id: str) -> str | None:
        """Return "id(channel=C, priority=P, status=S)" or None if unknown."""
        if campaign_id not in self.campaigns:
            return None
        return self._format(campaign_id, self.campaigns[campaign_id])

    def pause_campaign(self, campaign_id: str) -> bool:
        """Pause an active campaign; False if unknown or already paused."""
        if campaign_id not in self.campaigns or self.campaigns[campaign_id].status == 'paused':
            return False
        self.campaigns[campaign_id].status = 'paused'
        return True

    def resume_campaign(self, campaign_id: str) -> bool:
        """Resume a paused campaign; False if unknown or already active."""
        if campaign_id not in self.campaigns or self.campaigns[campaign_id].status == 'active':
            return False
        self.campaigns[campaign_id].status = 'active'
        return True

    def delete_campaign(self, campaign_id: str) -> bool:
        """Remove a campaign; False if unknown."""
        if campaign_id not in self.campaigns:
            return False
        del self.campaigns[campaign_id]
        return True
