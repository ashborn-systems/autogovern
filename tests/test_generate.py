"""Phase 7: the generation engine.

Four validation gates from the build plan:
- ``autogovern generate`` on fixture-basic (mocked LLM) produces the full
  document set, the lockfile, and valid frontmatter everywhere.
- Idempotence: a second generate immediately after produces zero git diff.
- Edit the fixture's model config, regenerate: only the sections the graph
  names are re-rendered (asserted by LLM call count and untouched mtimes).
- Style check: generated prompts contain the banned-constructions
  instruction block (snapshot test).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from autogovern.cli import app
from autogovern.context import default_context
from autogovern.frameworks import load_pack
from autogovern.generate import (
    STYLE_PREAMBLE,
    GenerationResult,
    build_section_messages,
    generate_docs,
)
from autogovern.ingest import scan_repo
from autogovern.models import AgentProfile, Config, ContextManifest, ModelProviderConfig
from autogovern.provider import ProviderClient
from tests.conftest import make_mock_provider

runner = CliRunner()

FIXTURE_BASIC = Path(__file__).resolve().parent / "fixtures" / "fixture-basic"
SLUG = "support-triage-agent"
GOV = "governance"
AGENT_GOV = f"governance/{SLUG}"


@pytest.fixture
def gen_repo(tmp_path: Path) -> Path:
    """A copy of fixture-basic in a temp dir, ready to generate into."""
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE_BASIC, repo)
    return repo


@pytest.fixture
def config() -> Config:
    return Config(
        model_provider=ModelProviderConfig(
            api_base="https://mock.example.com/v1",
            model="mock-model",
            api_key_env="AUTOGOVERN_TEST_KEY",
        )
    )


@pytest.fixture
def context() -> ContextManifest:
    return default_context()


def _scan_and_generate(
    repo: Path, config: Config, context: ContextManifest
) -> tuple[AgentProfile, GenerationResult, ProviderClient]:
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    provider = make_mock_provider(config)
    scan_result = scan_repo(repo, config, provider=provider, write_card=False)
    assert scan_result.agents
    result = generate_docs(
        repo,
        config,
        scan_result,
        context,
        provider=provider,
        context_from_file=True,
    )
    return scan_result.agents[0].profile, result, provider


# ---------------------------------------------------------------------------
# Gate 1: full document set, lockfile, valid frontmatter
# ---------------------------------------------------------------------------


def test_generate_produces_full_document_set(
    gen_repo: Path, config: Config, context: ContextManifest
) -> None:
    _, result, _ = _scan_and_generate(gen_repo, config, context)
    expected = {
        "QUICKSTART.md",
        "ATTENTION.md",
        "system-card.md",
        "risk-assessment.md",
        "data-protection.md",
        "oversight.md",
        "inventory.md",
        "testing.md",
        "incident-response.md",
        "CHANGELOG.md",
    }
    actual = {f.name for f in (gen_repo / GOV).iterdir() if f.is_file()}
    actual |= {f.name for f in (gen_repo / AGENT_GOV).iterdir() if f.is_file()}
    assert expected <= actual
    assert result.llm_call_count == 7  # the seven LLM-fed documents


def test_generate_writes_lockfile(gen_repo: Path, config: Config, context: ContextManifest) -> None:
    profile, _, _ = _scan_and_generate(gen_repo, config, context)
    lock = gen_repo / AGENT_GOV / "profile.lock"
    assert lock.is_file()
    locked = AgentProfile.model_validate(yaml.safe_load(lock.read_text()))
    assert locked.name == profile.name
    assert (
        locked.governance.model_configuration.value.model
        == profile.governance.model_configuration.value.model
    )


def test_every_document_has_valid_frontmatter(
    gen_repo: Path, config: Config, context: ContextManifest
) -> None:
    _, _, _ = _scan_and_generate(gen_repo, config, context)
    required_fields = {
        "doc_version",
        "agent_version",
        "generated",
        "generator_version",
        "input_hashes",
        "framework_pack_version",
        "section_hashes",
    }
    for doc in (gen_repo / GOV).iterdir():
        if doc.name in ("profile.lock", "context.lock") or not doc.is_file():
            continue
        text = doc.read_text()
        assert text.startswith("---"), f"{doc.name} missing frontmatter"
        end = text.index("\n---", 3)
        fm = yaml.safe_load(text[4:end])
        assert isinstance(fm, dict), f"{doc.name} frontmatter not a mapping"
        missing = required_fields - set(fm)
        assert not missing, f"{doc.name} missing frontmatter fields: {missing}"
        assert fm["framework_pack_version"], f"{doc.name} empty pack version"
        assert isinstance(fm["input_hashes"], dict), f"{doc.name} input_hashes not a dict"
        assert fm["section_hashes"], f"{doc.name} empty section_hashes"
    for doc in (gen_repo / AGENT_GOV).iterdir():
        if doc.name in ("profile.lock", "context.lock") or not doc.is_file():
            continue
        text = doc.read_text()
        assert text.startswith("---"), f"{doc.name} missing frontmatter"
        end = text.index("\n---", 3)
        fm = yaml.safe_load(text[4:end])
        assert isinstance(fm, dict), f"{doc.name} frontmatter not a mapping"
        missing = required_fields - set(fm)
        assert not missing, f"{doc.name} missing frontmatter fields: {missing}"
        assert fm["framework_pack_version"], f"{doc.name} empty pack version"
        assert isinstance(fm["input_hashes"], dict), f"{doc.name} input_hashes not a dict"
        assert fm["section_hashes"], f"{doc.name} empty section_hashes"


def test_input_hashes_contain_profile_provenance(
    gen_repo: Path, config: Config, context: ContextManifest
) -> None:
    profile, _, _ = _scan_and_generate(gen_repo, config, context)
    card_text = (gen_repo / AGENT_GOV / "system-card.md").read_text()
    end = card_text.index("\n---", 3)
    fm = yaml.safe_load(card_text[4:end])
    # The fixture's model-config source file should appear in input_hashes.
    assert any("support_triage_agent" in path for path in fm["input_hashes"])


# ---------------------------------------------------------------------------
# Gate 2: idempotence
# ---------------------------------------------------------------------------


def test_second_generate_produces_zero_diff(
    gen_repo: Path, config: Config, context: ContextManifest
) -> None:
    _, _, _ = _scan_and_generate(gen_repo, config, context)
    snapshot = _snapshot(gen_repo)

    _, result2, _ = _scan_and_generate(gen_repo, config, context)
    assert result2.llm_call_count == 0
    assert result2.regenerated == []

    diffs = [
        name for name, content in snapshot.items() if (gen_repo / GOV / name).read_text() != content
    ]
    assert diffs == [], f"idempotence broken: {diffs} changed"


def test_second_generate_reports_all_skipped(
    gen_repo: Path, config: Config, context: ContextManifest
) -> None:
    _, _, _ = _scan_and_generate(gen_repo, config, context)
    _, result2, _ = _scan_and_generate(gen_repo, config, context)
    assert sorted(result2.skipped) == [
        "support-triage-agent/data-protection.md",
        "support-triage-agent/incident-response.md",
        "support-triage-agent/inventory.md",
        "support-triage-agent/oversight.md",
        "support-triage-agent/risk-assessment.md",
        "support-triage-agent/system-card.md",
        "support-triage-agent/testing.md",
    ]


def test_second_generate_writes_nothing(
    gen_repo: Path, config: Config, context: ContextManifest
) -> None:
    _, _, _ = _scan_and_generate(gen_repo, config, context)
    _, result2, _ = _scan_and_generate(gen_repo, config, context)
    assert result2.written_files == []


# ---------------------------------------------------------------------------
# Gate 3: incremental regeneration by graph
# ---------------------------------------------------------------------------


def test_model_config_change_regenerates_only_graph_sections(
    gen_repo: Path, config: Config, context: ContextManifest
) -> None:
    import os
    import time

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    _, _, _ = _scan_and_generate(gen_repo, config, context)

    # Normalise mtimes so we can detect untouched files.
    gov = gen_repo / AGENT_GOV
    for f in gov.iterdir():
        if f.is_file():
            os.utime(f, (time.time(), time.time()))
    mtimes_before = {f.name: f.stat().st_mtime_ns for f in gov.iterdir() if f.suffix == ".md"}

    # Edit the model config: swap the model id in the fixture's source.
    src = gen_repo / "src" / "support_triage_agent.py"
    src.write_text(src.read_text().replace("claude-3-5-sonnet", "claude-3-5-haiku"))

    _, result3, _ = _scan_and_generate(gen_repo, config, context)

    # The graph names system-card and inventory for model_configuration.
    assert sorted(result3.regenerated) == [
        "support-triage-agent/inventory.md",
        "support-triage-agent/system-card.md",
    ]
    assert result3.llm_call_count == 2

    # The other five LLM-fed docs were not rewritten (mtimes untouched).
    mtimes_after = {f.name: f.stat().st_mtime_ns for f in gov.iterdir() if f.suffix == ".md"}
    untouched_llm_docs = {
        "risk-assessment.md",
        "data-protection.md",
        "oversight.md",
        "testing.md",
        "incident-response.md",
    }
    for doc in untouched_llm_docs:
        assert mtimes_before[doc] == mtimes_after[doc], f"{doc} was unexpectedly rewritten"


def test_changelog_appends_only_when_something_regenerated(
    gen_repo: Path, config: Config, context: ContextManifest
) -> None:
    _, _, _ = _scan_and_generate(gen_repo, config, context)
    changelog_before = (gen_repo / GOV / "CHANGELOG.md").read_text()
    entry_count_before = changelog_before.count("## ")

    # Idempotent run: no new changelog entry.
    _, result2, _ = _scan_and_generate(gen_repo, config, context)
    assert not result2.changed
    assert (gen_repo / GOV / "CHANGELOG.md").read_text().count("## ") == entry_count_before

    # Material edit: one new entry.
    src = gen_repo / "src" / "support_triage_agent.py"
    src.write_text(src.read_text().replace("claude-3-5-sonnet", "claude-3-5-haiku"))
    _, result3, _ = _scan_and_generate(gen_repo, config, context)
    assert result3.changed
    assert (gen_repo / GOV / "CHANGELOG.md").read_text().count("## ") == entry_count_before + 1


# ---------------------------------------------------------------------------
# Gate 4: style preamble in prompts (snapshot)
# ---------------------------------------------------------------------------


def test_style_preamble_contains_banned_constructions_block() -> None:
    """The exported STYLE_PREAMBLE carries every banned-construction rule.

    Snapshot test: editing the preamble deliberately requires updating this
    assertion, which flags drift in the style authority the generation prompts enforce.
    """
    for banned in (
        "em-dash",
        "contrastive negation",
        "significance inflation",
        "meta-signposting",
        "copula",
        "rhetorical triplets",
    ):
        assert banned in STYLE_PREAMBLE, f"style preamble lost the {banned!r} rule"
    # The affirmative rules are present too.
    assert "plain declarative sentences" in STYLE_PREAMBLE
    assert "concrete thresholds" in STYLE_PREAMBLE


def test_section_prompt_embeds_style_authority(
    gen_repo: Path, config: Config, context: ContextManifest
) -> None:
    """Every generated prompt carries the banned-constructions block."""
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    provider = make_mock_provider(config)
    scan_result = scan_repo(gen_repo, config, provider=provider, write_card=False)
    assert scan_result.agents[0].profile is not None
    agent_name = scan_result.agents[0].profile.name
    # Build a context with the agent's default context for prompt tests.
    from autogovern.models import AgentContext

    test_context = type(context)(
        project=context.project,
        agents={agent_name: AgentContext()},
    )
    pack = load_pack()
    feed = pack.document_feeds["system-card.md"]
    from autogovern.generate.inputs import extract_input

    declared = {
        p: extract_input(p, scan_result.agents[0].profile, test_context)
        for p in feed.profile_inputs
    }
    for p in feed.context_inputs:
        resolved = p
        if p.startswith("context.agents.*."):
            field_name = p.split("*.", 1)[1]
            resolved = f"context.agents.{agent_name}.{field_name}"
        declared[p] = extract_input(resolved, scan_result.agents[0].profile, test_context)
    messages = build_section_messages("system-card.md", feed, declared, pack.style_authority)
    system_prompt = messages[0]["content"]
    assert STYLE_PREAMBLE in system_prompt
    assert "banned" in system_prompt.lower() or "do not" in system_prompt.lower()
    # The pack's style-authority text is appended after the preamble.
    assert "Writing rules" in system_prompt
    provider.close()


def test_section_prompt_contains_only_declared_inputs(
    gen_repo: Path, config: Config, context: ContextManifest
) -> None:
    """The prompt includes declared inputs and excludes fields not declared."""
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    provider = make_mock_provider(config)
    scan_result = scan_repo(gen_repo, config, provider=provider, write_card=False)
    assert scan_result.agents[0].profile is not None
    pack = load_pack()
    feed = pack.document_feeds["inventory.md"]
    from autogovern.generate.inputs import extract_input

    declared = {
        p: extract_input(p, scan_result.agents[0].profile, context) for p in feed.profile_inputs
    }
    messages = build_section_messages("inventory.md", feed, declared, pack.style_authority)
    user_prompt = messages[1]["content"]
    # Declared input appears.
    assert "profile.governance.model_configuration" in user_prompt
    # A field inventory.md does not declare (risk_appetite) is absent.
    assert "context.project.risk_appetite" not in user_prompt
    provider.close()


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_generate_cli_writes_docs(
    gen_repo: Path, config: Config, context: ContextManifest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `autogovern generate` CLI produces the document set end to end."""
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    # Write config and context so the CLI can load them.
    (gen_repo / ".autogovern").mkdir(exist_ok=True)
    import yaml as _yaml

    (gen_repo / ".autogovern" / "config.yaml").write_text(
        _yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False)
    )
    (gen_repo / ".autogovern" / "context.yaml").write_text(
        _yaml.safe_dump(context.model_dump(mode="json"), sort_keys=False)
    )
    monkeypatch.chdir(gen_repo)

    # Inject the mocked provider so no live HTTP call is made.
    import autogovern.cli as cli_mod

    def _fake_build_provider(cfg: Config) -> ProviderClient:
        return make_mock_provider(cfg)

    monkeypatch.setattr(cli_mod, "build_provider", _fake_build_provider)

    result = runner.invoke(app, ["generate", str(gen_repo)])
    assert result.exit_code == 0, result.output
    assert "regenerated" in result.output.lower()
    assert (gen_repo / AGENT_GOV / "system-card.md").is_file()
    assert (gen_repo / AGENT_GOV / "profile.lock").is_file()


