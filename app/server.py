"""MCP server for Taiga project management."""

import asyncio
import logging
import sys
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

from app.config import settings
from app.core.auth import auth_manager
from app.core.client import TaigaClient
from app.core.exceptions import TaigaMCPError
from app.models.issue import UpdateIssueRequest
from app.models.task import CreateTaskRequest, UpdateTaskRequest
from app.models.userstory import CreateUserStoryRequest, UpdateUserStoryRequest
from app.services.issue_service import IssueService
from app.services.milestone_service import MilestoneService
from app.services.project_service import ProjectService
from app.services.task_service import TaskService
from app.services.user_service import UserService
from app.services.userstory_service import UserStoryService

# Configure logging to stderr (stdout is used for MCP protocol)
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # Log to stderr, not stdout
)
logger = logging.getLogger(__name__)

# Create MCP server
app = Server("taiga-mcp")


@app.list_resources()
async def list_resources() -> list[Resource]:
    """List available resources."""
    return [
        Resource(
            uri="taiga://docs/api",
            name="Taiga API Documentation",
            mimeType="text/plain",
            description="Documentation for Taiga MCP server capabilities",
        ),
    ]


@app.read_resource()
async def read_resource(uri: str) -> str:
    """Read resource content."""
    if uri == "taiga://docs/api":
        return f"""Taiga MCP Server - API Documentation

This MCP server allows you to interact with Taiga project management platform using natural language.

**Available Tools:**

1. authenticate - Authenticate with Taiga
2. listProjects - List all your Taiga projects
3. getProject - Get detailed information about a specific project
4. listProjectMembers - Get all members of a project
5. createUserStory - Create a new user story in a project
6. listUserStories - List user stories in a project (with pagination)
7. getUserStory - Get detailed information about a specific user story
8. updateUserStory - Update an existing user story
9. listUserStoryTasks - Get all tasks for a user story
10. createTask - Create a new task within a user story
11. updateTask - Update an existing task
12. listMilestones - List sprints (milestones) in a project
13. getMilestone - Get detailed sprint (milestone) information

**Configuration:**

- API URL: {settings.taiga_api_url}
- Authentication: Token-based (auto-refreshed)

**Getting Started:**

1. Authenticate using your Taiga credentials
2. List your projects to get project IDs or slugs
3. Create and manage user stories and tasks

For detailed usage, refer to individual tool descriptions.
"""
    raise ValueError(f"Unknown resource: {uri}")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="authenticate",
            description="Authenticate with Taiga API. Uses credentials from environment variables if not provided.",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Taiga username or email (optional, uses TAIGA_USERNAME env var)",
                    },
                    "password": {
                        "type": "string",
                        "description": "Taiga password (optional, uses TAIGA_PASSWORD env var)",
                    },
                },
            },
        ),
        Tool(
            name="listProjects",
            description="List all projects accessible to the authenticated user",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="getProject",
            description="Get detailed information about a specific project",
            inputSchema={
                "type": "object",
                "properties": {
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug",
                    },
                },
                "required": ["projectIdentifier"],
            },
        ),
        Tool(
            name="listProjectMembers",
            description="List all members of a project",
            inputSchema={
                "type": "object",
                "properties": {
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug",
                    },
                },
                "required": ["projectIdentifier"],
            },
        ),
        Tool(
            name="createUserStory",
            description="Create a new user story in a project",
            inputSchema={
                "type": "object",
                "properties": {
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug",
                    },
                    "subject": {
                        "type": "string",
                        "description": "User story title/subject",
                    },
                    "description": {
                        "type": "string",
                        "description": "User story description (optional)",
                    },
                    "status": {
                        "type": "string",
                        "description": "Status name (e.g., 'New', 'In progress') (optional)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Array of tags (optional)",
                    },
                },
                "required": ["projectIdentifier", "subject"],
            },
        ),
        Tool(
            name="listUserStories",
            description="List user stories in a project with pagination and filter support",
            inputSchema={
                "type": "object",
                "properties": {
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug",
                    },
                    "pageSize": {
                        "type": "number",
                        "description": "Number of stories per page (1-100, default: 100)",
                    },
                    "page": {
                        "type": "number",
                        "description": "Specific page number to fetch (optional)",
                    },
                    "fetchAll": {
                        "type": "boolean",
                        "description": "Whether to fetch all stories across all pages (default: true)",
                    },
                    "assignedTo": {
                        "type": "number",
                        "description": "Filter by assigned user ID (optional)",
                    },
                    "watchers": {
                        "type": "number",
                        "description": "Filter by watcher user ID (optional)",
                    },
                    "isClosed": {
                        "type": "boolean",
                        "description": "Filter by closed status (optional, omit to list all)",
                    },
                },
                "required": ["projectIdentifier"],
            },
        ),
        Tool(
            name="getUserStory",
            description="Get detailed information about a specific user story",
            inputSchema={
                "type": "object",
                "properties": {
                    "userStoryIdentifier": {
                        "type": "string",
                        "description": "User story ID or reference number (e.g., '123' or '#45')",
                    },
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug (required if using reference number)",
                    },
                },
                "required": ["userStoryIdentifier"],
            },
        ),
        Tool(
            name="updateUserStory",
            description="Update an existing user story",
            inputSchema={
                "type": "object",
                "properties": {
                    "userStoryIdentifier": {
                        "type": "string",
                        "description": "User story ID or reference number (e.g., '123' or '#45')",
                    },
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug (required if using reference number)",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Updated user story title/subject (optional)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Updated user story description (optional)",
                    },
                    "status": {
                        "type": "string",
                        "description": "Status name (e.g., 'New', 'In progress', 'Done') (optional)",
                    },
                    "assignedTo": {
                        "type": "string",
                        "description": "Username to assign the story to (optional)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Array of tags (optional)",
                    },
                    "points": {
                        "type": "string",
                        "description": "Story points (e.g., '1', '2', '3', '5', '8') (optional)",
                    },
                    "dueDate": {
                        "type": "string",
                        "description": "Due date in YYYY-MM-DD format (optional)",
                    },
                },
                "required": ["userStoryIdentifier"],
            },
        ),
        Tool(
            name="listUserStoryTasks",
            description="Get all tasks associated with a user story",
            inputSchema={
                "type": "object",
                "properties": {
                    "userStoryIdentifier": {
                        "type": "string",
                        "description": "User story ID or reference number (e.g., '123' or '#45')",
                    },
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug (required if using reference number)",
                    },
                },
                "required": ["userStoryIdentifier"],
            },
        ),
        Tool(
            name="createTask",
            description="Create a new task within a user story",
            inputSchema={
                "type": "object",
                "properties": {
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug",
                    },
                    "userStoryIdentifier": {
                        "type": "string",
                        "description": "User story ID or reference number",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Task title/subject",
                    },
                    "description": {
                        "type": "string",
                        "description": "Task description (optional)",
                    },
                    "status": {
                        "type": "string",
                        "description": "Status name (e.g., 'New', 'In progress') (optional)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Array of tags (optional)",
                    },
                },
                "required": ["projectIdentifier", "userStoryIdentifier", "subject"],
            },
        ),
        Tool(
            name="updateTask",
            description="Update an existing task",
            inputSchema={
                "type": "object",
                "properties": {
                    "taskId": {
                        "type": "string",
                        "description": "Task ID or reference number (e.g., '123' or '#45')",
                    },
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Updated task title/subject (optional)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Updated task description (optional)",
                    },
                    "status": {
                        "type": "string",
                        "description": "Status name (e.g., 'New', 'In progress', 'Done') (optional)",
                    },
                    "assignedTo": {
                        "type": "string",
                        "description": "Username or full name to assign the task to (optional)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Array of tags (optional)",
                    },
                    "comment": {
                        "type": "string",
                        "description": "Comment to add to the task (optional)",
                    },
                },
                "required": ["taskId", "projectIdentifier"],
            },
        ),
        Tool(
            name="listMilestones",
            description="List sprints (milestones) in a project",
            inputSchema={
                "type": "object",
                "properties": {
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug",
                    },
                    "closed": {
                        "type": "boolean",
                        "description": "Filter by closed status (optional, omit to list all)",
                    },
                },
                "required": ["projectIdentifier"],
            },
        ),
        Tool(
            name="getMilestone",
            description="Get detailed information about a specific sprint (milestone)",
            inputSchema={
                "type": "object",
                "properties": {
                    "milestoneId": {
                        "type": "number",
                        "description": "Milestone (sprint) ID",
                    },
                },
                "required": ["milestoneId"],
            },
        ),
        Tool(
            name="listIssues",
            description="List issues in a project with optional filters",
            inputSchema={
                "type": "object",
                "properties": {
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug",
                    },
                    "assignedTo": {
                        "type": "number",
                        "description": "Filter by assigned user ID (optional)",
                    },
                    "watchers": {
                        "type": "number",
                        "description": "Filter by watcher user ID (optional)",
                    },
                    "isClosed": {
                        "type": "boolean",
                        "description": "Filter by closed status (optional, omit to list all)",
                    },
                },
                "required": ["projectIdentifier"],
            },
        ),
        Tool(
            name="listMyUserStories",
            description="List non-closed user stories assigned to or watched by the current user, optionally filtered by project",
            inputSchema={
                "type": "object",
                "properties": {
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug (optional, omit to list across all projects)",
                    },
                },
            },
        ),
        Tool(
            name="listMyTasks",
            description="List non-closed tasks assigned to or watched by the current user, optionally filtered by project",
            inputSchema={
                "type": "object",
                "properties": {
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug (optional, omit to list across all projects)",
                    },
                },
            },
        ),
        Tool(
            name="listMyIssues",
            description="List non-closed issues assigned to or watched by the current user, optionally filtered by project",
            inputSchema={
                "type": "object",
                "properties": {
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug (optional, omit to list across all projects)",
                    },
                },
            },
        ),
        Tool(
            name="commentUserStory",
            description="Add a comment to a user story",
            inputSchema={
                "type": "object",
                "properties": {
                    "userStoryIdentifier": {
                        "type": "string",
                        "description": "User story ID or reference number (e.g., '123' or '#45')",
                    },
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug (required if using reference number)",
                    },
                    "comment": {
                        "type": "string",
                        "description": "Comment text to add",
                    },
                },
                "required": ["userStoryIdentifier", "comment"],
            },
        ),
        Tool(
            name="commentTask",
            description="Add a comment to a task",
            inputSchema={
                "type": "object",
                "properties": {
                    "taskId": {
                        "type": "string",
                        "description": "Task ID or reference number (e.g., '123' or '#45')",
                    },
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug (required if using reference number)",
                    },
                    "comment": {
                        "type": "string",
                        "description": "Comment text to add",
                    },
                },
                "required": ["taskId", "projectIdentifier", "comment"],
            },
        ),
        Tool(
            name="commentIssue",
            description="Add a comment to an issue",
            inputSchema={
                "type": "object",
                "properties": {
                    "issueId": {
                        "type": "string",
                        "description": "Issue ID or reference number (e.g., '123' or '#45')",
                    },
                    "projectIdentifier": {
                        "type": "string",
                        "description": "Project ID or slug (required if using reference number)",
                    },
                    "comment": {
                        "type": "string",
                        "description": "Comment text to add",
                    },
                },
                "required": ["issueId", "projectIdentifier", "comment"],
            },
        ),
    ]


