"""Tests for deterministic multi-language namespace generation."""

from pathlib import Path

from tools.codegen.generator import OUTPUT_PATH, check_generated, generate


def test_checked_in_project_namespace_is_current() -> None:
    assert check_generated(Path.cwd())


def test_generation_is_deterministic(tmp_path: Path) -> None:
    root = Path.cwd()
    spec = tmp_path / "spec/v1/namespaces"
    spec.mkdir(parents=True)
    source = root / "spec/v1/namespaces/projects.yaml"
    (spec / "projects.yaml").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    first = generate(tmp_path).read_text(encoding="utf-8")
    second = generate(tmp_path).read_text(encoding="utf-8")

    assert first == second
    assert "DO NOT EDIT" in first
    assert "GeneratedProjectNamespace" in first
    assert (tmp_path / OUTPUT_PATH).exists()
