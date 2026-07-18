"""Phase 4 scanner tests (library level).

Covers the four Phase 4 validation criteria:
  1. scan --json on fixture-basic emits a schema-valid AgentProfile with both
     MCP tools, the model configuration, and provenance on every field.
  2. scan writes a schema-valid AgentCard; on fixture-carded it parses the
     existing card and writes nothing.
  3. On fixture-plain, scan exits 0 with "no agent signals found".
  4. Two scans of fixture-basic produce byte-identical output for all non-LLM
     fields.

All tests use a mocked provider (httpx.MockTransport); no live LLM is called.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from autogovern.ingest import scan_repo
from autogovern.models import AgentCard, AgentProfile

from .conftest import FIXTURES, mock_config


def _copy_fixture(name: str, tmp_path: Path) -> Path:
    """Copy a fixture repo into tmp so card writes never mutate the source."""
    dest = tmp_path / name
    shutil.copytree(FIXTURES / name, dest)
    return dest


# ---------------------------------------------------------------------------
# Criterion 1: fixture-basic profile content
# ---------------------------------------------------------------------------


def test_scan_basic_emits_valid_profile(tmp_path: Path, mock_provider) -> None:
    """scan on fixture-basic produces a schema-valid AgentProfile."""
    basic = _copy_fixture("fixture-basic", tmp_path)
    result = scan_repo(basic, mock_config(), provider=mock_provider)

    assert result.signals_found is True
    assert result.profile is not None
    # Re-validate the serialised profile against the Phase 1 schema.
    profile = AgentProfile.model_validate(result.profile.model_dump())
    assert profile.name == "support-triage-agent"
    assert profile.version == "0.3.0"


def test_scan_basic_contains_both_mcp_tools(tmp_path: Path, mock_provider) -> None:
    """The profile's permissions surface lists both MCP tools."""
    basic = _copy_fixture("fixture-basic", tmp_path)
    result = scan_repo(basic, mock_config(), provider=mock_provider)
    assert result.profile is not None

    tool_names = sorted(
        perm.detail.split(" — ")[0]
        for perm in result.profile.governance.permissions_surface.value
        if perm.kind == "tool"
    )
    assert tool_names == ["assign_ticket", "fetch_ticket"]


def test_scan_basic_contains_model_configuration(tmp_path: Path, mock_provider) -> None:
    """The profile carries the model configuration from source."""
    basic = _copy_fixture("fixture-basic", tmp_path)
    result = scan_repo(basic, mock_config(), provider=mock_provider)
    assert result.profile is not None

    mc = result.profile.governance.model_configuration.value
    assert mc.model == "claude-3-5-sonnet"
    assert mc.provider == "anthropic"
    assert mc.temperature == 0.0
    # Provenance points at the source file that declared the model.
    prov = result.profile.governance.model_configuration.provenance
    assert prov.source_path == "src/support_triage_agent.py"
    assert prov.content_hash


def test_scan_basic_provenance_on_every_governance_field(tmp_path: Path, mock_provider) -> None:
    """Every governance extension field carries non-empty provenance."""
    basic = _copy_fixture("fixture-basic", tmp_path)
    result = scan_repo(basic, mock_config(), provider=mock_provider)
    assert result.profile is not None

    gov = result.profile.governance
    for field_name in (
        "model_configuration",
        "permissions_surface",
        "data_categories",
        "dependencies",
        "prompt_inventory",
    ):
        field = getattr(gov, field_name)
        assert field.provenance.source_path, f"{field_name} missing provenance source_path"
        assert field.provenance.content_hash, f"{field_name} missing provenance content_hash"


def test_scan_basic_env_var_in_permission_surface(tmp_path: Path, mock_provider) -> None:
    """The env-var reference in source appears in the permissions surface."""
    basic = _copy_fixture("fixture-basic", tmp_path)
    result = scan_repo(basic, mock_config(), provider=mock_provider)
    assert result.profile is not None

    env_perms = [
        perm.detail
        for perm in result.profile.governance.permissions_surface.value
        if perm.kind == "env"
    ]
    assert "ANTHROPIC_API_KEY" in env_perms


# ---------------------------------------------------------------------------
# Criterion 2: AgentCard write / parse
# ---------------------------------------------------------------------------