async def resolve_project_id(
    project_service: ProjectService, identifier: str
) -> tuple[int, str]:
    """Resolve project identifier to ID and name."""
    if identifier.isdigit():
        project = await project_service.get_project(int(identifier))
    else:
        project = await project_service.get_project_by_slug(identifier)
    return project.id, project.name


async def resolve_user_story_id(
    userstory_service: UserStoryService,
    project_service: ProjectService,
    user_story_identifier: str,
    project_identifier: Optional[str] = None,
) -> int:
    """Resolve user story identifier to ID."""
    user_story_identifier = str(user_story_identifier).strip()
    if user_story_identifier.startswith("#"):
        if not project_identifier:
            raise ValueError(
                "Project identifier is required when using user story reference number"
            )

        project_id, _ = await resolve_project_id(project_service, project_identifier)
        ref_number = user_story_identifier[1:]

        stories = await userstory_service.list_user_stories(project_id)
        for story in stories:
            if str(story.ref) == ref_number:
                return story.id

        raise ValueError(f"User story with reference {user_story_identifier} not found")

    return int(user_story_identifier)


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")
    try:
        async with TaigaClient() as client:
            project_service = ProjectService(client)
            userstory_service = UserStoryService(client)
            task_service = TaskService(client)
            milestone_service = MilestoneService(client)
            user_service = UserService(client)
            issue_service = IssueService(client)

            if name == "authenticate":
                username = arguments.get("username")
                password = arguments.get("password")
                await auth_manager.authenticate(username, password)
                current_user = await user_service.get_current_user()
                return [
                    TextContent(
                        type="text",
                        text=f"Successfully authenticated as {current_user.full_name} ({current_user.username}).",
                    )
                ]

            elif name == "listProjects":
                # Get current user for filtering
                current_user = await user_service.get_current_user()
                projects = await project_service.list_projects(member_id=current_user.id)
                project_list = "\n".join(
                    [f"- {p.name} (ID: {p.id}, Slug: {p.slug})" for p in projects]
                )
                return [
                    TextContent(
                        type="text",
                        text=f"Your Taiga Projects:\n\n{project_list}",
                    )
                ]

            elif name == "getProject":
                project_id, _ = await resolve_project_id(
                    project_service, arguments["projectIdentifier"]
                )
                project = await project_service.get_project(project_id)
                return [
                    TextContent(
                        type="text",
                        text=f"""Project Details:

Name: {project.name}
ID: {project.id}
Slug: {project.slug}
Description: {project.description or 'No description'}
Created: {project.created_date.strftime('%Y-%m-%d %H:%M:%S')}
Total Members: {project.total_memberships}
Private: {project.is_private}
""",
                    )
                ]

            elif name == "listProjectMembers":
                project_id, _ = await resolve_project_id(
                    project_service, arguments["projectIdentifier"]
                )
                members = await project_service.list_project_members(project_id)
                member_list = "\n".join(
                    [
                        f"- {m.full_name or (m.user_extra_info.get('full_name') if m.user_extra_info else 'Unknown')} "
                        f"(@{m.username or (m.user_extra_info.get('username') if m.user_extra_info else 'unknown')}) - {m.role_name}"
                        for m in members
                    ]
                )
                return [
                    TextContent(
                        type="text",
                        text=f"Project Members:\n\n{member_list}",
                    )
                ]

            elif name == "createUserStory":
                project_id, project_name = await resolve_project_id(
                    project_service, arguments["projectIdentifier"]
                )

                # Resolve status if provided
                status_id = None
                if "status" in arguments and arguments["status"]:
                    statuses = await userstory_service.get_user_story_statuses(project_id)
                    for status in statuses:
                        if status.name.lower() == arguments["status"].lower():
                            status_id = status.id
                            break

                request = CreateUserStoryRequest(
                    project=project_id,
                    subject=arguments["subject"],
                    description=arguments.get("description"),
                    status=status_id,
                    tags=arguments.get("tags"),
                )
                story = await userstory_service.create_user_story(request)

                return [
                    TextContent(
                        type="text",
                        text=f"""User story created successfully!

Subject: {story.subject}
Reference: #{story.ref}
Status: {story.status_extra_info.name if story.status_extra_info else 'Default status'}
Project: {project_name}
""",
                    )
                ]

            elif name == "listUserStories":
                project_id, _ = await resolve_project_id(
                    project_service, arguments["projectIdentifier"]
                )
                page_size = arguments.get("pageSize", 100)
                page = arguments.get("page")
                fetch_all = arguments.get("fetchAll", True)
                assigned_to = arguments.get("assignedTo")
                watchers_filter = arguments.get("watchers")
                is_closed = arguments.get("isClosed")

                stories = await userstory_service.list_user_stories(
                    project_id,
                    page_size=page_size,
                    page=page,
                    fetch_all=fetch_all,
                    assigned_users=assigned_to,
                    watchers=watchers_filter,
                    is_closed=is_closed,
                )

                if not stories:
                    return [
                        TextContent(
                            type="text",
                            text="No user stories found in this project.",
                        )
                    ]

                pagination_info = (
                    f" (Page {page})"
                    if page
                    else f" (All {len(stories)} stories)" if fetch_all else ""
                )
                story_list = "\n".join(
                    [
                        f"- #{s.ref}: {s.subject} (Status: {s.status_extra_info.name if s.status_extra_info else 'Unknown'})"
                        + (f" [BLOCKED: {s.blocked_note or 'Yes'}]" if s.is_blocked else "")
                        for s in stories
                    ]
                )
                return [
                    TextContent(
                        type="text",
                        text=f"User Stories in Project{pagination_info}:\n\n{story_list}",
                    )
                ]

            elif name == "getUserStory":
                user_story_id = await resolve_user_story_id(
                    userstory_service,
                    project_service,
                    arguments["userStoryIdentifier"],
                    arguments.get("projectIdentifier"),
                )
                story = await userstory_service.get_user_story(user_story_id)

                points_display = "None"
                if story.points:
                    if isinstance(story.points, dict):
                        points_display = story.points.get("name", "None")
                    else:
                        points_display = str(story.points)

                return [
                    TextContent(
                        type="text",
                        text=f"""User Story Details:

Subject: {story.subject}
Reference: #{story.ref}
Description: {story.description or 'No description'}
Status: {story.status_extra_info.name if story.status_extra_info else 'Unknown'}
Assigned to: {story.assigned_to_extra_info.full_name if story.assigned_to_extra_info else 'Unassigned'}
Points: {points_display}
Blocked: {('Yes - ' + story.blocked_note) if story.is_blocked and story.blocked_note else ('Yes' if story.is_blocked else 'No')}
Tags: {', '.join(story.tags) if story.tags else 'None'}
Due Date: {story.due_date or 'Not set'}
Created: {story.created_date.strftime('%Y-%m-%d %H:%M:%S')}
Modified: {story.modified_date.strftime('%Y-%m-%d %H:%M:%S')}
Project: {story.project_extra_info.name if story.project_extra_info else 'N/A'}
""",
                    )
                ]

            elif name == "updateUserStory":
                user_story_id = await resolve_user_story_id(
                    userstory_service,
                    project_service,
                    arguments["userStoryIdentifier"],
                    arguments.get("projectIdentifier"),
                )

                # Get current story for version and project ID
                current_story = await userstory_service.get_user_story(user_story_id)
                project_id = current_story.project

                # Build update request
                update_data = {"version": current_story.version}

                if "subject" in arguments:
                    update_data["subject"] = arguments["subject"]
                if "description" in arguments:
                    update_data["description"] = arguments["description"]
                if "tags" in arguments:
                    update_data["tags"] = arguments["tags"]
                if "points" in arguments and arguments["points"]:
                    # Note: Taiga uses role-based story points in some configurations
                    # Simple projects: points can be a decimal (e.g., 5.0)
                    # Complex projects with roles: points is a dict like {"role_id": value}
                    # For now, we'll try to use the existing points structure from the story
                    points_value = arguments["points"]

                    # If current story has points as dict (role-based), we need to maintain that structure
                    if isinstance(current_story.points, dict) and current_story.points:
                        # Get the first role from existing points and update its value
                        role_keys = list(current_story.points.keys())
                        if role_keys:
                            first_role = role_keys[0]
                            try:
                                update_data["points"] = {first_role: float(points_value)}
                            except (ValueError, TypeError):
                                logger.warning(f"Could not convert points value '{points_value}' to float")
                    else:
                        # Simple decimal points
                        try:
                            update_data["points"] = float(points_value) if points_value else None
                        except (ValueError, TypeError):
                            update_data["points"] = points_value
                if "dueDate" in arguments:
                    update_data["due_date"] = arguments["dueDate"]

                # Resolve status if provided
                if "status" in arguments and arguments["status"]:
                    statuses = await userstory_service.get_user_story_statuses(project_id)
                    status_found = False
                    for status in statuses:
                        if status.name.lower() == arguments["status"].lower():
                            update_data["status"] = status.id
                            status_found = True
                            break
                    if not status_found:
                        status_names = ", ".join([s.name for s in statuses])
                        return [
                            TextContent(
                                type="text",
                                text=f"Error: Status '{arguments['status']}' not found. Available statuses: {status_names}",
                            )
                        ]

                # Resolve assigned user if provided
                if "assignedTo" in arguments and arguments["assignedTo"]:
                    members = await project_service.list_project_members(project_id)
                    member_found = False
                    for member in members:
                        # Get username and full_name from either direct fields or user_extra_info
                        username = member.username or (member.user_extra_info.get("username") if member.user_extra_info else None)
                        full_name = member.full_name or (member.user_extra_info.get("full_name") if member.user_extra_info else None)

                        if username and username.lower() == arguments["assignedTo"].lower():
                            update_data["assigned_to"] = member.user
                            member_found = True
                            break
                        if full_name and full_name.lower() == arguments["assignedTo"].lower():
                            update_data["assigned_to"] = member.user
                            member_found = True
                            break

                    if not member_found:
                        usernames = ", ".join([
                            m.username or (m.user_extra_info.get("username") if m.user_extra_info else "unknown")
                            for m in members
                        ])
                        return [
                            TextContent(
                                type="text",
                                text=f"Error: User '{arguments['assignedTo']}' not found in project. Available members: {usernames}",
                            )
                        ]

                logger.debug(f"Update data being sent: {update_data}")
                request = UpdateUserStoryRequest(**update_data)
                story = await userstory_service.update_user_story(user_story_id, request)

                points_display = "None"
                if story.points:
                    if isinstance(story.points, dict):
                        points_display = story.points.get("name", "None")
                    else:
                        points_display = str(story.points)

                return [
                    TextContent(
                        type="text",
                        text=f"""User story updated successfully!

Subject: {story.subject}
Reference: #{story.ref}
Status: {story.status_extra_info.name if story.status_extra_info else 'Unknown'}
Assigned to: {story.assigned_to_extra_info.full_name if story.assigned_to_extra_info else 'Unassigned'}
Points: {points_display}
Blocked: {('Yes - ' + story.blocked_note) if story.is_blocked and story.blocked_note else ('Yes' if story.is_blocked else 'No')}
Project: {story.project_extra_info.name if story.project_extra_info else 'N/A'}
""",
                    )
                ]

            elif name == "listUserStoryTasks":
                user_story_id = await resolve_user_story_id(
                    userstory_service,
                    project_service,
                    arguments["userStoryIdentifier"],
                    arguments.get("projectIdentifier"),
                )
                tasks = await task_service.list_tasks(user_story_id)

                if not tasks:
                    return [
                        TextContent(
                            type="text",
                            text="No tasks found for this user story.",
                        )
                    ]

                task_list = "\n".join(
                    [
                        f"- #{t.ref}: {t.subject} (Status: {t.status_extra_info.name if t.status_extra_info else 'Unknown'}, "
                        f"Assigned: {t.assigned_to_extra_info.full_name if t.assigned_to_extra_info else 'Unassigned'})"
                        for t in tasks
                    ]
                )
                return [
                    TextContent(
                        type="text",
                        text=f"Tasks in User Story:\n\n{task_list}",
                    )
                ]

            elif name == "createTask":
                project_id, project_name = await resolve_project_id(
                    project_service, arguments["projectIdentifier"]
                )
                user_story_id = await resolve_user_story_id(
                    userstory_service,
                    project_service,
                    arguments["userStoryIdentifier"],
                    arguments["projectIdentifier"],
                )

                # Resolve status if provided
                status_id = None
                if "status" in arguments and arguments["status"]:
                    statuses = await task_service.get_task_statuses(project_id)
                    for status in statuses:
                        if status.name.lower() == arguments["status"].lower():
                            status_id = status.id
                            break

                request = CreateTaskRequest(
                    project=project_id,
                    user_story=user_story_id,
                    subject=arguments["subject"],
                    description=arguments.get("description"),
                    status=status_id,
                    tags=arguments.get("tags"),
                )
                task = await task_service.create_task(request)

                return [
                    TextContent(
                        type="text",
                        text=f"""Task created successfully!

Subject: {task.subject}
Reference: #{task.ref}
Status: {task.status_extra_info.name if task.status_extra_info else 'Default status'}
Project: {project_name}
User Story: #{task.user_story_extra_info.ref if task.user_story_extra_info else 'N/A'} - {task.user_story_extra_info.subject if task.user_story_extra_info else 'N/A'}
""",
                    )
                ]

            elif name == "updateTask":
                project_id, _ = await resolve_project_id(
                    project_service, arguments["projectIdentifier"]
                )

                # Resolve task ID (support both ID and #ref)
                task_identifier = str(arguments["taskId"]).strip()
                if task_identifier.startswith("#"):
                    current_task = await task_service.get_task_by_ref(
                        int(task_identifier[1:]), project_id
                    )
                else:
                    current_task = await task_service.get_task(int(task_identifier))
                task_id = current_task.id

                # Build update request
                update_data = {"version": current_task.version}

                if "subject" in arguments:
                    update_data["subject"] = arguments["subject"]
                if "description" in arguments:
                    update_data["description"] = arguments["description"]
                if "tags" in arguments:
                    update_data["tags"] = arguments["tags"]
                if "comment" in arguments and arguments["comment"]:
                    update_data["comment"] = arguments["comment"]

                # Resolve status if provided
                if "status" in arguments and arguments["status"]:
                    statuses = await task_service.get_task_statuses(project_id)
                    status_found = False
                    for status in statuses:
                        if status.name.lower() == arguments["status"].lower():
                            update_data["status"] = status.id
                            status_found = True
                            break
                    if not status_found:
                        status_names = ", ".join([s.name for s in statuses])
                        return [
                            TextContent(
                                type="text",
                                text=f"Error: Status '{arguments['status']}' not found. Available statuses: {status_names}",
                            )
                        ]

                # Resolve assigned user if provided
                if "assignedTo" in arguments and arguments["assignedTo"]:
                    members = await project_service.list_project_members(project_id)
                    member_found = False
                    for member in members:
                        username = member.username or (member.user_extra_info.get("username") if member.user_extra_info else None)
                        full_name = member.full_name or (member.user_extra_info.get("full_name") if member.user_extra_info else None)

                        if username and username.lower() == arguments["assignedTo"].lower():
                            update_data["assigned_to"] = member.user
                            member_found = True
                            break
                        if full_name and full_name.lower() == arguments["assignedTo"].lower():
                            update_data["assigned_to"] = member.user
                            member_found = True
                            break

                    if not member_found:
                        usernames = ", ".join([
                            m.username or (m.user_extra_info.get("username") if m.user_extra_info else "unknown")
                            for m in members
                        ])
                        return [
                            TextContent(
                                type="text",
                                text=f"Error: User '{arguments['assignedTo']}' not found in project. Available members: {usernames}",
                            )
                        ]

                logger.debug(f"Update data being sent: {update_data}")
                request = UpdateTaskRequest(**update_data)
                task = await task_service.update_task(task_id, request)

                return [
                    TextContent(
                        type="text",
                        text=f"""Task updated successfully!

Subject: {task.subject}
Reference: #{task.ref}
Status: {task.status_extra_info.name if task.status_extra_info else 'Unknown'}
Assigned to: {task.assigned_to_extra_info.full_name if task.assigned_to_extra_info else 'Unassigned'}
Tags: {', '.join(task.tags) if task.tags else 'None'}
Project: {task.project_extra_info.name if task.project_extra_info else 'N/A'}
User Story: #{task.user_story_extra_info.ref if task.user_story_extra_info else 'N/A'} - {task.user_story_extra_info.subject if task.user_story_extra_info else 'N/A'}
""",
                    )
                ]

            elif name == "listMilestones":
                project_id, project_name = await resolve_project_id(
                    project_service, arguments["projectIdentifier"]
                )
                closed = arguments.get("closed")
                milestones = await milestone_service.list_milestones(project_id, closed=closed)

                if not milestones:
                    return [
                        TextContent(
                            type="text",
                            text="No sprints (milestones) found in this project.",
                        )
                    ]

                milestone_list = "\n".join(
                    [
                        f"- {m.name} (ID: {m.id}, "
                        f"Start: {m.estimated_start or 'Not set'}, "
                        f"End: {m.estimated_finish or 'Not set'}, "
                        f"Closed: {m.closed}, "
                        f"Points: {m.closed_points or 0}/{m.total_points or 0})"
                        for m in milestones
                    ]
                )
                return [
                    TextContent(
                        type="text",
                        text=f"Sprints in {project_name}:\n\n{milestone_list}",
                    )
                ]

            elif name == "getMilestone":
                milestone = await milestone_service.get_milestone(
                    int(arguments["milestoneId"])
                )

                stories_display = ""
                if milestone.user_stories:
                    stories_display = "\n\nUser Stories:\n" + "\n".join(
                        [
                            f"- #{s.get('ref', 'N/A')}: {s.get('subject', 'N/A')} "
                            f"(Closed: {s.get('is_closed', False)})"
                            for s in milestone.user_stories
                        ]
                    )

                return [
                    TextContent(
                        type="text",
                        text=f"""Sprint Details:

Name: {milestone.name}
ID: {milestone.id}
Slug: {milestone.slug}
Closed: {milestone.closed}
Start: {milestone.estimated_start or 'Not set'}
End: {milestone.estimated_finish or 'Not set'}
Points: {milestone.closed_points or 0}/{milestone.total_points or 0}
Created: {milestone.created_date.strftime('%Y-%m-%d %H:%M:%S')}
Modified: {milestone.modified_date.strftime('%Y-%m-%d %H:%M:%S')}
{stories_display}""",
                    )
                ]

            elif name == "listIssues":
                project_id, project_name = await resolve_project_id(
                    project_service, arguments["projectIdentifier"]
                )
                assigned_to = arguments.get("assignedTo")
                watchers_filter = arguments.get("watchers")
                is_closed = arguments.get("isClosed")

                issues = await issue_service.list_issues(
                    project_id,
                    assigned_to=assigned_to,
                    watchers=watchers_filter,
                    status__is_closed=is_closed,
                )

                if not issues:
                    return [
                        TextContent(
                            type="text",
                            text="No issues found matching the filters.",
                        )
                    ]

                issue_list = "\n".join(
                    [
                        f"- #{i.ref}: {i.subject} (Status: {i.status_extra_info.name if i.status_extra_info else 'Unknown'}, "
                        f"Assigned: {i.assigned_to_extra_info.full_name if i.assigned_to_extra_info else 'Unassigned'})"
                        for i in issues
                    ]
                )
                return [
                    TextContent(
                        type="text",
                        text=f"Issues in {project_name}:\n\n{issue_list}",
                    )
                ]

            elif name == "listMyUserStories":
                project_id = None
                scope_label = "all projects"
                if arguments.get("projectIdentifier"):
                    project_id, project_name = await resolve_project_id(
                        project_service, arguments["projectIdentifier"]
                    )
                    scope_label = project_name

                current_user = await user_service.get_current_user()
                user_id = current_user.id

                # Fetch assigned and watched stories in parallel
                assigned_stories, watched_stories = await asyncio.gather(
                    userstory_service.list_user_stories(
                        project_id, assigned_users=user_id, is_closed=False
                    ),
                    userstory_service.list_user_stories(
                        project_id, watchers=user_id, is_closed=False
                    ),
                )

                # Merge and deduplicate by ID
                seen_ids: set[int] = set()
                stories: list = []
                for story in assigned_stories + watched_stories:
                    if story.id not in seen_ids:
                        seen_ids.add(story.id)
                        stories.append(story)

                if not stories:
                    return [
                        TextContent(
                            type="text",
                            text=f"No open user stories assigned to or watched by you in {scope_label}.",
                        )
                    ]

                story_list = "\n".join(
                    [
                        f"- #{s.ref}: {s.subject} "
                        f"(Project: {s.project_extra_info.name if s.project_extra_info else 'N/A'}, "
                        f"Status: {s.status_extra_info.name if s.status_extra_info else 'Unknown'}, "
                        f"Assigned: {s.assigned_to_extra_info.full_name if s.assigned_to_extra_info else 'Unassigned'})"
                        + (f" [BLOCKED: {s.blocked_note or 'Yes'}]" if s.is_blocked else "")
                        for s in stories
                    ]
                )
                return [
                    TextContent(
                        type="text",
                        text=f"Your open user stories in {scope_label} ({len(stories)}):\n\n{story_list}",
                    )
                ]

            elif name == "listMyTasks":
                project_id = None
                scope_label = "all projects"
                if arguments.get("projectIdentifier"):
                    project_id, project_name = await resolve_project_id(
                        project_service, arguments["projectIdentifier"]
                    )
                    scope_label = project_name

                current_user = await user_service.get_current_user()
                user_id = current_user.id

                assigned_tasks, watched_tasks = await asyncio.gather(
                    task_service.list_tasks(
                        project_id=project_id, assigned_to=user_id, status__is_closed=False
                    ),
                    task_service.list_tasks(
                        project_id=project_id, watchers=user_id, status__is_closed=False
                    ),
                )

                seen_ids: set[int] = set()
                tasks: list = []
                for task in assigned_tasks + watched_tasks:
                    if task.id not in seen_ids:
                        seen_ids.add(task.id)
                        tasks.append(task)

                if not tasks:
                    return [
                        TextContent(
                            type="text",
                            text=f"No open tasks assigned to or watched by you in {scope_label}.",
                        )
                    ]

                task_list = "\n".join(
                    [
                        f"- #{t.ref}: {t.subject} "
                        f"(Project: {t.project_extra_info.name if t.project_extra_info else 'N/A'}, "
                        f"Status: {t.status_extra_info.name if t.status_extra_info else 'Unknown'}, "
                        f"Assigned: {t.assigned_to_extra_info.full_name if t.assigned_to_extra_info else 'Unassigned'}, "
                        f"Story: #{t.user_story_extra_info.ref if t.user_story_extra_info else 'N/A'})"
                        for t in tasks
                    ]
                )
                return [
                    TextContent(
                        type="text",
                        text=f"Your open tasks in {scope_label} ({len(tasks)}):\n\n{task_list}",
                    )
                ]

            elif name == "listMyIssues":
                project_id = None
                scope_label = "all projects"
                if arguments.get("projectIdentifier"):
                    project_id, project_name = await resolve_project_id(
                        project_service, arguments["projectIdentifier"]
                    )
                    scope_label = project_name

                current_user = await user_service.get_current_user()
                user_id = current_user.id

                assigned_issues, watched_issues = await asyncio.gather(
                    issue_service.list_issues(
                        project_id, assigned_to=user_id, status__is_closed=False
                    ),
                    issue_service.list_issues(
                        project_id, watchers=user_id, status__is_closed=False
                    ),
                )

                seen_ids: set[int] = set()
                issues: list = []
                for issue in assigned_issues + watched_issues:
                    if issue.id not in seen_ids:
                        seen_ids.add(issue.id)
                        issues.append(issue)

                if not issues:
                    return [
                        TextContent(
                            type="text",
                            text=f"No open issues assigned to or watched by you in {scope_label}.",
                        )
                    ]

                issue_list = "\n".join(
                    [
                        f"- #{i.ref}: {i.subject} "
                        f"(Project: {i.project_extra_info.name if i.project_extra_info else 'N/A'}, "
                        f"Status: {i.status_extra_info.name if i.status_extra_info else 'Unknown'}, "
                        f"Assigned: {i.assigned_to_extra_info.full_name if i.assigned_to_extra_info else 'Unassigned'})"
                        for i in issues
                    ]
                )
                return [
                    TextContent(
                        type="text",
                        text=f"Your open issues in {scope_label} ({len(issues)}):\n\n{issue_list}",
                    )
                ]

            elif name == "commentUserStory":
                user_story_id = await resolve_user_story_id(
                    userstory_service,
                    project_service,
                    arguments["userStoryIdentifier"],
                    arguments.get("projectIdentifier"),
                )
                current_story = await userstory_service.get_user_story(user_story_id)
                request = UpdateUserStoryRequest(
                    version=current_story.version,
                    comment=arguments["comment"],
                )
                story = await userstory_service.update_user_story(user_story_id, request)
                return [
                    TextContent(
                        type="text",
                        text=f"Comment added to user story #{story.ref}: {story.subject}",
                    )
                ]

            elif name == "commentTask":
                project_id, _ = await resolve_project_id(
                    project_service, arguments["projectIdentifier"]
                )
                task_identifier = str(arguments["taskId"]).strip()
                if task_identifier.startswith("#"):
                    current_task = await task_service.get_task_by_ref(
                        int(task_identifier[1:]), project_id
                    )
                else:
                    current_task = await task_service.get_task(int(task_identifier))

                request = UpdateTaskRequest(
                    version=current_task.version,
                    comment=arguments["comment"],
                )
                task = await task_service.update_task(current_task.id, request)
                return [
                    TextContent(
                        type="text",
                        text=f"Comment added to task #{task.ref}: {task.subject}",
                    )
                ]

            elif name == "commentIssue":
                project_id, _ = await resolve_project_id(
                    project_service, arguments["projectIdentifier"]
                )
                issue_identifier = str(arguments["issueId"]).strip()
                if issue_identifier.startswith("#"):
                    current_issue = await issue_service.get_issue_by_ref(
                        int(issue_identifier[1:]), project_id
                    )
                else:
                    current_issue = await issue_service.get_issue(int(issue_identifier))

                request = UpdateIssueRequest(
                    version=current_issue.version,
                    comment=arguments["comment"],
                )
                issue = await issue_service.update_issue(current_issue.id, request)
                return [
                    TextContent(
                        type="text",
                        text=f"Comment added to issue #{issue.ref}: {issue.subject}",
                    )
                ]

            else:
                raise ValueError(f"Unknown tool: {name}")

    except TaigaMCPError as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]
    except Exception as e:
        logger.exception("Unexpected error in tool call")
        return [TextContent(type="text", text=f"Unexpected error: {str(e)}")]


async def main() -> None:
    """Run the MCP server."""
    logger.info("Starting Taiga MCP server...")
    logger.info(f"API URL: {settings.taiga_api_url}")
    logger.info(f"Debug mode: {settings.debug}")

    async with stdio_server() as (read_stream, write_stream):
        logger.info("Server ready, waiting for MCP messages on stdin/stdout")
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
