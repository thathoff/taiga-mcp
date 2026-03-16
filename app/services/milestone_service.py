"""Milestone (sprint) service for Taiga API operations."""

from app.core.client import TaigaClient
from app.models.milestone import Milestone


class MilestoneService:
    """Service for managing Taiga milestones (sprints)."""

    def __init__(self, client: TaigaClient) -> None:
        self.client = client

    async def list_milestones(self, project_id: int, closed: bool | None = None) -> list[Milestone]:
        """List milestones in a project."""
        params: dict = {"project": project_id}
        if closed is not None:
            params["closed"] = str(closed).lower()
        data = await self.client.get("/milestones", params=params)
        return [Milestone(**m) for m in data]

    async def get_milestone(self, milestone_id: int) -> Milestone:
        """Get milestone details."""
        data = await self.client.get(f"/milestones/{milestone_id}")
        return Milestone(**data)
