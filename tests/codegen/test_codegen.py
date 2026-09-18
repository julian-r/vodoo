"""Tests for deterministic multi-language namespace generation."""

from pathlib import Path

from tools.codegen.generator import OUTPUT_PATHS, check_generated, generate


def test_checked_in_project_namespaces_are_current() -> None:
    assert check_generated(Path.cwd())


def test_generation_is_deterministic(tmp_path: Path) -> None:
    root = Path.cwd()
    spec = tmp_path / "spec/v1/namespaces"
    spec.mkdir(parents=True)
    source = root / "spec/v1/namespaces/projects.yaml"
    (spec / "projects.yaml").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    first_paths = generate(tmp_path)
    first = {path.relative_to(tmp_path): path.read_text(encoding="utf-8") for path in first_paths}
    second_paths = generate(tmp_path)
    second = {path.relative_to(tmp_path): path.read_text(encoding="utf-8") for path in second_paths}

    assert first == second
    assert set(first) == set(OUTPUT_PATHS)
    assert all("DO NOT EDIT" in content for content in first.values())
    assert "GeneratedProjectNamespace" in first[OUTPUT_PATHS[0]]
    assert "GeneratedAsyncProjectNamespace" in first[OUTPUT_PATHS[2]]
