"""Tests for deterministic multi-language namespace generation."""

import re
from pathlib import Path
from shutil import copytree

import pytest
from pydantic import ValidationError

from tools.codegen.generator import (
    OUTPUT_PATHS,
    SPEC_DIR,
    all_output_paths,
    check_generated,
    generate,
    render_async_python,
    render_python,
    render_typescript,
    stale_outputs,
)
from tools.codegen.models import NamespaceSpec


def test_checked_in_namespaces_are_current() -> None:
    root = Path.cwd()
    assert check_generated(root)
    assert len(all_output_paths(root)) == 24
    assert set(OUTPUT_PATHS).issubset(all_output_paths(root))


def test_generation_is_deterministic_for_all_specs(tmp_path: Path) -> None:
    root = Path.cwd()
    copytree(root / SPEC_DIR, tmp_path / SPEC_DIR)

    first_paths = generate(tmp_path)
    first = {path.relative_to(tmp_path): path.read_text(encoding="utf-8") for path in first_paths}
    second_paths = generate(tmp_path)
    second = {path.relative_to(tmp_path): path.read_text(encoding="utf-8") for path in second_paths}

    assert first == second
    assert tuple(first) == all_output_paths(tmp_path)
    assert all("DO NOT EDIT" in content for content in first.values())
    assert "GeneratedProjectNamespace" in first[OUTPUT_PATHS[0]]
    assert "GeneratedAsyncProjectNamespace" in first[OUTPUT_PATHS[2]]
    assert any("GeneratedHelpdeskNamespace" in content for content in first.values())
    assert any("GeneratedAsyncTaskNamespace" in content for content in first.values())


def _minimal_spec(**overrides: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "specVersion": 1,
        "namespace": "sample",
        "className": "Sample",
        "model": "sample.model",
        "recordType": "Sample",
        "defaultFields": ["id"],
        "fieldSets": {"stages": ["id"]},
        "operations": [],
    }
    spec.update(overrides)
    return spec


@pytest.mark.parametrize(
    "override",
    [
        {"namespace": "class"},
        *(
            {
                "operations": [
                    {
                        "name": member,
                        "kind": "write",
                        "description": "member collision",
                        "model": "sample.model",
                        "idParameter": "recordId",
                        "values": {},
                    }
                ]
            }
            for member in ("constructor", "decodeRecord", "__init__", "list", "commentWithId")
        ),
        *(
            {
                "operations": [
                    {
                        "name": "stages",
                        "kind": "searchRead",
                        "description": "local collision",
                        "model": "sample.model",
                        "fields": "stages",
                        "order": "id",
                        "domain": {
                            "kind": "required",
                            "parameter": parameter,
                            "field": "id",
                            "operator": "=",
                        },
                    }
                ]
            }
            for parameter in ("self", "domain", "Self", "Domain")
        ),
        *(
            {
                "operations": [
                    {
                        "name": "updateRecord",
                        "kind": "write",
                        "description": "local collision",
                        "model": "sample.model",
                        "idParameter": parameter,
                        "values": {},
                    }
                ]
            }
            for parameter in ("self", "domain", "Self")
        ),
        {"fieldSets": {"model": ["id"]}},
        {"fieldSets": {"dateFields": ["id"]}},
        {
            "fieldSets": {
                "milestones": ["deadline"],
                "milestonesDateFields": ["id"],
            },
            "fieldSetDateFields": {"milestones": {"deadline": "date"}},
        },
        {
            "operations": [
                {
                    "name": "foo-bar",
                    "kind": "write",
                    "description": "bad",
                    "model": "sample.model",
                    "idParameter": "recordId",
                    "values": {},
                }
            ]
        },
        {
            "operations": [
                {
                    "name": "stages",
                    "kind": "searchRead",
                    "description": "bad",
                    "model": "sample.model",
                    "fields": "stages",
                    "order": "id",
                    "domain": {
                        "kind": "required",
                        "parameter": "class",
                        "field": "id",
                        "operator": "=",
                    },
                }
            ]
        },
        {"fieldSets": {"stage": ["id"], "stages": ["name"]}},
        {"fieldSets": {"fooBar": ["id"], "foo_bar": ["name"]}},
        {
            "operations": [
                {
                    "name": "update",
                    "kind": "write",
                    "description": "bad parameter",
                    "model": "sample.model",
                    "idParameter": "class",
                    "values": {},
                }
            ]
        },
        {
            "operations": [
                {
                    "name": name,
                    "kind": "write",
                    "description": "collision",
                    "model": "sample.model",
                    "idParameter": "recordId",
                    "values": {},
                }
                for name in ("getURL", "getUrl")
            ]
        },
    ],
)
def test_ir_rejects_unsafe_or_colliding_identifiers(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        NamespaceSpec.model_validate(_minimal_spec(**override))


def test_renderers_escape_operation_descriptions() -> None:
    spec = NamespaceSpec.model_validate(
        _minimal_spec(
            operations=[
                {
                    "name": "stages",
                    "kind": "searchRead",
                    "description": 'line one */\nline two """',
                    "model": "sample.model",
                    "fields": "stages",
                    "order": "id",
                }
            ]
        )
    )
    sync_source = render_python(spec)
    async_source = render_async_python(spec)
    compile(sync_source, "sample.py", "exec")
    compile(async_source, "async_sample.py", "exec")
    typescript_source = render_typescript(spec)
    assert "line one *\\/" in typescript_source
    assert "line one */" not in typescript_source


def test_safe_symbol_table_emits_compilable_python_and_unique_typescript_symbols() -> None:
    spec = NamespaceSpec.model_validate(
        _minimal_spec(
            fieldSets={"milestones": ["id", "deadline"]},
            fieldSetDateFields={"milestones": {"deadline": "date"}},
            operations=[
                {
                    "name": "milestoneTasks",
                    "kind": "searchRead",
                    "description": "List milestone tasks.",
                    "model": "sample.task",
                    "fields": "milestones",
                    "order": "id",
                    "domain": {
                        "kind": "required",
                        "parameter": "milestoneId",
                        "field": "milestone_id",
                        "operator": "=",
                    },
                }
            ],
        )
    )
    compile(render_python(spec), "sample.py", "exec")
    compile(render_async_python(spec), "async_sample.py", "exec")

    typescript_source = render_typescript(spec)
    constants = re.findall(r"^export const ([A-Z][A-Z0-9_]*) =", typescript_source, re.MULTILINE)
    assert len(constants) == len(set(constants))
    assert "async milestoneTasks(milestoneId: number)" in typescript_source


def test_spec_filename_must_match_namespace(tmp_path: Path) -> None:
    root = Path.cwd()
    copytree(root / SPEC_DIR, tmp_path / SPEC_DIR)
    projects = tmp_path / SPEC_DIR / "projects.yaml"
    projects.rename(tmp_path / SPEC_DIR / "wrong.yaml")

    with pytest.raises(ValueError, match="must match namespace"):
        generate(tmp_path)


def test_check_reports_orphaned_generated_files(tmp_path: Path) -> None:
    root = Path.cwd()
    copytree(root / SPEC_DIR, tmp_path / SPEC_DIR)
    generate(tmp_path)
    orphan = tmp_path / "packages/typescript/src/generated/orphan.ts"
    orphan.write_text(
        "// DO NOT EDIT — generated by python -m tools.codegen.\n",
        encoding="utf-8",
    )

    assert not check_generated(tmp_path)
    assert orphan.relative_to(tmp_path) in stale_outputs(tmp_path)
