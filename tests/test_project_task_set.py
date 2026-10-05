"""Tests for ``vodoo project-task set`` output formatting."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import click
import pytest
from typer.testing import CliRunner

import vodoo.main as main_module
from vodoo.base import configure_output
from vodoo.main import app


class _FakeTasks:
    def __init__(self) -> None:
        self.updates: list[tuple[int, dict[str, Any]]] = []

    def set(self, task_id: int, values: dict[str, Any]) -> bool:
        self.updates.append((task_id, values))
        return True


class _FakeClient:
    def __init__(self) -> None:
        self.tasks = _FakeTasks()

    def fields_get(self, model: str) -> dict[str, dict[str, str]]:
        assert model == "project.task"
        return {
            "description": {"type": "html"},
            "name": {"type": "char"},
        }


@pytest.fixture(autouse=True)
def _reset_output() -> Iterator[None]:
    main_module._console_config.update(simple=False, json=False, toon=False)
    configure_output(simple=False, json_mode=False, toon_mode=False)
    try:
        yield
    finally:
        main_module._console_config.update(simple=False, json=False, toon=False)
        configure_output(simple=False, json_mode=False, toon_mode=False)


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient()
    monkeypatch.setattr(main_module, "get_client", lambda: client)
    return client


def test_set_displays_html_field_as_markdown_by_default(fake_client: _FakeClient) -> None:
    result = CliRunner().invoke(
        app,
        ["project-task", "set", "42", "description=# Task Details\n\n**Important**"],
    )

    assert result.exit_code == 0
    assert "description = # Task Details" in result.output
    assert "**Important**" in result.output
    assert "<h1>" not in result.output
    assert fake_client.tasks.updates == [
        (42, {"description": "<h1>Task Details</h1>\n<p><strong>Important</strong></p>"})
    ]


@pytest.mark.parametrize(
    ("value", "extra_args"),
    [
        (f"**{'authored-markdown-' * 8}**", []),
        (f"<p>{'raw-html-' * 16}</p>", ["--no-markdown", "--html"]),
    ],
)
def test_set_does_not_wrap_long_terminal_values(
    fake_client: _FakeClient,
    value: str,
    extra_args: list[str],
) -> None:
    result = CliRunner().invoke(
        app,
        ["project-task", "set", "42", f"description={value}", *extra_args],
    )

    assert result.exit_code == 0
    assert f"description = {value}" in click.unstyle(result.output)
    assert fake_client.tasks.updates


def test_set_preserves_authored_markdown_without_changing_write_payload(
    fake_client: _FakeClient,
) -> None:
    markdown = """![Architecture](https://example.com/diagram.png)

> Preserve this quote.

```python
print(\"hello\")
```

| Name | Value |
| --- | --- |
| one | two |"""
    expected_html = """<p><img alt="Architecture" src="https://example.com/diagram.png" /></p>
<blockquote>
<p>Preserve this quote.</p>
</blockquote>
<pre><code class="language-python">print(&quot;hello&quot;)
</code></pre>
<table>
<thead>
<tr>
<th>Name</th>
<th>Value</th>
</tr>
</thead>
<tbody>
<tr>
<td>one</td>
<td>two</td>
</tr>
</tbody>
</table>"""

    result = CliRunner().invoke(
        app,
        [
            "--json",
            "project-task",
            "set",
            "42",
            f"description={markdown}",
            "name=Keep me unchanged",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["updated"] == {
        "description": markdown,
        "name": "Keep me unchanged",
    }
    assert fake_client.tasks.updates == [
        (42, {"description": expected_html, "name": "Keep me unchanged"})
    ]


def test_set_no_markdown_displays_raw_html_readably_by_default(
    fake_client: _FakeClient,
) -> None:
    raw_html = "<h2>Raw HTML</h2><p><strong>Bold</strong></p>"

    result = CliRunner().invoke(
        app,
        ["--json", "project-task", "set", "42", f"description={raw_html}", "--no-markdown"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["updated"]["description"] == "## Raw HTML\n\n\n**Bold**"
    assert fake_client.tasks.updates == [(42, {"description": raw_html})]


def test_set_html_flag_displays_raw_html(fake_client: _FakeClient) -> None:
    result = CliRunner().invoke(
        app,
        ["project-task", "set", "42", "description=# Task Details", "--html"],
    )

    assert result.exit_code == 0
    assert "description = <h1>Task Details</h1>" in click.unstyle(result.output)
    assert fake_client.tasks.updates == [(42, {"description": "<h1>Task Details</h1>"})]


@pytest.mark.parametrize(
    ("extra_args", "expected_description"),
    [
        ([], "# Task Details"),
        (["--html"], "<h1>Task Details</h1>"),
    ],
)
def test_set_formats_structured_output(
    fake_client: _FakeClient,
    extra_args: list[str],
    expected_description: str,
) -> None:
    result = CliRunner().invoke(
        app,
        ["--json", "project-task", "set", "42", "description=# Task Details", *extra_args],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["updated"]["description"] == expected_description
    assert fake_client.tasks.updates == [(42, {"description": "<h1>Task Details</h1>"})]


def test_set_help_documents_markdown_default_and_html_opt_out() -> None:
    result = CliRunner().invoke(app, ["project-task", "set", "--help"])

    assert result.exit_code == 0
    output = click.unstyle(result.output)
    assert "--html" in output
    assert "raw HTML" in output
    assert "markdown is the default" in output
    assert "--description-file" in output


def test_set_description_file_utf8(fake_client: _FakeClient, tmp_path: Path) -> None:
    text = "  # Grüße 世界\n\n**Important**  \n"
    path = tmp_path / "task.md"
    path.write_bytes(text.encode())
    result = CliRunner().invoke(
        app, ["--json", "project-task", "set", "42", "--description-file", str(path)]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["updated"] == {"description": text}
    assert fake_client.tasks.updates == [
        (42, {"description": "<p># Grüße 世界</p>\n<p><strong>Important</strong>  </p>"})
    ]


@pytest.mark.parametrize("text", ["# Grüße 世界\n", "", "123", "true", "json:[]"])
def test_set_description_stdin_is_text(fake_client: _FakeClient, text: str) -> None:
    result = CliRunner().invoke(
        app,
        ["--json", "project-task", "set", "42", "--description-file", "-"],
        input=text,
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["updated"]["description"] == text
    assert isinstance(fake_client.tasks.updates[0][1]["description"], str)


@pytest.mark.parametrize("flags", [["--no-markdown"], ["--no-markdown", "--html"]])
def test_set_file_preserves_html_semantics(fake_client: _FakeClient, flags: list[str]) -> None:
    text = "  <p><strong>Grüße</strong></p>\n"
    result = CliRunner().invoke(
        app,
        ["--json", "project-task", "set", "42", "--description-file", "-", *flags],
        input=text,
    )
    assert result.exit_code == 0, result.output
    assert fake_client.tasks.updates == [(42, {"description": text})]
    expected = text if "--html" in flags else "**Grüße**"
    assert json.loads(result.output)["updated"]["description"] == expected


def test_set_file_html_output_and_other_assignments(fake_client: _FakeClient) -> None:
    result = CliRunner().invoke(
        app,
        ["--json", "project-task", "set", "42", "name=New", "--description-file", "-", "--html"],
        input="# Title",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["updated"] == {"name": "New", "description": "<h1>Title</h1>"}
    assert fake_client.tasks.updates == [(42, {"name": "New", "description": "<h1>Title</h1>"})]


@pytest.mark.parametrize(
    "assignment", ["description=text", " description = text", "description+=1"]
)
def test_set_file_conflict_before_client(monkeypatch: pytest.MonkeyPatch, assignment: str) -> None:
    def no_client() -> None:
        pytest.fail("Client must not be constructed")

    monkeypatch.setattr(main_module, "get_client", no_client)
    result = CliRunner().invoke(
        app,
        ["--json", "project-task", "set", "42", assignment, "--description-file", "missing.md"],
    )
    assert result.exit_code != 0
    assert "mutually exclusive" in json.loads(result.output)["error"]


@pytest.mark.parametrize("failure", ["missing", "directory", "unreadable", "utf8"])
def test_set_file_failure_before_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str
) -> None:
    def no_client() -> None:
        pytest.fail("Client must not be constructed")

    monkeypatch.setattr(main_module, "get_client", no_client)
    path = tmp_path / "task.md"
    if failure == "directory":
        path = tmp_path
    elif failure == "utf8":
        path.write_bytes(b"\xff")
    elif failure == "unreadable":

        def unreadable(_path: Path) -> bytes:
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "read_bytes", unreadable)
    result = CliRunner().invoke(
        app,
        ["--json", "project-task", "set", "42", "name=New", "--description-file", str(path)],
    )
    assert result.exit_code != 0
    assert "Cannot read UTF-8" in json.loads(result.output)["error"]


def test_set_no_input_fails_before_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_client() -> None:
        pytest.fail("Client must not be constructed")

    monkeypatch.setattr(main_module, "get_client", no_client)
    result = CliRunner().invoke(app, ["--json", "project-task", "set", "42"])
    assert result.exit_code != 0
    assert "Provide field assignments or --description-file" in json.loads(result.output)["error"]
