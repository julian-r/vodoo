"""CRM lead/opportunity operations for Vodoo."""

from __future__ import annotations

import datetime as _dt
from typing import Any

from vodoo.base import (
    _get_console,
    _is_simple_output,
    is_structured_output,
    structured_print,
)
from vodoo.generated.crm import STAGE_FIELDS, GeneratedCRMNamespace

_PIPELINE_FIELDS = [
    "id",
    "name",
    "stage_id",
    "expected_revenue",
    "probability",
    "create_date",
    "partner_id",
    "user_id",
    "team_id",
]

# Default staleness thresholds (days) by stage sequence position.
# First stage gets a higher threshold; later stages get stricter ones.
DEFAULT_STALE_THRESHOLDS: dict[str, int] = {
    "_first": 30,
    "_middle": 45,
    "_late": 60,
}


class CRMNamespace(GeneratedCRMNamespace):
    """CRM leads/opportunities namespace."""

    def create(
        self,
        name: str,
        *,
        partner_id: int | None = None,
        expected_revenue: float | None = None,
        stage_id: int | None = None,
        user_id: int | None = None,
        team_id: int | None = None,
        tag_ids: list[int] | None = None,
        lead_type: str = "opportunity",
        **extra_fields: Any,
    ) -> int:
        """Create a CRM lead or opportunity.

        Args:
            name: Lead/opportunity name.
            partner_id: Customer partner ID.
            expected_revenue: Expected revenue amount.
            stage_id: Pipeline stage ID.
            user_id: Salesperson user ID.
            team_id: Sales team ID.
            tag_ids: List of tag IDs to apply.
            lead_type: ``'lead'`` or ``'opportunity'`` (default).
            **extra_fields: Additional fields to set.

        Returns:
            ID of created record.

        """
        values: dict[str, Any] = {**extra_fields, "name": name, "type": lead_type}
        if partner_id is not None:
            values["partner_id"] = partner_id
        if expected_revenue is not None:
            values["expected_revenue"] = expected_revenue
        if stage_id is not None:
            values["stage_id"] = stage_id
        if user_id is not None:
            values["user_id"] = user_id
        if team_id is not None:
            values["team_id"] = team_id
        if tag_ids is not None:
            values["tag_ids"] = [(6, 0, tag_ids)]
        return self._client.create(self._model, values)

    def stages(self, *, team_id: int | None = None) -> list[dict[str, Any]]:
        """List CRM pipeline stages.

        Args:
            team_id: Filter stages by sales team (None = all stages).

        Returns:
            List of stage dictionaries.

        """
        domain: list[Any] = []
        if team_id is not None:
            domain.append(("team_id", "=", team_id))
        return self._client.search_read(
            "crm.stage",
            domain=domain,
            fields=STAGE_FIELDS,
            order="sequence",
        )

    def pipeline(
        self,
        *,
        team: str | None = None,
        user: str | None = None,
    ) -> dict[str, Any]:
        """Fetch pipeline data and return aggregated summary.

        Returns a dict with keys ``team``, ``date``, ``stages`` (list of
        per-stage aggregates), ``totals``, and ``deals`` (raw deal list).
        """
        domain: list[Any] = [("type", "=", "opportunity")]
        if team:
            domain.append(("team_id.name", "ilike", team))
        if user:
            domain.append(("user_id.name", "ilike", user))

        deals = self._client.search_read(
            self._model,
            domain=domain,
            fields=_PIPELINE_FIELDS,
            limit=0,  # all
        )

        stages = self._client.search_read(
            "crm.stage",
            domain=[],
            fields=STAGE_FIELDS,
            order="sequence",
        )

        return build_pipeline_summary(deals, stages, team=team)


# ---------------------------------------------------------------------------
# Pure aggregation (no client needed)
# ---------------------------------------------------------------------------

_TODAY = None  # allow override in tests


def _today() -> _dt.date:
    return _TODAY or _dt.datetime.now(_dt.UTC).date()


def _age_days(create_date: str | None) -> int:
    if not create_date:
        return 0
    try:
        created = _dt.datetime.fromisoformat(create_date).date()
    except (ValueError, TypeError):
        return 0
    return (_today() - created).days


