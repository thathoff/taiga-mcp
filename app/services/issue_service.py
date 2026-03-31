"""Issue service for Taiga API operations."""

from typing import Optional

from app.core.client import TaigaClient
from app.models.issue import Issue
from app.models.status import IssueStatus


class IssueService:
    """Service for managing Taiga issues."""

    def __init__(self, client: TaigaClient) -> None:
        self.client = client

    async def list_issues(
        self,
        project_id: Optional[int] = None,
        assigned_to: Optional[int] = None,
        watchers: Optional[int] = None,
        status__is_closed: Optional[bool] = None,
    ) -> list[Issue]:
        """
        List issues with optional filters.

        Args:
            project_id: Project ID (optional, omit to list across all projects)
            assigned_to: Filter by assigned user ID
            watchers: Filter by watcher user ID
            status__is_closed: Filter by closed status

        Returns:
            List of issues
        """
        params: dict = {}
        if project_id is not None:
            params["project"] = project_id
        if assigned_to is not None:
            params["assigned_to"] = assigned_to
        if watchers is not None:
            params["watchers"] = watchers
        if status__is_closed is not None:
            params["status__is_closed"] = str(status__is_closed).lower()

        data = await self.client.get("/issues", params=params)
        return [Issue(**issue) for issue in data]

    async def get_issue(self, issue_id: int) -> Issue:
        """Get issue details."""
        data = await self.client.get(f"/issues/{issue_id}")
        return Issue(**data)

    async def get_issue_statuses(self, project_id: int) -> list[IssueStatus]:
        """Get available statuses for issues in a project."""
        data = await self.client.get("/issue-statuses", params={"project": project_id})
        return [IssueStatus(**status) for status in data]
