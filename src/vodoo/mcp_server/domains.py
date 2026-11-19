"""Domain tools for the Vodoo MCP server: projects, tasks, helpdesk, CRM, knowledge,
documents, activities, and tags.

These mirror the ``vodoo`` CLI commands with friendly filters (names instead of
domains) and reuse the async namespaces on :class:`AsyncOdooClient`. Chatter,
attachments, fields, URLs, and plain field updates stay generic (see server.py).
"""

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from vodoo.aio.client import AsyncOdooClient
from vodoo.content import Markdown
from vodoo.crm import compute_health_flags
from vodoo.documents import _decode_document_data, _safe_document_filename
from vodoo.generated.activities import _GeneratedActivityAttrs
from vodoo.generated.crm import _GeneratedCRMAttrs
from vodoo.generated.documents import _GeneratedDocumentAttrs
from vodoo.generated.helpdesk import _GeneratedHelpdeskAttrs
from vodoo.generated.knowledge import _GeneratedKnowledgeAttrs
from vodoo.generated.project_tasks import _GeneratedTaskAttrs
from vodoo.generated.projects import _GeneratedProjectAttrs
from vodoo.mcp_server._common import (
    ClientHolder,
    FilePolicy,
    check_extra,
    clamp_limit,
    guard_delete,
    search_page,
    write_new_file,
)

TagKind = Literal["task", "ticket", "lead"]
_TAG_MODELS: dict[str, tuple[str, str]] = {
    # kind -> (record model, tag model)
    "task": ("project.task", "project.tags"),
    "ticket": ("helpdesk.ticket", "helpdesk.tag"),
    "lead": ("crm.lead", "crm.tag"),
}
_ACTIVITY_TODO_XMLID = "mail_activity_data_todo"

Register = Callable[..., None]
RecordUrl = Callable[[AsyncOdooClient, str, int], Awaitable[str]]

Limit = Annotated[int, Field(description="Max records (1-500).")]
Offset = Annotated[int, Field(ge=0)]
Mine = Annotated[bool, Field(description="Only records assigned to the connected user.")]
Fields = Annotated[
    list[str] | None, Field(description="Fields to return. Omit for a curated default set.")
]
Extra = Annotated[
    dict[str, Any] | None,
    Field(description="Any other field values (Odoo field names; see get_fields)."),
]


def _ilike(domain: list[Any], field: str, value: str | None) -> None:
    if value:
        domain.append((field, "ilike", value))


def _or_ilike(domain: list[Any], fields: list[str], value: str | None) -> None:
    """Match *value* in any of *fields* (Odoo prefix OR)."""
    if not value:
        return
    domain.extend(["|"] * (len(fields) - 1))
    domain.extend((field, "ilike", value) for field in fields)