def build_pipeline_summary(
    deals: list[dict[str, Any]],
    stages: list[dict[str, Any]],
    *,
    team: str | None = None,
) -> dict[str, Any]:
    """Build a pipeline summary from raw deals and stages."""
    stage_order = {s["id"]: i for i, s in enumerate(stages)}
    stage_names = {s["id"]: s["name"] for s in stages}

    # Group deals by stage
    by_stage: dict[int, list[dict[str, Any]]] = {}
    for deal in deals:
        sid = deal.get("stage_id")
        if isinstance(sid, list):
            sid = sid[0]
        if sid is None:
            continue
        by_stage.setdefault(sid, []).append(deal)

    stage_summaries: list[dict[str, Any]] = []
    total_deals = 0
    total_revenue = 0.0
    total_weighted = 0.0

    for stage in stages:
        sid = stage["id"]
        stage_deals = by_stage.get(sid, [])
        count = len(stage_deals)
        if count == 0:
            continue

        revenue = sum(d.get("expected_revenue") or 0 for d in stage_deals)
        weighted = sum(
            (d.get("expected_revenue") or 0) * (d.get("probability") or 0) / 100
            for d in stage_deals
        )
        ages = [_age_days(d.get("create_date")) for d in stage_deals]
        avg_age = round(sum(ages) / count) if count else 0
        oldest = max(ages) if ages else 0

        stage_summaries.append(
            {
                "stage_id": sid,
                "name": stage_names.get(sid, f"Stage {sid}"),
                "deals": count,
                "revenue": revenue,
                "weighted": round(weighted, 2),
                "avg_age_days": avg_age,
                "oldest_days": oldest,
            }
        )

        total_deals += count
        total_revenue += revenue
        total_weighted += weighted

    # Attach enriched deal data (for --deals flag)
    enriched_deals: list[dict[str, Any]] = []
    for deal in deals:
        sid = deal.get("stage_id")
        if isinstance(sid, list):
            sid = sid[0]
        partner = deal.get("partner_id")
        partner_name = partner[1] if isinstance(partner, list) else None
        user = deal.get("user_id")
        user_name = user[1] if isinstance(user, list) else None
        enriched_deals.append(
            {
                "id": deal["id"],
                "name": deal.get("name", ""),
                "stage_id": sid,
                "stage_name": stage_names.get(sid, ""),
                "expected_revenue": deal.get("expected_revenue") or 0,
                "probability": deal.get("probability") or 0,
                "age_days": _age_days(deal.get("create_date")),
                "partner": partner_name,
                "user": user_name,
                "stage_order": stage_order.get(sid, 999),
            }
        )
    enriched_deals.sort(key=lambda d: (d["stage_order"], -d["expected_revenue"]))

    return {
        "team": team or "All Teams",
        "date": str(_today()),
        "stages": stage_summaries,
        "totals": {
            "deals": total_deals,
            "revenue": total_revenue,
            "weighted": round(total_weighted, 2),
        },
        "deals": enriched_deals,
    }


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


