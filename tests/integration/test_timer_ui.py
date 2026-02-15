"""Playwright UI tests: cross-validate timer state between vodoo API and Odoo web UI.

Tests start/stop timers via the API and verify the Odoo web UI reflects the correct
state, and vice versa.  Requires enterprise edition (timesheet_grid) and a running
Odoo instance with Playwright/Chromium installed.

Run with:
    VODOO_TEST_ENV=tests/integration/.env.test.19ee \
        uv run pytest tests/integration/test_timer_ui.py -v --headed
"""

from __future__ import annotations

import contextlib
import os
from typing import Any

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import Page, expect

from vodoo.client import OdooClient
from vodoo.config import OdooConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

START_BTN = 'button[name="action_timer_start"]'
STOP_BTN = 'button[name="action_timer_stop"]'
WIZARD_DIALOG = ".modal-dialog"
WIZARD_CONFIRM = '.modal-footer button[name="action_save_timesheet"]'


def _odoo_login(page: Page, config: OdooConfig) -> None:
    """Log into the Odoo web client.

    Uses 'admin' as the web password because the test env stores an API key
    in ODOO_PASSWORD, not the interactive login password.
    """
    web_password = os.environ.get("ODOO_WEB_PASSWORD", "admin")
    page.goto(
        f"{config.url}/web/login?db={config.database}",
        timeout=15_000,
    )
    page.fill('input[name="login"]', config.username)
    page.fill('input[name="password"]', web_password)
    page.click('button[type="submit"]')
    page.wait_for_url("**/odoo**", timeout=15_000)


def _open_record_form(page: Page, config: OdooConfig, model: str, record_id: int) -> None:
    """Navigate to a record's form view via hash URL (works across Odoo 17-19)."""
    page.goto(
        f"{config.url}/web#model={model}&view_type=form&id={record_id}",
        timeout=15_000,
    )
    page.wait_for_selector(".o_form_view", timeout=15_000)
    # Give the form time to render its statusbar buttons
    page.wait_for_timeout(1500)


def _click_stop_and_confirm(page: Page) -> None:
    """Click the Stop button and handle the stop-timer confirmation wizard."""
    page.locator(f"{STOP_BTN}:visible").click()
    # Odoo 19 shows a "Confirm Time Spent" wizard; earlier versions may not.
    dialog = page.locator(WIZARD_DIALOG)
    try:
        dialog.wait_for(timeout=5000)
    except Exception:
        # No wizard — stop happened directly
        return
    confirm = page.locator(WIZARD_CONFIRM)
    if confirm.count() > 0:
        confirm.click()
    page.wait_for_timeout(1500)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def odoo_page(page: Page, odoo_config: OdooConfig) -> Page:
    """Playwright page logged into the Odoo test instance."""
    _odoo_login(page, odoo_config)
    return page


# ---------------------------------------------------------------------------
# Task timer (project.task)
# ---------------------------------------------------------------------------


@pytest.mark.enterprise
class TestTimerTaskUI:
    """Cross-validate timer on project tasks between vodoo API and Odoo web UI."""

    @pytest.fixture(autouse=True)
    def _setup(self, client: OdooClient) -> Any:
        self.project_id = client.generic.create(
            "project.project",
            {"name": "Vodoo UI Timer Test Project", "allow_timesheets": True},
        )
        self.task_id = client.tasks.create("Vodoo UI Timer Test Task", project_id=self.project_id)
        yield
        with contextlib.suppress(Exception):
            client.timer.stop()
        for model, rid in [
            ("project.task", self.task_id),
            ("project.project", self.project_id),
        ]:
            with contextlib.suppress(Exception):
                client.generic.delete(model, rid)

    def test_api_start_shows_stop_in_ui(
        self, client: OdooClient, odoo_page: Page, odoo_config: OdooConfig
    ) -> None:
        """Start timer via API -> UI shows Stop button on the task form."""
        handle = client.timer.start_task(self.task_id)
        try:
            _open_record_form(odoo_page, odoo_config, "project.task", self.task_id)
            expect(odoo_page.locator(f"{STOP_BTN}:visible")).to_be_visible(timeout=10_000)
        finally:
            handle.stop()

    def test_handle_stop_shows_start_in_ui(
        self, client: OdooClient, odoo_page: Page, odoo_config: OdooConfig
    ) -> None:
        """Start via API, stop via handle -> UI shows Start button."""
        handle = client.timer.start_task(self.task_id)
        handle.stop()
        _open_record_form(odoo_page, odoo_config, "project.task", self.task_id)
        expect(odoo_page.locator(f"{START_BTN}:visible")).to_be_visible(timeout=10_000)

    def test_ui_start_detected_by_api(
        self, client: OdooClient, odoo_page: Page, odoo_config: OdooConfig
    ) -> None:
        """Click Start in UI -> API detects running timer on this task."""
        _open_record_form(odoo_page, odoo_config, "project.task", self.task_id)
        odoo_page.locator(f"{START_BTN}:visible").click()
        # Wait for the stop button to appear (timer is running in UI)
        expect(odoo_page.locator(f"{STOP_BTN}:visible")).to_be_visible(timeout=10_000)
        # API should see it
        active = client.timer.active()
        assert any(ts.source.kind == "task" and ts.source.id == self.task_id for ts in active), (
            f"Expected task {self.task_id} in active timers, got {active}"
        )

    def test_ui_stop_detected_by_api(
        self, client: OdooClient, odoo_page: Page, odoo_config: OdooConfig
    ) -> None:
        """Start via API, stop in UI -> API detects timer stopped."""
        client.timer.start_task(self.task_id)
        _open_record_form(odoo_page, odoo_config, "project.task", self.task_id)
        _click_stop_and_confirm(odoo_page)
        active = client.timer.active()
        assert not any(
            ts.source.kind == "task" and ts.source.id == self.task_id for ts in active
        ), f"Expected no active timer for task {self.task_id}, got {active}"