def register_domain_tools(  # noqa: PLR0915
    register: Register,
    holder: ClientHolder,
    files: FilePolicy,
    *,
    allow_write: bool,
    allow_delete: bool,
    record_url: RecordUrl,
) -> None:
    """Register the domain tools; write tools only when *allow_write*."""

    field_cache: dict[str, set[str]] = {}

    async def _field_names(odoo: AsyncOdooClient, model: str) -> set[str]:
        if model not in field_cache:
            field_cache[model] = set(await odoo.fields_get(model, attributes=["type"]))
        return field_cache[model]

    # -- Projects & tasks (read) ---------------------------------------------

    async def list_tasks(
        project: Annotated[str | None, Field(description="Project name (substring).")] = None,
        stage: Annotated[str | None, Field(description="Stage name (substring).")] = None,
        assigned_to: Annotated[str | None, Field(description="Assignee name (substring).")] = None,
        mine: Mine = False,
        search: Annotated[str | None, Field(description="Text in the task name.")] = None,
        tag: Annotated[str | None, Field(description="Tag name (substring).")] = None,
        milestone_id: int | None = None,
        parent_id: Annotated[int | None, Field(description="Only subtasks of this task.")] = None,
        deadline_before: Annotated[str | None, Field(description="YYYY-MM-DD.")] = None,
        include_closed: Annotated[
            bool, Field(description="Also done and cancelled tasks.")
        ] = False,
        fields: Fields = None,
        limit: Limit = 50,
        offset: Offset = 0,
        order: str = "priority desc, date_deadline, id desc",
    ) -> dict[str, Any]:
        """List project tasks with name-based filters."""
        odoo = await holder.get()
        domain: list[Any] = []
        _ilike(domain, "project_id.name", project)
        _ilike(domain, "stage_id.name", stage)
        _ilike(domain, "user_ids.name", assigned_to)
        _ilike(domain, "name", search)
        _ilike(domain, "tag_ids.name", tag)
        if mine:
            domain.append(("user_ids", "in", [await odoo.get_uid()]))
        if milestone_id is not None:
            domain.append(("milestone_id", "=", milestone_id))
        if parent_id is not None:
            domain.append(("parent_id", "=", parent_id))
        if deadline_before:
            domain.append(("date_deadline", "<", deadline_before))
        if not include_closed and "state" in await _field_names(odoo, "project.task"):
            domain.append(("state", "not in", ["1_done", "1_canceled"]))
        return await search_page(
            odoo,
            "project.task",
            domain,
            fields or list(_GeneratedTaskAttrs._default_fields),
            limit,
            offset,
            order,
        )

    async def get_task_context(
        task_id: int,
        extra_fields: Annotated[
            list[str] | None, Field(description="Additional task fields to include.")
        ] = None,
        page_size: Annotated[int, Field(ge=1, le=200)] = 50,
        max_pages: Annotated[
            int, Field(ge=1, description="Pages of chatter/attachments per section.")
        ] = 2,
    ) -> dict[str, Any]:
        """Everything about one task in one call: fields, project, stage, assignees,
        tags, parent/subtasks, dependencies, milestone, chatter, attachments, and URL.

        Sections that are cut off by max_pages are reported, with how to continue.
        """
        odoo = await holder.get()
        context: dict[str, Any] = await odoo.tasks.context(
            task_id, extra_fields, page_size=page_size, max_pages=max_pages
        )
        return context

    async def list_projects(
        name: Annotated[str | None, Field(description="Project name (substring).")] = None,
        manager: Annotated[str | None, Field(description="Project manager name.")] = None,
        partner: Annotated[str | None, Field(description="Customer name.")] = None,
        fields: Fields = None,
        limit: Limit = 50,
        offset: Offset = 0,
    ) -> dict[str, Any]:
        """List projects."""
        odoo = await holder.get()
        domain: list[Any] = []
        _ilike(domain, "name", name)
        _ilike(domain, "user_id.name", manager)
        _ilike(domain, "partner_id.name", partner)
        return await search_page(
            odoo,
            "project.project",
            domain,
            fields or list(_GeneratedProjectAttrs._default_fields),
            limit,
            offset,
            "sequence, name",
        )

    async def list_project_stages(
        project_id: Annotated[int | None, Field(description="Only this project's stages.")] = None,
    ) -> list[dict[str, Any]]:
        """List task stages (columns), to find a stage_id for create_task or update_records."""
        odoo = await holder.get()
        rows: list[dict[str, Any]] = await odoo.projects.stages(project_id)
        return rows

    async def list_milestones(
        project: Annotated[int | str, Field(description="Project id or exact name.")],
    ) -> list[dict[str, Any]]:
        """List a project's milestones with deadline and reached state."""
        odoo = await holder.get()
        rows: list[dict[str, Any]] = await odoo.projects.milestones(project)
        return rows

    async def list_milestone_tasks(milestone_id: int) -> list[dict[str, Any]]:
        """List the tasks assigned to a milestone."""
        odoo = await holder.get()
        rows: list[dict[str, Any]] = await odoo.projects.milestone_tasks(milestone_id)
        return rows

    # -- Helpdesk (read) -----------------------------------------------------

    async def list_tickets(
        stage: Annotated[str | None, Field(description="Stage name (substring).")] = None,
        team: Annotated[str | None, Field(description="Helpdesk team name.")] = None,
        partner: Annotated[str | None, Field(description="Customer name.")] = None,
        assigned_to: Annotated[str | None, Field(description="Assignee name.")] = None,
        mine: Mine = False,
        search: Annotated[
            str | None, Field(description="Text in subject, customer email, or number.")
        ] = None,
        include_closed: Annotated[bool, Field(description="Also closed tickets.")] = False,
        fields: Fields = None,
        limit: Limit = 50,
        offset: Offset = 0,
        order: str = "priority desc, create_date desc",
    ) -> dict[str, Any]:
        """List helpdesk tickets with name-based filters."""
        odoo = await holder.get()
        domain: list[Any] = []
        _ilike(domain, "stage_id.name", stage)
        _ilike(domain, "team_id.name", team)
        _ilike(domain, "partner_id.name", partner)
        _ilike(domain, "user_id.name", assigned_to)
        if mine:
            domain.append(("user_id", "=", await odoo.get_uid()))
        search_fields = ["name", "partner_email"]
        if search and "ticket_ref" in await _field_names(odoo, "helpdesk.ticket"):
            search_fields.append("ticket_ref")
        _or_ilike(domain, search_fields, search)
        if not include_closed:
            domain.append(("stage_id.fold", "=", False))
        return await search_page(
            odoo,
            "helpdesk.ticket",
            domain,
            fields or list(_GeneratedHelpdeskAttrs._default_fields),
            limit,
            offset,
            order,
        )

    # -- CRM (read) ----------------------------------------------------------

    async def list_leads(
        lead_type: Annotated[
            Literal["lead", "opportunity"] | None, Field(description="Omit for both.")
        ] = None,
        stage: Annotated[str | None, Field(description="Stage name (substring).")] = None,
        team: Annotated[str | None, Field(description="Sales team name.")] = None,
        salesperson: Annotated[str | None, Field(description="Salesperson name.")] = None,
        mine: Mine = False,
        partner: Annotated[str | None, Field(description="Customer name.")] = None,
        search: Annotated[
            str | None, Field(description="Text in name, email, phone, contact, description.")
        ] = None,
        fields: Fields = None,
        limit: Limit = 50,
        offset: Offset = 0,
        order: str = "create_date desc",
    ) -> dict[str, Any]:
        """List CRM leads and opportunities."""
        odoo = await holder.get()
        domain: list[Any] = []
        _or_ilike(domain, ["name", "email_from", "phone", "contact_name", "description"], search)
        _ilike(domain, "stage_id.name", stage)
        _ilike(domain, "team_id.name", team)
        _ilike(domain, "user_id.name", salesperson)
        _ilike(domain, "partner_id.name", partner)
        if mine:
            domain.append(("user_id", "=", await odoo.get_uid()))
        if lead_type:
            domain.append(("type", "=", lead_type))
        return await search_page(
            odoo,
            "crm.lead",
            domain,
            fields or list(_GeneratedCRMAttrs._default_fields),
            limit,
            offset,
            order,
        )

    async def list_crm_stages(team_id: int | None = None) -> list[dict[str, Any]]:
        """List CRM pipeline stages."""
        odoo = await holder.get()
        rows: list[dict[str, Any]] = await odoo.crm.stages(team_id=team_id)
        return rows

    async def crm_pipeline(
        team: Annotated[str | None, Field(description="Sales team name.")] = None,
        salesperson: Annotated[str | None, Field(description="Salesperson name.")] = None,
        health: Annotated[
            bool, Field(description="Add health flags (stale deals, missing data).")
        ] = True,
        include_deals: Annotated[bool, Field(description="List the deals per stage.")] = False,
    ) -> dict[str, Any]:
        """Pipeline summary: deals, revenue, and weighted revenue per stage."""
        odoo = await holder.get()
        summary: dict[str, Any] = await odoo.crm.pipeline(team=team, user=salesperson)
        if health:
            summary["health_flags"] = compute_health_flags(summary)
        if not include_deals:
            summary.pop("deals", None)  # the per-deal list; stage counts stay
        return summary

    # -- Knowledge (read) ----------------------------------------------------

    async def list_articles(
        name: Annotated[str | None, Field(description="Title (substring).")] = None,
        parent: Annotated[str | None, Field(description="Parent article title.")] = None,
        category: Literal["workspace", "private", "shared"] | None = None,
        search: Annotated[str | None, Field(description="Text in the article body.")] = None,
        limit: Limit = 50,
        offset: Offset = 0,
    ) -> dict[str, Any]:
        """List knowledge articles. Read one with read_records (body as Markdown)."""
        odoo = await holder.get()
        domain: list[Any] = []
        _ilike(domain, "name", name)
        _ilike(domain, "parent_id.name", parent)
        _ilike(domain, "body", search)
        if category:
            domain.append(("category", "=", category))
        return await search_page(
            odoo,
            "knowledge.article",
            domain,
            list(_GeneratedKnowledgeAttrs._default_fields),
            limit,
            offset,
            "sequence, id",
        )

    # -- Documents (read) ----------------------------------------------------

    async def list_documents(
        folder: Annotated[
            int | str | None, Field(description="Folder id or exact folder name.")
        ] = None,
        search: Annotated[str | None, Field(description="Text in the file name.")] = None,
        limit: Limit = 50,
        offset: Offset = 0,
    ) -> dict[str, Any]:
        """List files in Odoo Documents."""
        odoo = await holder.get()
        domain: list[Any] = [("type", "=", "binary")]
        if folder is not None:
            domain.append(("folder_id", "=", await odoo.documents.resolve_folder(folder)))
        _ilike(domain, "name", search)
        return await search_page(
            odoo,
            "documents.document",
            domain,
            list(_GeneratedDocumentAttrs._default_fields),
            limit,
            offset,
            "create_date desc",
        )

    async def list_document_folders(limit: Limit = 100) -> list[dict[str, Any]]:
        """List Odoo Documents folders (with path and depth)."""
        odoo = await holder.get()
        rows: list[dict[str, Any]] = await odoo.documents.folders(
            limit=clamp_limit(limit), tree=True
        )
        return rows

    async def download_document(
        document_id: int,
        output_dir: Annotated[
            str | None, Field(description="Subfolder of the download folder.")
        ] = None,
    ) -> dict[str, Any]:
        """Download a file from Odoo Documents into the local download folder."""
        odoo = await holder.get()
        rows = await odoo.read(
            "documents.document", [document_id], ["name", "type", "mimetype", "datas"]
        )
        if not rows:
            raise ToolError(f"Document {document_id} not found")
        data = _decode_document_data(rows[0], document_id)
        filename = _safe_document_filename(rows[0].get("name"), document_id)
        if filename.startswith("."):
            filename = f"document_{document_id}{filename}"
        path = write_new_file(files.download_target(output_dir), filename, data)
        return {"path": str(path), "bytes": len(data), "mimetype": rows[0].get("mimetype")}

    # -- Activities & tags (read) --------------------------------------------

    async def list_activities(
        model: Annotated[
            str | None, Field(description="Related model, e.g. 'account.move', 'crm.lead'.")
        ] = None,
        record_id: Annotated[int | None, Field(description="Related record id.")] = None,
        assigned_to: Annotated[str | None, Field(description="User name (substring).")] = None,
        mine: Mine = False,
        activity_type: Annotated[str | None, Field(description="Type name, e.g. 'Call'.")] = None,
        overdue: Annotated[bool, Field(description="Only past their deadline.")] = False,
        due_before: Annotated[str | None, Field(description="Deadline before YYYY-MM-DD.")] = None,
        limit: Limit = 50,
        offset: Offset = 0,
    ) -> dict[str, Any]:
        """List scheduled activities (to-dos, calls, follow-ups), soonest first."""
        odoo = await holder.get()
        domain: list[Any] = []
        if model:
            domain.append(("res_model", "=", model))
        if record_id is not None:
            domain.append(("res_id", "=", record_id))
        _ilike(domain, "user_id.name", assigned_to)
        _ilike(domain, "activity_type_id.name", activity_type)
        if mine:
            domain.append(("user_id", "=", await odoo.get_uid()))
        if overdue:
            domain.append(("date_deadline", "<", date.today().isoformat()))  # noqa: DTZ011
        if due_before:
            domain.append(("date_deadline", "<", due_before))
        return await search_page(
            odoo,
            "mail.activity",
            domain,
            list(_GeneratedActivityAttrs._default_fields),
            limit,
            offset,
            "date_deadline, id",
        )

    async def list_tags(kind: TagKind) -> list[dict[str, Any]]:
        """List the tags for tasks, helpdesk tickets, or CRM leads."""
        odoo = await holder.get()
        return await odoo.search_read(
            _TAG_MODELS[kind][1], fields=["id", "name", "color"], order="name"
        )

    reads: list[tuple[Callable[..., Awaitable[Any]], str, str | None]] = [
        (list_tasks, "List tasks", "project.task"),
        (get_task_context, "Task context", "project.task"),
        (list_projects, "List projects", "project.project"),
        (list_project_stages, "List task stages", "project.task.type"),
        (list_milestones, "List milestones", "project.milestone"),
        (list_milestone_tasks, "List milestone tasks", "project.milestone"),
        (list_tickets, "List helpdesk tickets", "helpdesk.ticket"),
        (list_leads, "List leads / opportunities", "crm.lead"),
        (list_crm_stages, "List CRM stages", "crm.stage"),
        (crm_pipeline, "CRM pipeline", "crm.lead"),
        (list_articles, "List knowledge articles", "knowledge.article"),
        (list_documents, "List documents", "documents.document"),
        (list_document_folders, "List document folders", "documents.document"),
        (download_document, "Download document", "documents.document"),
        (list_activities, "List activities", None),
        (list_tags, "List tags", None),
    ]
    for tool, title, requires in reads:
        register(tool, title=title, read_only=True, requires=requires)

    if allow_write:
        _register_domain_write_tools(register, holder, files, allow_delete, record_url)


