"""Semver doc_version stamping.

Unit tests for the versioning primitives (parse, bump, classify, graph
mapping) plus engine integration tests: first generation stamps 0.1.0,
a model swap bumps system-card and inventory by one minor step and leaves
every other document's version untouched, and a context autonomy change
bumps the affected documents by a major step.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import yaml

from autogovern.context import default_context
from autogovern.detect.diff import FieldDiff
from autogovern.frameworks import load_pack
from autogovern.generate import generate_docs
from autogovern.generate.frontmatter import parse_frontmatter
from autogovern.ingest import scan_repo
from autogovern.models import Config, ContextManifest, ModelProviderConfig
from autogovern.versioning import (
    INITIAL_VERSION,
    classify_field_diff,
    doc_bump_levels,
    most_significant,
    next_version,
    parse_version,
)
from tests.conftest import make_mock_provider

FIXTURE_BASIC = Path(__file__).resolve().parent / "fixtures" / "fixture-basic"
GOV = "governance"


# ---------------------------------------------------------------------------
# Unit: parse and bump
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.2.3", (1, 2, 3)),
        ("0.1.0", (0, 1, 0)),
        ("10.20.30", (10, 20, 30)),
        ("a3f8c2d91e04", None),  # legacy hash style
        ("1.2", None),
        ("", None),
        (None, None),
        (42, None),
    ],
)
def test_parse_version(text: object, expected: tuple[int, int, int] | None) -> None:
    assert parse_version(text) == expected


def test_next_version_bumps() -> None:
    assert next_version("1.2.3", "major") == "2.0.0"
    assert next_version("1.2.3", "minor") == "1.3.0"
    assert next_version("1.2.3", "patch") == "1.2.4"


def test_next_version_legacy_restarts_at_initial() -> None:
    """Pre-semver (hash) versions restart at INITIAL_VERSION on regeneration."""
    assert next_version("a3f8c2d91e04", "minor") == INITIAL_VERSION
    assert next_version(None, "patch") == INITIAL_VERSION


# ---------------------------------------------------------------------------
# Unit: classification
# ---------------------------------------------------------------------------


def _permissions(*tools: str, env: list[str] | None = None) -> list[dict[str, str]]:
    perms = [{"kind": "tool", "detail": f"{t} — does {t}"} for t in tools]
    perms.extend({"kind": "env", "detail": name} for name in (env or []))
    return perms


@pytest.mark.parametrize(
    ("fd", "expected"),
    [
        (
            FieldDiff("context.agent.autonomy_level", "human-in-the-loop", "fully-autonomous"),
            "major",
        ),
        (FieldDiff("governance.data_categories", ["none"], ["personal"]), "major"),
        (FieldDiff("governance.model_configuration", {"model": "a"}, {"model": "b"}), "minor"),
        (FieldDiff("context.project.risk_appetite", "conservative", "aggressive"), "minor"),
        (FieldDiff("name", "a", "b"), "patch"),
        (FieldDiff("governance.dependencies", [], [{"name": "httpx"}]), "patch"),
        (FieldDiff("governance.prompt_inventory.paths", ["a.md"], ["a.md", "b.md"]), "patch"),
    ],
)
def test_classify_field_diff(fd: FieldDiff, expected: str) -> None:
    assert classify_field_diff(fd) == expected


def test_classify_permissions_tool_change_is_minor() -> None:
    fd = FieldDiff(
        "governance.permissions_surface",
        _permissions("fetch_ticket"),
        _permissions("fetch_ticket", "close_ticket"),
    )
    assert classify_field_diff(fd) == "minor"


def test_classify_permissions_scope_change_is_major() -> None:
    fd = FieldDiff(
        "governance.permissions_surface",
        _permissions("fetch_ticket", env=["ANTHROPIC_API_KEY"]),
        _permissions("fetch_ticket", env=["ANTHROPIC_API_KEY", "SLACK_TOKEN"]),
    )
    assert classify_field_diff(fd) == "major"


def test_most_significant() -> None:
    assert most_significant(["patch", "minor", "patch"]) == "minor"
    assert most_significant(["minor", "major"]) == "major"
    assert most_significant([]) == "patch"


# ---------------------------------------------------------------------------
# Unit: graph mapping via the real pack
# ---------------------------------------------------------------------------


def test_doc_bump_levels_model_change() -> None:
    """Model configuration feeds system-card and inventory, both minor."""
    pack = load_pack()
    fields = [FieldDiff("governance.model_configuration", {"model": "a"}, {"model": "b"})]
    levels = doc_bump_levels(fields, pack.graph)
    assert levels == {"inventory.md": "minor", "system-card.md": "minor"}


def test_doc_bump_levels_prompt_paths() -> None:
    pack = load_pack()
    fields = [FieldDiff("governance.prompt_inventory.paths", ["a.md"], ["a.md", "b.md"])]
    levels = doc_bump_levels(fields, pack.graph)
    assert levels == {"inventory.md": "patch"}


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, r)
    return r


@pytest.fixture
def config() -> Config:
    return Config(
        model_provider=ModelProviderConfig(
            api_base="https://mock.example.com/v1",
            model="mock-model",
            api_key_env="AUTOGOVERN_TEST_KEY",
        )
    )


def _generate(repo: Path, config: Config, context: ContextManifest) -> None:
    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    provider = make_mock_provider(config)
    try:
        scan_result = scan_repo(repo, config, provider=provider, write_card=False)
        assert scan_result.profile is not None
        generate_docs(repo, config, scan_result.profile, context, provider=provider)
    finally:
        provider.close()


def _doc_version(repo: Path, doc: str) -> str:
    fm, _ = parse_frontmatter((repo / GOV / doc).read_text())
    return str(fm["doc_version"])


def test_first_generation_stamps_initial_version(repo: Path, config: Config) -> None:
    _generate(repo, config, default_context())
    for doc in ("system-card.md", "inventory.md", "risk-assessment.md", "QUICKSTART.md"):
        assert _doc_version(repo, doc) == INITIAL_VERSION


def test_model_swap_bumps_only_affected_docs(repo: Path, config: Config) -> None:
    _generate(repo, config, default_context())

    # Swap the model id in the fixture source.
    source = repo / "src" / "support_triage_agent.py"
    source.write_text(source.read_text().replace("claude-3-5-sonnet", "gpt-4o-mini"))

    _generate(repo, config, default_context())

    # system-card and inventory consume model_configuration: minor bump.
    assert _doc_version(repo, "system-card.md") == "0.2.0"
    assert _doc_version(repo, "inventory.md") == "0.2.0"
    # Untouched documents keep their versions.
    assert _doc_version(repo, "risk-assessment.md") == INITIAL_VERSION
    assert _doc_version(repo, "oversight.md") == INITIAL_VERSION

    # The changelog records the bump and the significance.
    changelog = (repo / GOV / "CHANGELOG.md").read_text()
    assert "0.1.0 → 0.2.0" in changelog
    assert "Most significant change: minor" in changelog


def test_autonomy_change_bumps_major(repo: Path, config: Config) -> None:

    context = default_context()
    _generate(repo, config, context)

    context2 = context.model_copy(
        update={"agent": context.agent.model_copy(update={"autonomy_level": "fully-autonomous"})}
    )
    _generate(repo, config, context2)

    # system-card and oversight consume context.agent.autonomy_level: major bump.
    assert _doc_version(repo, "system-card.md") == "1.0.0"
    assert _doc_version(repo, "oversight.md") == "1.0.0"
    # inventory does not consume it.
    assert _doc_version(repo, "inventory.md") == INITIAL_VERSION


def test_idempotent_regenerate_keeps_versions(repo: Path, config: Config) -> None:
    """A no-op second generate leaves every doc_version unchanged."""
    _generate(repo, config, default_context())
    before = {
        doc: _doc_version(repo, doc)
        for doc in ("system-card.md", "inventory.md", "QUICKSTART.md", "CHANGELOG.md")
    }
    _generate(repo, config, default_context())
    after = {doc: _doc_version(repo, doc) for doc in before}
    assert before == after


def test_changelog_disabled_is_not_written(repo: Path, config: Config) -> None:
    """documents.changelog: false suppresses CHANGELOG.md entirely."""
    cfg = config.model_copy(update={"documents": {**config.documents, "changelog": False}})
    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    provider = make_mock_provider(cfg)
    try:
        scan_result = scan_repo(repo, cfg, provider=provider, write_card=False)
        assert scan_result.profile is not None
        generate_docs(repo, cfg, scan_result.profile, default_context(), provider=provider)
    finally:
        provider.close()
    assert not (repo / GOV / "CHANGELOG.md").exists()


def test_lockfiles_are_content_addressed(repo: Path, config: Config) -> None:
    """A no-op regenerate does not rewrite the lockfiles (mtime-stable)."""
    _generate(repo, config, default_context())
    profile_lock = repo / GOV / "profile.lock"
    context_lock = repo / GOV / "context.lock"
    mtimes = (profile_lock.stat().st_mtime_ns, context_lock.stat().st_mtime_ns)
    _generate(repo, config, default_context())
    assert (profile_lock.stat().st_mtime_ns, context_lock.stat().st_mtime_ns) == mtimes


def test_lockfiles_roundtrip(repo: Path, config: Config) -> None:
    """The written locks parse back into the Phase 1 models."""
    from autogovern.generate.lockfile import read_context_lock, read_lockfile

    _generate(repo, config, default_context())
    assert read_lockfile(repo / GOV) is not None
    locked_context = read_context_lock(repo / GOV)
    assert locked_context is not None
    assert locked_context.agent.autonomy_level == default_context().agent.autonomy_level


def test_generated_docs_have_sorted_yaml(repo: Path, config: Config) -> None:
    """Frontmatter stays valid YAML after the versioning changes."""
    _generate(repo, config, default_context())
    for doc in (repo / GOV).glob("*.md"):
        fm, _ = parse_frontmatter(doc.read_text())
        assert isinstance(fm, dict)
        assert fm["doc_version"] == INITIAL_VERSION
        assert yaml.safe_load(doc.read_text().split("---")[1]) is not None