# ---------------------------------------------------------------------------
# Ticket timer (helpdesk.ticket)
# ---------------------------------------------------------------------------


@pytest.mark.enterprise
class TestTimerTicketUI:
    """Cross-validate timer on helpdesk tickets between vodoo API and Odoo web UI."""

    @pytest.fixture(autouse=True)
    def _setup(self, client: OdooClient) -> Any:
        # Ensure the default helpdesk team has timesheets enabled
        teams = client.search_read(
            "helpdesk.team", fields=["id", "use_helpdesk_timesheet"], limit=1
        )
        self.team_id = teams[0]["id"]
        if not teams[0]["use_helpdesk_timesheet"]:
            client.write("helpdesk.team", [self.team_id], {"use_helpdesk_timesheet": True})
            self._restored_timesheet = True
        else:
            self._restored_timesheet = False

        self.ticket_id = client.helpdesk.create("Vodoo UI Timer Test Ticket", team_id=self.team_id)
        yield
        with contextlib.suppress(Exception):
            client.timer.stop()
        with contextlib.suppress(Exception):
            client.generic.delete("helpdesk.ticket", self.ticket_id)
        if self._restored_timesheet:
            with contextlib.suppress(Exception):
                client.write("helpdesk.team", [self.team_id], {"use_helpdesk_timesheet": False})

    def test_api_start_shows_stop_in_ui(
        self, client: OdooClient, odoo_page: Page, odoo_config: OdooConfig
    ) -> None:
        """Start timer via API -> UI shows Stop button on the ticket form."""
        handle = client.timer.start_ticket(self.ticket_id)
        try:
            _open_record_form(odoo_page, odoo_config, "helpdesk.ticket", self.ticket_id)
            expect(odoo_page.locator(f"{STOP_BTN}:visible")).to_be_visible(timeout=10_000)
        finally:
            handle.stop()

    def test_handle_stop_shows_start_in_ui(
        self, client: OdooClient, odoo_page: Page, odoo_config: OdooConfig
    ) -> None:
        """Start via API, stop via handle -> UI shows Start button."""
        handle = client.timer.start_ticket(self.ticket_id)
        handle.stop()
        _open_record_form(odoo_page, odoo_config, "helpdesk.ticket", self.ticket_id)
        expect(odoo_page.locator(f"{START_BTN}:visible")).to_be_visible(timeout=10_000)

    def test_ui_start_detected_by_api(
        self, client: OdooClient, odoo_page: Page, odoo_config: OdooConfig
    ) -> None:
        """Click Start in UI -> API detects running timer on this ticket."""
        _open_record_form(odoo_page, odoo_config, "helpdesk.ticket", self.ticket_id)
        odoo_page.locator(f"{START_BTN}:visible").click()
        expect(odoo_page.locator(f"{STOP_BTN}:visible")).to_be_visible(timeout=10_000)
        active = client.timer.active()
        assert any(
            ts.source.kind == "ticket" and ts.source.id == self.ticket_id for ts in active
        ), f"Expected ticket {self.ticket_id} in active timers, got {active}"

    def test_ui_stop_detected_by_api(
        self, client: OdooClient, odoo_page: Page, odoo_config: OdooConfig
    ) -> None:
        """Start via API, stop in UI -> API detects timer stopped."""
        client.timer.start_ticket(self.ticket_id)
        _open_record_form(odoo_page, odoo_config, "helpdesk.ticket", self.ticket_id)
        _click_stop_and_confirm(odoo_page)
        active = client.timer.active()
        assert not any(
            ts.source.kind == "ticket" and ts.source.id == self.ticket_id for ts in active
        ), f"Expected no active timer for ticket {self.ticket_id}, got {active}"