def _register_domain_write_tools(  # noqa: PLR0915
    register: Register,
    holder: ClientHolder,
    files: FilePolicy,
    allow_delete: bool,
    record_url: RecordUrl,
) -> None:
    def guard(*payloads: Any) -> None:
        guard_delete(allow_delete, *payloads)

    async def created(odoo: AsyncOdooClient, model: str, record_id: int) -> dict[str, Any]:
        return {"id": record_id, "url": await record_url(odoo, model, record_id)}

    # -- Projects & tasks (write) --------------------------------------------

    async def create_task(
        name: str,
        project: Annotated[int | str, Field(description="Project id or exact name.")],
        description: Annotated[str | None, Field(description="Markdown text.")] = None,
        assignee_ids: Annotated[list[int] | None, Field(description="res.users ids.")] = None,
        tag_ids: list[int] | None = None,
        stage_id: Annotated[int | None, Field(description="See list_project_stages.")] = None,
        parent_id: Annotated[int | None, Field(description="Parent task (subtask).")] = None,
        depends_on_ids: Annotated[
            list[int] | None, Field(description="Tasks that block this one.")
        ] = None,
        milestone_id: int | None = None,
        deadline: Annotated[str | None, Field(description="YYYY-MM-DD.")] = None,
        priority: Annotated[Literal["0", "1"] | None, Field(description="'1' = starred.")] = None,
        extra_values: Extra = None,
    ) -> dict[str, Any]:
        """Create a project task (or subtask) and return its id and URL."""
        guard(extra_values)
        check_extra(
            extra_values,
            {
                "name": "name",
                "project_id": "project",
                "description": "description",
                "user_ids": "assignee_ids",
                "tag_ids": "tag_ids",
                "parent_id": "parent_id",
                "stage_id": "stage_id",
                "depend_on_ids": "depends_on_ids",
                "milestone_id": "milestone_id",
                "date_deadline": "deadline",
                "priority": "priority",
            },
        )
        odoo = await holder.get()
        project_id = await odoo.projects.resolve_project_id(project)
        optional = {"milestone_id": milestone_id, "date_deadline": deadline, "priority": priority}
        values = {k: v for k, v in optional.items() if v is not None} | (extra_values or {})
        task_id = await odoo.tasks.create(
            name,
            project_id,
            description,
            assignee_ids,
            tag_ids,
            parent_id,
            stage_id=stage_id,
            depend_on_ids=depends_on_ids,
            **values,
        )
        return await created(odoo, "project.task", task_id)

    async def set_task_milestone(task_id: int, milestone_id: int) -> dict[str, Any]:
        """Assign a task to a milestone of the same project."""
        odoo = await holder.get()
        await odoo.tasks.set_milestone(task_id, milestone_id)
        return {"task_id": task_id, "milestone_id": milestone_id}

    async def set_task_dependencies(
        task_id: int,
        add_ids: Annotated[
            list[int] | None, Field(description="Tasks that must be done first.")
        ] = None,
        clear: Annotated[bool, Field(description="Remove all dependencies first.")] = False,
    ) -> dict[str, Any]:
        """Add or clear the tasks that block a task ("blocked by")."""
        if not add_ids and not clear:
            raise ToolError("Give add_ids, clear=true, or both")
        odoo = await holder.get()
        if clear:
            await odoo.tasks.clear_dependencies(task_id)
        if add_ids:
            await odoo.tasks.add_dependencies(task_id, add_ids)
        rows = await odoo.read("project.task", [task_id], ["depend_on_ids"])
        return {"task_id": task_id, "depend_on_ids": rows[0].get("depend_on_ids") if rows else []}

    async def schedule_task(
        task_id: int,
        start: Annotated[str, Field(description="Planned start, UTC 'YYYY-MM-DD HH:MM:SS'.")],
        end: Annotated[str, Field(description="Deadline 'YYYY-MM-DD'.")],
    ) -> dict[str, Any]:
        """Set a task's planned start and deadline (Gantt; Project Enterprise)."""
        odoo = await holder.get()
        await odoo.tasks.schedule(task_id, start, end)
        return {"task_id": task_id, "start": start, "end": end}

    async def create_milestone(
        project: Annotated[int | str, Field(description="Project id or exact name.")],
        name: str,
        deadline: Annotated[str, Field(description="YYYY-MM-DD.")],
    ) -> dict[str, Any]:
        """Create a project milestone."""
        odoo = await holder.get()
        milestone_id = await odoo.projects.create_milestone(project, name, deadline)
        return {"id": milestone_id}

    async def reach_milestone(milestone_id: int) -> dict[str, Any]:
        """Mark a milestone as reached."""
        odoo = await holder.get()
        await odoo.projects.reach_milestone(milestone_id)
        return {"id": milestone_id, "is_reached": True}

    # -- Helpdesk, CRM, knowledge (write) ------------------------------------

    async def create_ticket(
        name: Annotated[str, Field(description="Ticket subject.")],
        description: Annotated[str | None, Field(description="Markdown text.")] = None,
        partner_id: Annotated[int | None, Field(description="Customer (res.partner).")] = None,
        team_id: int | None = None,
        assignee_id: Annotated[int | None, Field(description="res.users id.")] = None,
        tag_ids: list[int] | None = None,
        priority: Annotated[
            Literal["0", "1", "2", "3"] | None, Field(description="0 low ... 3 urgent.")
        ] = None,
        extra_values: Extra = None,
    ) -> dict[str, Any]:
        """Create a helpdesk ticket."""
        guard(extra_values)
        check_extra(
            extra_values,
            {
                "name": "name",
                "description": "description",
                "partner_id": "partner_id",
                "tag_ids": "tag_ids",
                "team_id": "team_id",
                "user_id": "assignee_id",
                "priority": "priority",
            },
        )
        odoo = await holder.get()
        optional = {"user_id": assignee_id, "priority": priority}
        values = {k: v for k, v in optional.items() if v is not None} | (extra_values or {})
        ticket_id = await odoo.helpdesk.create(
            name,
            description=Markdown(description) if description else None,
            partner_id=partner_id,
            tag_ids=tag_ids,
            team_id=team_id,
            **values,
        )
        return await created(odoo, "helpdesk.ticket", ticket_id)

    async def create_lead(
        name: str,
        lead_type: Literal["lead", "opportunity"] = "opportunity",
        partner_id: Annotated[int | None, Field(description="Customer (res.partner).")] = None,
        expected_revenue: float | None = None,
        probability: Annotated[float | None, Field(ge=0, le=100)] = None,
        stage_id: Annotated[int | None, Field(description="See list_crm_stages.")] = None,
        salesperson_id: Annotated[int | None, Field(description="res.users id.")] = None,
        team_id: int | None = None,
        tag_ids: list[int] | None = None,
        email: str | None = None,
        phone: str | None = None,
        contact_name: str | None = None,
        description: Annotated[str | None, Field(description="Internal notes (Markdown).")] = None,
        deadline: Annotated[str | None, Field(description="Expected closing, YYYY-MM-DD.")] = None,
        extra_values: Extra = None,
    ) -> dict[str, Any]:
        """Create a CRM lead or opportunity."""
        guard(extra_values)
        check_extra(
            extra_values,
            {
                "name": "name",
                "type": "lead_type",
                "partner_id": "partner_id",
                "expected_revenue": "expected_revenue",
                "stage_id": "stage_id",
                "user_id": "salesperson_id",
                "team_id": "team_id",
                "tag_ids": "tag_ids",
                "probability": "probability",
                "email_from": "email",
                "phone": "phone",
                "contact_name": "contact_name",
                "description": "description",
                "date_deadline": "deadline",
            },
        )
        odoo = await holder.get()
        optional: dict[str, Any] = {
            "probability": probability,
            "email_from": email,
            "phone": phone,
            "contact_name": contact_name,
            "description": Markdown(description) if description else None,
            "date_deadline": deadline,
        }
        values = {k: v for k, v in optional.items() if v is not None} | (extra_values or {})
        lead_id = await odoo.crm.create(
            name,
            partner_id=partner_id,
            expected_revenue=expected_revenue,
            stage_id=stage_id,
            user_id=salesperson_id,
            team_id=team_id,
            tag_ids=tag_ids,
            lead_type=lead_type,
            **values,
        )
        return await created(odoo, "crm.lead", lead_id)

    async def create_article(
        name: Annotated[str, Field(description="Article title.")],
        body: Annotated[str | None, Field(description="Markdown text.")] = None,
        parent_id: Annotated[int | None, Field(description="Parent article.")] = None,
        private: Annotated[
            bool,
            Field(
                description="Only you can see it. Default: a workspace article that all "
                "internal users can read and edit. Under a private parent it is always "
                "private; a private article cannot go under a workspace parent."
            ),
        ] = False,
        icon: Annotated[str | None, Field(description="Emoji, e.g. '📘'.")] = None,
    ) -> dict[str, Any]:
        """Create a knowledge article (workspace or private)."""
        odoo = await holder.get()
        # Odoo computes `category` from permissions, so writing it has no effect.
        # article_create sets the permissions and members like the Knowledge UI does.
        kwargs: dict[str, Any] = {"title": name, "is_private": private}
        if parent_id is not None:
            kwargs["parent_id"] = parent_id
        result = await odoo.execute("knowledge.article", "article_create", **kwargs)
        article_id = int(result[0] if isinstance(result, list) else result)
        values: dict[str, Any] = {}
        if body:
            values["body"] = Markdown(body)
        if icon:
            values["icon"] = icon
        if values:
            await odoo.write("knowledge.article", [article_id], values)
        rows = await odoo.read("knowledge.article", [article_id], ["category"])
        return {
            "id": article_id,
            "category": rows[0].get("category") if rows else None,
            "url": await odoo.knowledge.url(article_id),
        }

    # -- Documents, tags, activities (write) ---------------------------------

    async def upload_document(
        file_path: Annotated[str, Field(description="Local file in an allowed folder.")],
        folder: Annotated[int | str, Field(description="Folder id or exact folder name.")],
        name: Annotated[str | None, Field(description="Name in Odoo (default: file name).")] = None,
        tags: Annotated[
            list[int | str] | None, Field(description="Document tag ids or exact names.")
        ] = None,
        owner: Annotated[
            int | str | None, Field(description="Owner user id, login, or exact name.")
        ] = None,
    ) -> dict[str, Any]:
        """Upload a local file to Odoo Documents."""
        path = files.upload_source(file_path)
        odoo = await holder.get()
        document_id = await odoo.documents.upload(
            path, folder=folder, tags=tags, owner=owner, name=name
        )
        return {"id": document_id, "name": name or path.name}

    async def add_tag(kind: TagKind, record_id: int, tag_id: int) -> dict[str, Any]:
        """Add a tag to a task, helpdesk ticket, or CRM lead (keeps existing tags)."""
        odoo = await holder.get()
        model = _TAG_MODELS[kind][0]
        rows = await odoo.read(model, [record_id], ["tag_ids"])
        if not rows:
            raise ToolError(f"{model} {record_id} not found")
        await odoo.write(model, [record_id], {"tag_ids": [(4, tag_id, 0)]})
        return {"record_id": record_id, "tag_id": tag_id}

    async def create_tag(
        kind: TagKind,
        name: str,
        color: Annotated[int | None, Field(ge=0, le=11, description="Odoo color index.")] = None,
    ) -> dict[str, Any]:
        """Create a tag for tasks, helpdesk tickets, or CRM leads."""
        odoo = await holder.get()
        values: dict[str, Any] = {"name": name}
        if color is not None:
            values["color"] = color
        return {"id": await odoo.create(_TAG_MODELS[kind][1], values)}

    async def schedule_activity(
        model: Annotated[str, Field(description="Record model, e.g. 'account.move'.")],
        record_id: int,
        summary: str,
        deadline: Annotated[str, Field(description="YYYY-MM-DD.")],
        note: Annotated[str | None, Field(description="Markdown text.")] = None,
        assignee_id: Annotated[
            int | None, Field(description="res.users id; default: the connected user.")
        ] = None,
        activity_type: Annotated[
            str | None, Field(description="Type name, e.g. 'Call' or 'Email'; default To-Do.")
        ] = None,
    ) -> dict[str, Any]:
        """Schedule an activity (to-do, call, follow-up) on any record."""
        odoo = await holder.get()
        model_rows = await odoo.search_read(
            "ir.model", domain=[("model", "=", model)], fields=["id"], limit=1
        )
        if not model_rows:
            raise ToolError(f"Unknown model {model}")
        type_id = await _activity_type_id(odoo, activity_type, model)
        values: dict[str, Any] = {
            "res_model_id": model_rows[0]["id"],
            "res_id": record_id,
            "summary": summary,
            "date_deadline": deadline,
            "user_id": assignee_id or await odoo.get_uid(),
            "activity_type_id": type_id,
        }
        if note:
            values["note"] = Markdown(note)
        activity_id = await odoo.create("mail.activity", values)
        return {"id": activity_id}

    writes: list[tuple[Callable[..., Awaitable[Any]], str, bool, bool, str | None]] = [
        # (tool, title, destructive, idempotent, required model)
        (create_task, "Create task", False, False, "project.task"),
        (set_task_milestone, "Set task milestone", True, True, "project.milestone"),
        (set_task_dependencies, "Set task dependencies", True, False, "project.task"),
        (schedule_task, "Schedule task", True, True, "project.task"),
        (create_milestone, "Create milestone", False, False, "project.milestone"),
        (reach_milestone, "Reach milestone", True, True, "project.milestone"),
        (create_ticket, "Create helpdesk ticket", False, False, "helpdesk.ticket"),
        (create_lead, "Create lead / opportunity", False, False, "crm.lead"),
        (create_article, "Create knowledge article", False, False, "knowledge.article"),
        (upload_document, "Upload document", False, False, "documents.document"),
        (add_tag, "Add tag", False, True, None),
        (create_tag, "Create tag", False, False, None),
        (schedule_activity, "Schedule activity", False, False, None),
    ]
    for tool, title, destructive, idempotent, requires in writes:
        register(
            tool,
            title=title,
            read_only=False,
            destructive=destructive,
            idempotent=idempotent,
            requires=requires,
        )


async def _activity_type_id(odoo: AsyncOdooClient, name: str | None, model: str) -> int:
    """Resolve an activity type usable on *model* (generic or specific to it)."""
    if name:
        usable: list[Any] = ["|", ("res_model", "=", False), ("res_model", "=", model)]
        for operator in ("=ilike", "ilike"):  # exact (case-insensitive) first
            rows = await odoo.search_read(
                "mail.activity.type",
                domain=[*usable, ("name", operator, name)],
                fields=["id", "name"],
                limit=5,
            )
            if len(rows) == 1:
                return int(rows[0]["id"])
            if len(rows) > 1:
                names = ", ".join(f"{r['name']} (id {r['id']})" for r in rows)
                raise ToolError(f"Activity type '{name}' is ambiguous: {names}")
        raise ToolError(f"No activity type named '{name}' for {model}")
    reference = await odoo.execute(
        "ir.model.data",
        "check_object_reference",
        module="mail",
        xml_id=_ACTIVITY_TODO_XMLID,
        raise_on_access_error=True,
    )
    if isinstance(reference, list | tuple) and len(reference) == 2:
        return int(reference[1])
    raise ToolError("Could not find the default To-Do activity type")


__all__ = ["register_domain_tools"]