def test_scan_basic_writes_valid_card(tmp_path: Path, mock_provider) -> None:
    """scan writes a schema-valid AgentCard when none exists."""
    basic = _copy_fixture("fixture-basic", tmp_path)
    result = scan_repo(basic, mock_config(), provider=mock_provider)

    assert result.card_written is True
    card_path = basic / ".well-known" / "agent.json"
    assert card_path.is_file()
    card = AgentCard.model_validate_json(card_path.read_text(encoding="utf-8"))
    assert card.name == "support-triage-agent"
    assert card.version == "0.3.0"


def test_scan_no_write_card_flag(tmp_path: Path, mock_provider) -> None:
    """write_card=False suppresses card writing."""
    basic = _copy_fixture("fixture-basic", tmp_path)
    result = scan_repo(basic, mock_config(), provider=mock_provider, write_card=False)

    assert result.card_written is False
    assert not (basic / ".well-known" / "agent.json").is_file()


def test_scan_carded_parses_existing_card_no_write(tmp_path: Path, mock_provider) -> None:
    """On fixture-carded, scan parses the existing card and writes nothing."""
    carded = _copy_fixture("fixture-carded", tmp_path)
    card_path = carded / ".well-known" / "agent.json"
    before = card_path.read_text(encoding="utf-8")

    result = scan_repo(carded, mock_config(), provider=mock_provider)

    assert result.card_written is False
    after = card_path.read_text(encoding="utf-8")
    assert before == after  # the existing card is untouched
    assert result.profile is not None
    # Card-standard fields come from the parsed card.
    assert result.profile.name == "support-triage-agent"
    assert len(result.profile.skills) == 2
    assert result.profile.provider is not None
    assert result.profile.provider.organization == "Acme Support"


# ---------------------------------------------------------------------------
# Criterion 3: fixture-plain — no agent signals
# ---------------------------------------------------------------------------


def test_scan_plain_no_signals(tmp_path: Path, mock_provider) -> None:
    """scan on fixture-plain reports no signals, not an empty profile."""
    plain = _copy_fixture("fixture-plain", tmp_path)
    result = scan_repo(plain, mock_config(), provider=mock_provider)

    assert result.signals_found is False
    assert result.profile is None
    assert result.card_written is False


# ---------------------------------------------------------------------------
# Criterion 4: determinism for non-LLM fields
# ---------------------------------------------------------------------------


def test_scan_determinism_non_llm_fields(tmp_path: Path, mock_provider) -> None:
    """Two scans of fixture-basic produce byte-identical non-LLM output."""
    basic_a = _copy_fixture("fixture-basic", tmp_path / "a")
    basic_b = _copy_fixture("fixture-basic", tmp_path / "b")

    result_a = scan_repo(basic_a, mock_config(), provider=mock_provider)
    result_b = scan_repo(basic_b, mock_config(), provider=mock_provider)
    assert result_a.profile is not None and result_b.profile is not None

    dump_a = result_a.profile.model_dump(mode="json")
    dump_b = result_b.profile.model_dump(mode="json")
    # data_categories is the only LLM-derived field; remove it before comparing.
    dump_a["governance"].pop("data_categories")
    dump_b["governance"].pop("data_categories")
    assert dump_a == dump_b

    # The written cards are byte-identical too.
    card_a = (basic_a / ".well-known" / "agent.json").read_text(encoding="utf-8")
    card_b = (basic_b / ".well-known" / "agent.json").read_text(encoding="utf-8")
    assert card_a == card_b


def test_scan_determinism_content_hashes_stable(tmp_path: Path, mock_provider) -> None:
    """Provenance content hashes are stable across scans (real sha256 of files)."""
    basic_a = _copy_fixture("fixture-basic", tmp_path / "a")
    basic_b = _copy_fixture("fixture-basic", tmp_path / "b")

    a = scan_repo(basic_a, mock_config(), provider=mock_provider).profile
    b = scan_repo(basic_b, mock_config(), provider=mock_provider).profile
    assert a is not None and b is not None

    assert (
        a.governance.model_configuration.provenance.content_hash
        == b.governance.model_configuration.provenance.content_hash
    )
    assert (
        a.governance.dependencies.provenance.content_hash
        == b.governance.dependencies.provenance.content_hash
    )
