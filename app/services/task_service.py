"""Task service for Taiga API operations."""

from typing import Optional

from app.core.client import TaigaClient
from app.models.status import TaskStatus
from app.models.task import CreateTaskRequest, Task, UpdateTaskRequest


class TaskService:
    """Service for managing Taiga tasks."""

    def __init__(self, client: TaigaClient) -> None:
        self.client = client

    async def list_tasks(
        self,
        user_story_id: Optional[int] = None,
        project_id: Optional[int] = None,
        assigned_to: Optional[int] = None,
        watchers: Optional[int] = None,
        status__is_closed: Optional[bool] = None,
    ) -> list[Task]:
        """
        List tasks with optional filters.

        Args:
            user_story_id: Filter by user story ID
            project_id: Filter by project ID
            assigned_to: Filter by assigned user ID
            watchers: Filter by watcher user ID
            status__is_closed: Filter by closed status

        Returns:
            List of tasks
        """
        params: dict = {}
        if user_story_id is not None:
            params["user_story"] = user_story_id
        if project_id is not None:
            params["project"] = project_id
        if assigned_to is not None:
            params["assigned_to"] = assigned_to
        if watchers is not None:
            params["watchers"] = watchers
        if status__is_closed is not None:
            params["status__is_closed"] = str(status__is_closed).lower()

        data = await self.client.get("/tasks", params=params)
        return [Task(**task) for task in data]

    async def get_task_by_ref(self, ref: int, project_id: int) -> Task:
        """
        Get task by reference number and project ID.

        Args:
            ref: Task reference number
            project_id: Project ID

        Returns:
            Task details
        """
        data = await self.client.get(
            "/tasks/by_ref", params={"ref": ref, "project": project_id}
        )
        return Task(**data)

    async def get_task(self, task_id: int) -> Task:
        """
        Get task details.

        Args:
            task_id: Task ID

        Returns:
            Task details
        """
        data = await self.client.get(f"/tasks/{task_id}")
        return Task(**data)

    async def create_task(self, request: CreateTaskRequest) -> Task:
        """
        Create a new task.

        Args:
            request: Task creation request

        Returns:
            Created task
        """
        data = await self.client.post(
            "/tasks",
            request.model_dump(exclude_none=True),
        )
        return Task(**data)

    async def update_task(self, task_id: int, request: UpdateTaskRequest) -> Task:
        """
        Update an existing task.

        Args:
            task_id: Task ID
            request: Task update request

        Returns:
            Updated task
        """
        data = await self.client.patch(
            f"/tasks/{task_id}",
            request.model_dump(exclude_none=True),
        )
        return Task(**data)

    async def get_task_statuses(self, project_id: int) -> list[TaskStatus]:
        """
        Get available statuses for tasks in a project.

        Args:
            project_id: Project ID

        Returns:
            List of task statuses
        """
        data = await self.client.get("/task-statuses", params={"project": project_id})
        return [TaskStatus(**status) for status in data]
