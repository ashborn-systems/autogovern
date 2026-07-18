"""Phase 9: material change detection.

Four validation gates from the build plan:
- Tool added to fixture-basic's .mcp.json: profile diff detected,
  deterministic score >= 80, zero LLM calls asserted.
- Unwatched file edited: heuristic pass negative, no profile rebuild, no LLM.
- Prompt text edited: semantic scorer invoked exactly once (mocked), band
  logic honoured for mocked scores of 15, 50, and 85.
- git log-friendliness: lockfile diffs are line-stable.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import httpx
import pytest

from autogovern.detect import detect_material_change
from autogovern.detect.heuristic import heuristic_pass
from autogovern.detect.scorer import (
    band_for,
    build_result,
    score_deterministic,
)
from autogovern.generate.lockfile import serialise_profile, write_lockfile
from autogovern.ingest import scan_repo
from autogovern.models import (
    AgentProfile,
    Config,
    MaterialityCriterion,
    ModelProviderConfig,
    Thresholds,
)
from tests.conftest import make_mock_provider

FIXTURE_BASIC = Path(__file__).resolve().parent / "fixtures" / "fixture-basic"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan(repo: Path, config: Config) -> AgentProfile:
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    provider = make_mock_provider(config)
    result = scan_repo(repo, config, provider=provider, write_card=False)
    provider.close()
    assert result.profile is not None
    return result.profile


def _config() -> Config:
    return Config(
        model_provider=ModelProviderConfig(
            api_base="https://mock.example.com/v1",
            model="mock-model",
            api_key_env="AUTOGOVERN_TEST_KEY",
        )
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, r)
    return r


# ---------------------------------------------------------------------------
# Gate 1: tool added → deterministic material, zero LLM
# ---------------------------------------------------------------------------


def test_tool_added_deterministic_material(repo: Path) -> None:
    """A new tool in .mcp.json scores >= 80 deterministically, no LLM."""
    config = _config()
    locked = _scan(repo, config)
    write_lockfile(repo / "governance", locked)

    # Add a third tool to .mcp.json.
    mcp_path = repo / ".mcp.json"
    mcp = json.loads(mcp_path.read_text())
    mcp["mcpServers"]["ticketing"]["tools"].append(
        {"name": "close_ticket", "description": "Close a support ticket."}
    )
    mcp_path.write_text(json.dumps(mcp, indent=2))

    current = _scan(repo, config)

    # No provider: deterministic scoring only. Zero LLM calls.
    result = detect_material_change(
        changed_files=[".mcp.json"],
        config=config,
        locked_profile=locked,
        current_profile=current,
    )

    assert result.heuristic.matched
    assert result.profile_diff is not None
    assert result.profile_diff.has_diff
    assert result.materiality is not None
    assert result.materiality.score >= 80
    assert result.materiality.band == "material"
    assert result.llm_call_count == 0
    # The criterion names the new tool.
    assert any("tool" in c.criterion.lower() for c in result.materiality.criteria)


def test_model_swap_deterministic_material(repo: Path) -> None:
    """A model swap scores material deterministically."""
    config = _config()
    locked = _scan(repo, config)
    write_lockfile(repo / "governance", locked)

    src = repo / "src" / "support_triage_agent.py"
    src.write_text(src.read_text().replace("claude-3-5-sonnet", "claude-3-5-haiku"))

    current = _scan(repo, config)
    result = detect_material_change(
        changed_files=["src/support_triage_agent.py"],
        config=config,
        locked_profile=locked,
        current_profile=current,
        ci_mode=True,
    )
    assert result.materiality is not None
    assert result.materiality.score >= 80
    assert result.materiality.band == "material"
    assert result.llm_call_count == 0
    assert any("model" in c.criterion.lower() for c in result.materiality.criteria)


def test_no_diff_when_unchanged(repo: Path) -> None:
    """No changes → no diff, no LLM, immaterial."""
    config = _config()
    locked = _scan(repo, config)
    write_lockfile(repo / "governance", locked)
    current = _scan(repo, config)

    result = detect_material_change(
        changed_files=[],
        config=config,
        locked_profile=locked,
        current_profile=current,
    )
    assert not result.heuristic.matched
    # Heuristic negative → no profile diff stage.
    assert result.materiality is None
    assert result.llm_call_count == 0


# ---------------------------------------------------------------------------
# Gate 2: unwatched file → heuristic negative, no rebuild
# ---------------------------------------------------------------------------


def test_unwatched_file_no_rebuild(repo: Path) -> None:
    """An unwatched file edit: heuristic negative, no profile diff, no LLM."""
    config = _config()
    locked = _scan(repo, config)
    write_lockfile(repo / "governance", locked)

    # Edit an unwatched file (README is not in the watched set).
    readme = repo / "README.md"
    readme.write_text(readme.read_text() + "\n\nA new paragraph.\n")

    result = detect_material_change(
        changed_files=["README.md"],
        config=config,
        locked_profile=locked,
        current_profile=locked,  # wouldn't even be rebuilt
    )
    assert not result.heuristic.matched
    assert result.profile_diff is None
    assert result.materiality is None
    assert result.llm_call_count == 0


def test_watched_file_triggers_heuristic(repo: Path) -> None:
    """A watched file (CLAUDE.md) triggers the heuristic pass."""
    config = _config()
    result = heuristic_pass(["CLAUDE.md"], config)
    assert result.matched
    assert "CLAUDE.md" in result.matched_paths


def test_nested_watched_file(repo: Path) -> None:
    """A file under .claude/** matches the watched glob."""
    config = _config()
    result = heuristic_pass([".claude/instructions.md"], config)
    assert result.matched


# ---------------------------------------------------------------------------
# Gate 3: prompt text edit → semantic scorer once, band logic
# ---------------------------------------------------------------------------


def _mock_semantic_provider(config: Config, score: int) -> object:
    """Build a mock provider returning a canned semantic score."""
    canned = json.dumps({"score": score, "reasoning": f"mocked score {score}"})

    def handler(request: httpx.Request) -> httpx.Response:
        body = {"choices": [{"message": {"role": "assistant", "content": canned}}]}
        return httpx.Response(200, content=json.dumps(body).encode())

    httpx.MockTransport(handler)
    return type(
        "MockProvider",
        (),
        {
            "chat_json": lambda self, messages, schema=None: _parse_score(canned),
            "chat": lambda self, messages: canned,
            "close": lambda self: None,
        },
    )()


def _parse_score(content: str):
    from autogovern.detect.scorer import SemanticScore

    return SemanticScore.model_validate(json.loads(content))


def test_prompt_edit_triggers_semantic_once(repo: Path) -> None:
    """A prompt content change invokes the semantic scorer exactly once."""
    config = _config()
    locked = _scan(repo, config)
    write_lockfile(repo / "governance", locked)

    # Edit prompt content (same path, new content).
    prompt = repo / "prompts" / "system.md"
    prompt.write_text(prompt.read_text() + "\n\nNew instruction.\n")

    current = _scan(repo, config)
    provider = _mock_semantic_provider(config, score=50)

    result = detect_material_change(
        changed_files=["prompts/system.md"],
        config=config,
        locked_profile=locked,
        current_profile=current,
        provider=provider,  # type: ignore[arg-type]
    )
    assert result.llm_call_count == 1
    assert result.materiality is not None
    assert result.materiality.score == 50


@pytest.mark.parametrize(
    "score,expected_band", [(15, "immaterial"), (50, "advisory"), (85, "material")]
)
def test_band_logic_honoured(score: int, expected_band: str) -> None:
    """Band logic: >=80 material, 21-79 advisory, <=20 immaterial."""
    thresholds = Thresholds()
    assert band_for(score, thresholds) == expected_band


def test_band_logic_with_custom_thresholds() -> None:
    """Custom thresholds from config are honoured."""
    thresholds = Thresholds(material=90, immaterial=10)
    assert band_for(85, thresholds) == "advisory"
    assert band_for(95, thresholds) == "material"
    assert band_for(5, thresholds) == "immaterial"


# ---------------------------------------------------------------------------
# Gate 4: lockfile line-stability
# ---------------------------------------------------------------------------


def test_lockfile_diffs_line_stable(repo: Path) -> None:
    """Two serialisations of the same profile are byte-identical (sorted keys)."""
    config = _config()
    profile = _scan(repo, config)
    first = serialise_profile(profile)
    second = serialise_profile(profile)
    assert first == second


def test_lockfile_sorted_keys(repo: Path) -> None:
    """The lockfile uses sorted keys so diffs are minimal and git-friendly."""
    config = _config()
    profile = _scan(repo, config)
    text = serialise_profile(profile)
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith(" ")]
    # Top-level keys should appear in sorted order.
    keys = [line.split(":")[0] for line in lines]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Deterministic scorer unit tests
# ---------------------------------------------------------------------------


def test_new_data_category_scores_material() -> None:
    from autogovern.detect.diff import FieldDiff

    diff = type(
        "D",
        (),
        {
            "fields": [
                FieldDiff(
                    field="governance.data_categories",
                    old=["personal"],
                    new=["personal", "financial"],
                )
            ],
            "semantic_fields": [],
            "has_diff": True,
        },
    )()
    criteria = score_deterministic(diff)
    assert len(criteria) == 1
    assert criteria[0].score >= 80
    assert "data category" in criteria[0].criterion.lower()


def test_permission_scope_change_scores_material() -> None:
    from autogovern.detect.diff import FieldDiff

    diff = type(
        "D",
        (),
        {
            "fields": [
                FieldDiff(
                    field="governance.permissions_surface",
                    old=[{"kind": "env", "detail": "KEY_A"}],
                    new=[{"kind": "env", "detail": "KEY_A"}, {"kind": "env", "detail": "KEY_B"}],
                )
            ],
            "semantic_fields": [],
            "has_diff": True,
        },
    )()
    criteria = score_deterministic(diff)
    assert len(criteria) == 1
    assert criteria[0].score >= 80


def test_build_result_takes_max_score() -> None:
    criteria = [
        MaterialityCriterion(criterion="a", score=50),
        MaterialityCriterion(criterion="b", score=90),
    ]
    result = build_result(criteria, Thresholds())
    assert result.score == 90
    assert result.band == "material"