def compute_health_flags(
    summary: dict[str, Any],
    *,
    stale_thresholds: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Compute health flags for deals in a pipeline summary.

    Returns a sorted list of ``{severity, rule, deal_id, deal_name, detail}`` dicts.
    """
    thresholds = stale_thresholds or DEFAULT_STALE_THRESHOLDS
    first_threshold = thresholds.get("_first", 30)
    middle_threshold = thresholds.get("_middle", 45)
    late_threshold = thresholds.get("_late", 60)

    stages = summary.get("stages", [])
    stage_positions: dict[int, int] = {}
    for i, s in enumerate(stages):
        stage_positions[s["stage_id"]] = i
    num_stages = len(stages)

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    flags: list[dict[str, Any]] = []

    for deal in summary.get("deals", []):
        did = deal["id"]
        dname = deal["name"]
        prob = deal.get("probability", 0)
        rev = deal.get("expected_revenue", 0)
        age = deal.get("age_days", 0)
        partner = deal.get("partner")
        user = deal.get("user")
        sid = deal.get("stage_id")
        pos = stage_positions.get(sid, 0)

        # Critical: 0% probability on open deal
        if prob == 0:
            flags.append(
                {
                    "severity": "critical",
                    "rule": "Zero probability",
                    "deal_id": did,
                    "deal_name": dname,
                    "detail": "Open deal with 0% probability",
                }
            )

        # Warning: missing revenue past first stage
        if rev == 0 and pos > 0:
            flags.append(
                {
                    "severity": "warning",
                    "rule": "Missing revenue",
                    "deal_id": did,
                    "deal_name": dname,
                    "detail": f"No expected revenue in stage '{deal.get('stage_name', '')}'",
                }
            )

        # Staleness by position
        if pos == 0 and age > first_threshold:
            flags.append(
                {
                    "severity": "info",
                    "rule": "Stale deal",
                    "deal_id": did,
                    "deal_name": dname,
                    "detail": f"{age}d in first stage (threshold: {first_threshold}d)",
                }
            )
        elif 0 < pos < num_stages // 2 and age > middle_threshold:
            flags.append(
                {
                    "severity": "warning",
                    "rule": "Stale deal",
                    "deal_id": did,
                    "deal_name": dname,
                    "detail": f"{age}d in '{deal.get('stage_name', '')}'"
                    f" (threshold: {middle_threshold}d)",
                }
            )
        elif pos >= num_stages // 2 and age > late_threshold:
            flags.append(
                {
                    "severity": "warning",
                    "rule": "Stale deal",
                    "deal_id": did,
                    "deal_name": dname,
                    "detail": f"{age}d in '{deal.get('stage_name', '')}'"
                    f" (threshold: {late_threshold}d)",
                }
            )

        # Warning: no partner
        if not partner:
            flags.append(
                {
                    "severity": "warning",
                    "rule": "No partner",
                    "deal_id": did,
                    "deal_name": dname,
                    "detail": "No partner linked",
                }
            )

        # Warning: no salesperson
        if not user:
            flags.append(
                {
                    "severity": "warning",
                    "rule": "No salesperson",
                    "deal_id": did,
                    "deal_name": dname,
                    "detail": "No salesperson assigned",
                }
            )

    flags.sort(key=lambda f: (severity_order.get(f["severity"], 9), f["deal_name"]))
    return flags


# ---------------------------------------------------------------------------
# Display functions
# ---------------------------------------------------------------------------


def display_crm_stages(stages: list[dict[str, Any]]) -> None:
    """Display CRM pipeline stages in a table, TSV, or structured format."""
    if is_structured_output():
        structured_print(stages)
        return

    if _is_simple_output():
        print("id\tname\tsequence\tis_won\tfold")
        for s in stages:
            won = "true" if s.get("is_won") else "false"
            fold = "true" if s.get("fold") else "false"
            print(f"{s['id']}\t{s['name']}\t{s.get('sequence', '')}\t{won}\t{fold}")
    else:
        from rich.table import Table

        console = _get_console()
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Name", style="green")
        table.add_column("Sequence", justify="right")
        table.add_column("Won", justify="center")
        table.add_column("Folded", justify="center")

        for s in stages:
            table.add_row(
                str(s["id"]),
                s["name"],
                str(s.get("sequence", "")),
                "✓" if s.get("is_won") else "",
                "✓" if s.get("fold") else "",
            )

        console.print(table)


def _fmt_currency(value: float) -> str:
    """Format a number as currency-like string."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:,.1f}M"
    if value >= 1_000:
        return f"{value:,.0f}"
    return f"{value:,.0f}"


def _fmt_days(days: int) -> str:
    return f"{days}d"


def display_pipeline(
    summary: dict[str, Any],
    *,
    show_deals: bool = False,
    show_health: bool = False,
    health_flags: list[dict[str, Any]] | None = None,
) -> None:
    """Display pipeline summary in table, TSV, or structured format."""
    if is_structured_output():
        output: dict[str, Any] = {
            "team": summary["team"],
            "date": summary["date"],
            "stages": summary["stages"],
            "totals": summary["totals"],
        }
        if show_deals:
            output["deals"] = summary["deals"]
        if show_health and health_flags:
            output["health"] = health_flags
        structured_print(output)
        return

    if _is_simple_output():
        _display_pipeline_simple(summary, show_deals, show_health, health_flags)
        return

    _display_pipeline_rich(summary, show_deals, show_health, health_flags)


def _display_pipeline_simple(
    summary: dict[str, Any],
    show_deals: bool,
    show_health: bool,
    health_flags: list[dict[str, Any]] | None,
) -> None:
    print(f"# Pipeline: {summary['team']}  {summary['date']}")
    print("stage\tdeals\trevenue\tweighted\tavg_age\toldest")
    for s in summary["stages"]:
        print(
            f"{s['name']}\t{s['deals']}\t{s['revenue']}\t{s['weighted']}"
            f"\t{s['avg_age_days']}\t{s['oldest_days']}"
        )
    t = summary["totals"]
    print(f"TOTAL\t{t['deals']}\t{t['revenue']}\t{t['weighted']}\t\t")

    if show_deals:
        print("\n# Deals")
        print("id\tname\tstage\trevenue\tprobability\tage\tuser")
        for d in summary["deals"]:
            print(
                f"{d['id']}\t{d['name']}\t{d['stage_name']}"
                f"\t{d['expected_revenue']}\t{d['probability']}"
                f"\t{d['age_days']}\t{d.get('user', '')}"
            )

    if show_health and health_flags:
        print("\n# Health")
        print("severity\trule\tdeal_id\tdeal_name\tdetail")
        for f in health_flags:
            print(f"{f['severity']}\t{f['rule']}\t{f['deal_id']}\t{f['deal_name']}\t{f['detail']}")


def _display_pipeline_rich(
    summary: dict[str, Any],
    show_deals: bool,
    show_health: bool,
    health_flags: list[dict[str, Any]] | None,
) -> None:
    from rich.table import Table

    console = _get_console()

    console.print(f"\n[bold]Pipeline: {summary['team']}[/bold]  [dim]{summary['date']}[/dim]\n")

    table = Table(show_header=True, header_style="bold magenta", show_footer=True)
    table.add_column("Stage", style="green", footer_style="bold")
    table.add_column("Deals", justify="right", footer_style="bold")
    table.add_column("Revenue", justify="right", footer_style="bold")
    table.add_column("Weighted", justify="right", footer_style="bold")
    table.add_column("Avg Age", justify="right")
    table.add_column("Oldest", justify="right")

    for s in summary["stages"]:
        table.add_row(
            s["name"],
            str(s["deals"]),
            _fmt_currency(s["revenue"]),
            _fmt_currency(s["weighted"]),
            _fmt_days(s["avg_age_days"]),
            _fmt_days(s["oldest_days"]),
        )

    t = summary["totals"]
    table.columns[0].footer = "Total"
    table.columns[1].footer = str(t["deals"])
    table.columns[2].footer = _fmt_currency(t["revenue"])
    table.columns[3].footer = _fmt_currency(t["weighted"])

    console.print(table)

    # --deals: individual deals under each stage
    if show_deals:
        console.print()
        stage_deals: dict[int, list[dict[str, Any]]] = {}
        for d in summary["deals"]:
            stage_deals.setdefault(d["stage_id"], []).append(d)

        for s in summary["stages"]:
            sid = s["stage_id"]
            deals = stage_deals.get(sid, [])
            console.print(
                f"\n[bold]{s['name']}[/bold]"
                f" [dim]({s['deals']} deals, {_fmt_currency(s['revenue'])})[/dim]"
            )
            for d in deals:
                flags = ""
                if d["expected_revenue"] == 0 and s != summary["stages"][0]:
                    flags += " [yellow]NO-REV[/yellow]"
                if d["probability"] == 0:
                    flags += " [red]0-PROB[/red]"
                user = d.get("user") or "[dim]unassigned[/dim]"
                console.print(
                    f"  [cyan]#{d['id']}[/cyan]  {d['name']:<30}"
                    f"  {_fmt_currency(d['expected_revenue']):>10}"
                    f"  {d['probability']:>3.0f}%"
                    f"  {_fmt_days(d['age_days']):>5}"
                    f"  {user}{flags}"
                )

    # --health: flagged issues
    if show_health and health_flags:
        console.print("\n[bold]Health Flags[/bold]\n")
        htable = Table(show_header=True, header_style="bold")
        htable.add_column("Severity")
        htable.add_column("Rule")
        htable.add_column("Deal")
        htable.add_column("Detail")

        severity_styles = {
            "critical": "bold red",
            "warning": "yellow",
            "info": "dim",
        }
        for f in health_flags:
            style = severity_styles.get(f["severity"], "")
            htable.add_row(
                f"[{style}]{f['severity'].upper()}[/{style}]",
                f["rule"],
                f"#{f['deal_id']} {f['deal_name']}",
                f["detail"],
            )

        console.print(htable)
    elif show_health:
        console.print("\n[green]No health issues found.[/green]")