def test_generate_cli_no_agent_signals_exits_nonzero(
    tmp_path: Path, config: Config, context: ContextManifest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate on a plain (non-agent) repo exits 1."""
    import yaml as _yaml

    (tmp_path / ".autogovern").mkdir()
    (tmp_path / ".autogovern" / "config.yaml").write_text(
        _yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False)
    )
    (tmp_path / ".autogovern" / "context.yaml").write_text(
        _yaml.safe_dump(context.model_dump(mode="json"), sort_keys=False)
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["generate", str(tmp_path)])
    assert result.exit_code == 1
    assert "no agent signals" in result.output.lower()


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


def test_generate_failure_leaves_no_partial_files(
    gen_repo: Path, config: Config, context: ContextManifest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the provider fails mid-generation, existing docs are intact and no
    partial file is left behind (atomic temp-file rename)."""
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"

    # First, a clean generate.
    _, _, _ = _scan_and_generate(gen_repo, config, context)
    snapshot = _snapshot(gen_repo)

    # Now a provider that fails on the first LLM call.
    from autogovern.provider import ProviderError

    class FailingProvider:
        def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str:
            raise ProviderError("simulated failure")

        def close(self) -> None:
            pass

    provider = FailingProvider()
    # Edit FIRST, then scan, so the rebuilt profile's model_configuration
    # differs from the one stored in the existing documents.
    src = gen_repo / "src" / "support_triage_agent.py"
    src.write_text(src.read_text().replace("claude-3-5-sonnet", "claude-3-5-haiku"))
    scan_result = scan_repo(gen_repo, config, provider=make_mock_provider(config), write_card=False)
    assert scan_result.agents[0].profile is not None
    with pytest.raises(ProviderError):
        generate_docs(
            gen_repo,
            config,
            scan_result,
            context,
            provider=provider,
            context_from_file=True,
        )

    # No .tmp files left behind.
    gov = gen_repo / GOV
    assert not list(gov.rglob("*.tmp"))
    # Existing files are unchanged (the failure aborted before any write).
    for name, content in snapshot.items():
        assert (gov / name).read_text() == content


# ---------------------------------------------------------------------------
# Vanilla mode (no context manifest)
# ---------------------------------------------------------------------------


def test_vanilla_mode_generates_docs_without_context(gen_repo: Path, config: Config) -> None:
    """generate works without a context manifest; docs are generic."""
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    provider = make_mock_provider(config)
    scan_result = scan_repo(gen_repo, config, provider=provider, write_card=False)
    assert scan_result.agents[0].profile is not None
    context = default_context()  # vanilla: no context file loaded
    result = generate_docs(
        gen_repo,
        config,
        scan_result,
        context,
        provider=provider,
        context_from_file=False,
    )
    provider.close()

    assert result.llm_call_count == 7
    assert (gen_repo / AGENT_GOV / "system-card.md").is_file()
    assert (gen_repo / GOV / "ATTENTION.md").is_file()

    att = (gen_repo / GOV / "ATTENTION.md").read_text()
    assert "without a context manifest" in att
    assert "autogovern init" in att

    quickstart = (gen_repo / GOV / "QUICKSTART.md").read_text()
    assert "without a context manifest" in quickstart


def test_vanilla_mode_idempotent(gen_repo: Path, config: Config) -> None:
    """Vanilla mode is idempotent: second run produces zero diff."""
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    provider = make_mock_provider(config)
    scan_result = scan_repo(gen_repo, config, provider=provider, write_card=False)
    assert scan_result.agents[0].profile is not None
    context = default_context()
    generate_docs(
        gen_repo,
        config,
        scan_result,
        context,
        provider=provider,
        context_from_file=False,
    )
    provider.close()

    snapshot = _snapshot(gen_repo)

    provider2 = make_mock_provider(config)
    scan_result2 = scan_repo(gen_repo, config, provider=provider2, write_card=False)
    result2 = generate_docs(
        gen_repo,
        config,
        scan_result2,
        context,
        provider=provider2,
        context_from_file=False,
    )
    provider2.close()

    assert result2.llm_call_count == 0
    diffs = [
        name for name, content in snapshot.items() if (gen_repo / GOV / name).read_text() != content
    ]
    assert diffs == [], f"idempotence broken: {diffs}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snapshot(repo: Path) -> dict[str, str]:
    """Snapshot all governance files recursively."""
    result = {}
    gov = repo / GOV
    for f in gov.rglob("*"):
        if f.is_file():
            result[str(f.relative_to(gov))] = f.read_text()
    return result
