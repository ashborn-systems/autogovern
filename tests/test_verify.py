"""Phase 8: verifier and attention ledger.

Three validation gates from the build plan:
- Mocked verifier returning one unsupported claim: claim absent from the
  final document, one open item in ATTENTION.md naming the resolving input.
- Mocked verifier returning all-supported: ledger untouched.
- Rubric findings appear in the run manifest (GenerationResult), not in the
  documents.

Also covers: claim removal, ledger lifecycle (open then close on re-verify),
generation-time gaps, and the cleaner unit.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from autogovern.cli import app
from autogovern.context import default_context
from autogovern.generate import generate_docs
from autogovern.generate.ledger import stable_item_id
from autogovern.ingest import scan_repo
from autogovern.models import Config, ContextManifest, DataCategory, ModelProviderConfig
from autogovern.provider import ProviderClient
from tests.conftest import make_mock_provider

runner = CliRunner()

FIXTURE_BASIC = Path(__file__).resolve().parent / "fixtures" / "fixture-basic"
GOV = "governance"

# A claim that appears in the mocked generation content and is flagged
# unsupported by the mocked verifier.
UNSUPPORTED_CLAIM = "The agent uses GPT-4"
RESOLVING_INPUT = "profile.governance.model_configuration"
RUBRIC_CRITERION = "risks mapped to capabilities"
RUBRIC_FINDING = "no risks listed"

# Canned generation content: markdown containing the unsupported claim.
_GENERATION_CONTENT = f"# Document\n\n{UNSUPPORTED_CLAIM} for inference.\n\nOther content.\n"

# Canned verifier result: one unsupported claim + one rubric finding.
_UNSUPPORTED_VERIFICATION = {
    "section": "",
    "claims": [
        {
            "claim": UNSUPPORTED_CLAIM,
            "supported": False,
            "source_reference": "",
            "resolving_input": RESOLVING_INPUT,
        }
    ],
    "rubric_findings": [
        {"criterion": RUBRIC_CRITERION, "finding": RUBRIC_FINDING, "severity": "warning"}
    ],
}

# Canned verifier result: all claims supported, no findings.
_ALL_SUPPORTED_VERIFICATION = {
    "section": "",
    "claims": [],
    "rubric_findings": [],
}


def _make_verify_mock_provider(
    config: Config,
    *,
    verification: dict,
) -> ProviderClient:
    """Build a mock provider returning canned generation + verification output.

    Detection is by message content: verification prompts mention "verify".
    Everything else (generation and summarisation) gets the canned generation
    content (for chat) or the FreeTextSummary shape (for chat_json
    summarisation, detected by "summar" in the messages).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        messages = payload.get("messages", [])
        combined = " ".join(m.get("content", "") for m in messages).lower()
        is_json = payload.get("response_format") is not None

        if is_json and "verify" in combined:
            # Verifier pass (chat_json).
            content = json.dumps(verification)
        elif is_json:
            # Summarisation pass (chat_json, no "verify").
            content = json.dumps({"data_categories": ["personal"]})
        else:
            # Generation pass (chat, plain text).
            content = _GENERATION_CONTENT

        body = {"choices": [{"message": {"role": "assistant", "content": content}}]}
        return httpx.Response(200, content=json.dumps(body).encode())

    transport = httpx.MockTransport(handler)
    return ProviderClient(config, client=httpx.Client(transport=transport, timeout=30.0))


@pytest.fixture
def gen_repo(tmp_path: Path) -> Path:
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
def matching_context() -> ContextManifest:
    """A context whose data categories match the scan, so no generation gap."""
    ctx = default_context()
    ctx.data_categories = [DataCategory.PERSONAL]
    return ctx


def _scan_and_generate(
    repo: Path, config: Config, context: ContextManifest, provider: ProviderClient
):
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    scan_result = scan_repo(repo, config, provider=provider, write_card=False)
    assert scan_result.profile is not None
    result = generate_docs(repo, config, scan_result.profile, context, provider=provider)
    return scan_result.profile, result


# ---------------------------------------------------------------------------
# Gate 1: unsupported claim removed, attention item opened
# ---------------------------------------------------------------------------


def test_unsupported_claim_absent_from_document(
    gen_repo: Path, config: Config, matching_context: ContextManifest
) -> None:
    """The unsupported claim is removed from the final document."""
    provider = _make_verify_mock_provider(config, verification=_UNSUPPORTED_VERIFICATION)
    _, result = _scan_and_generate(gen_repo, config, matching_context, provider)
    provider.close()

    # The claim was in the generation content; it must be absent now.
    card_text = (gen_repo / GOV / "system-card.md").read_text()
    assert UNSUPPORTED_CLAIM not in card_text
    # Other content survives.
    assert "Other content" in card_text


def test_unsupported_claim_opens_attention_item(
    gen_repo: Path, config: Config, matching_context: ContextManifest
) -> None:
    """One open item in ATTENTION.md naming the resolving input."""
    provider = _make_verify_mock_provider(config, verification=_UNSUPPORTED_VERIFICATION)
    _, result = _scan_and_generate(gen_repo, config, matching_context, provider)
    provider.close()

    att_text = (gen_repo / GOV / "ATTENTION.md").read_text()
    assert RESOLVING_INPUT in att_text
    # At least one open item.
    fm, body = _split_frontmatter(att_text)
    items = fm.get("items", [])
    open_items = [i for i in items if i.get("status") == "open"]
    assert len(open_items) >= 1
    assert any(i.get("resolving_input") == RESOLVING_INPUT for i in open_items)

    # The attention item is also on the result for the run manifest.
    assert any(
        ai.action == "open" and "system-card.md" in ai.detail for ai in result.attention_items
    )


def test_unsupported_claim_stable_id(
    gen_repo: Path, config: Config, matching_context: ContextManifest
) -> None:
    """The item id is the stable hash of section + resolving_input."""
    provider = _make_verify_mock_provider(config, verification=_UNSUPPORTED_VERIFICATION)
    _, _ = _scan_and_generate(gen_repo, config, matching_context, provider)
    provider.close()

    att_text = (gen_repo / GOV / "ATTENTION.md").read_text()
    fm, _ = _split_frontmatter(att_text)
    items = fm.get("items", [])
    expected_id = stable_item_id("system-card.md", RESOLVING_INPUT)
    assert any(i.get("item_id") == expected_id for i in items)


# ---------------------------------------------------------------------------
# Gate 2: all-supported → ledger untouched
# ---------------------------------------------------------------------------


def test_all_supported_leaves_ledger_empty(
    gen_repo: Path, config: Config, matching_context: ContextManifest
) -> None:
    """When the verifier returns all-supported, no open items are opened."""
    provider = _make_verify_mock_provider(config, verification=_ALL_SUPPORTED_VERIFICATION)
    _, result = _scan_and_generate(gen_repo, config, matching_context, provider)
    provider.close()

    att_text = (gen_repo / GOV / "ATTENTION.md").read_text()
    fm, _ = _split_frontmatter(att_text)
    items = fm.get("items", [])
    open_items = [i for i in items if i.get("status") == "open"]
    assert open_items == []
    assert "(none)" in att_text  # the empty-ledger body marker

    # No attention items opened by the verifier.
    assert not any(ai.action == "open" for ai in result.attention_items)


# ---------------------------------------------------------------------------
# Gate 3: rubric findings in manifest, not in documents
# ---------------------------------------------------------------------------


def test_rubric_findings_in_result_not_in_documents(
    gen_repo: Path, config: Config, matching_context: ContextManifest
) -> None:
    """Rubric findings appear on GenerationResult, never in the document body."""
    provider = _make_verify_mock_provider(config, verification=_UNSUPPORTED_VERIFICATION)
    _, result = _scan_and_generate(gen_repo, config, matching_context, provider)
    provider.close()

    # The finding is on the result (for the run manifest).
    all_findings = []
    for vr in result.verifier_results:
        all_findings.extend(vr.findings)
    assert any(RUBRIC_CRITERION in str(f) for f in all_findings)
    assert any(RUBRIC_FINDING in str(f) for f in all_findings)

    # The finding is NOT in any document body.
    for doc in (gen_repo / GOV).iterdir():
        if doc.name == "profile.lock" or not doc.is_file():
            continue
        _, body = _split_frontmatter(doc.read_text())
        assert RUBRIC_CRITERION not in body, f"{doc.name} leaked a rubric finding"
        assert RUBRIC_FINDING not in body, f"{doc.name} leaked a rubric finding"


def test_verifier_results_have_correct_counts(
    gen_repo: Path, config: Config, matching_context: ContextManifest
) -> None:
    """Each regenerated section has a verifier result with claim counts."""
    provider = _make_verify_mock_provider(config, verification=_UNSUPPORTED_VERIFICATION)
    _, result = _scan_and_generate(gen_repo, config, matching_context, provider)
    provider.close()

    assert len(result.verifier_results) == 7  # one per LLM-fed doc
    for vr in result.verifier_results:
        assert vr.unsupported_claims == 1
        assert vr.supported_claims == 0
        assert len(vr.findings) == 1


def test_verifier_call_count(
    gen_repo: Path, config: Config, matching_context: ContextManifest
) -> None:
    """One verifier call per regenerated section."""
    provider = _make_verify_mock_provider(config, verification=_UNSUPPORTED_VERIFICATION)
    _, result = _scan_and_generate(gen_repo, config, matching_context, provider)
    provider.close()

    assert result.verifier_call_count == 7
    assert result.llm_call_count == 7  # generation calls, separate from verify


# ---------------------------------------------------------------------------
# Ledger lifecycle: open then close
# ---------------------------------------------------------------------------


def test_ledger_closes_resolved_item_on_clean_reverify(
    gen_repo: Path, config: Config, matching_context: ContextManifest
) -> None:
    """An item opened in run 1 closes in run 2 when the verifier is clean."""
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"

    # Run 1: unsupported claim → item opened.
    provider1 = _make_verify_mock_provider(config, verification=_UNSUPPORTED_VERIFICATION)
    _, result1 = _scan_and_generate(gen_repo, config, matching_context, provider1)
    provider1.close()
    assert any(ai.action == "open" for ai in result1.attention_items)

    # Run 2: same inputs (no regeneration) → verifier doesn't run → item stays.
    # To force re-verification with a clean verdict, edit the model so inputs
    # change, then use an all-supported verifier.
    src = gen_repo / "src" / "support_triage_agent.py"
    src.write_text(src.read_text().replace("claude-3-5-sonnet", "claude-3-5-haiku"))

    provider2 = _make_verify_mock_provider(config, verification=_ALL_SUPPORTED_VERIFICATION)
    _, result2 = _scan_and_generate(gen_repo, config, matching_context, provider2)
    provider2.close()

    # The previously-open item for system-card.md is now closed.
    att_text = (gen_repo / GOV / "ATTENTION.md").read_text()
    fm, _ = _split_frontmatter(att_text)
    items = fm.get("items", [])
    system_card_items = [i for i in items if i.get("section") == "system-card.md"]
    assert any(i.get("status") == "closed" for i in system_card_items)
    assert not any(
        i.get("status") == "open" and i.get("section") == "system-card.md" for i in items
    )


def test_ledger_persists_across_runs(
    gen_repo: Path, config: Config, matching_context: ContextManifest
) -> None:
    """An open item persists across an idempotent re-run."""
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"

    provider1 = _make_verify_mock_provider(config, verification=_UNSUPPORTED_VERIFICATION)
    _, _ = _scan_and_generate(gen_repo, config, matching_context, provider1)
    provider1.close()

    att_after_run1 = (gen_repo / GOV / "ATTENTION.md").read_text()

    # Idempotent re-run: no regeneration, no verification.
    provider2 = make_mock_provider(config)
    _, result2 = _scan_and_generate(gen_repo, config, matching_context, provider2)
    provider2.close()

    assert result2.regenerated == []
    assert result2.verifier_call_count == 0

    # The ledger is unchanged (same open items).
    att_after_run2 = (gen_repo / GOV / "ATTENTION.md").read_text()
    fm1, body1 = _split_frontmatter(att_after_run1)
    fm2, body2 = _split_frontmatter(att_after_run2)
    assert body1 == body2  # the human-readable body is unchanged


# ---------------------------------------------------------------------------
# Generation-time gaps
# ---------------------------------------------------------------------------


def test_generation_gap_data_category_mismatch(gen_repo: Path, config: Config) -> None:
    """Scan finds data categories but context declares none → ledger item."""
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    # default_context declares data_categories=[NONE]; scan finds ["personal"].
    context = default_context()
    provider = make_mock_provider(config)
    _, result = _scan_and_generate(gen_repo, config, context, provider)
    provider.close()

    att_text = (gen_repo / GOV / "ATTENTION.md").read_text()
    assert "context.data_categories" in att_text
    assert "data-protection.md" in att_text

    # The gap is also on the result.
    assert any(
        ai.action == "open" and "data categories" in ai.detail for ai in result.attention_items
    )


# ---------------------------------------------------------------------------
# Claim cleaner unit tests
# ---------------------------------------------------------------------------


def test_remove_unsupported_claims_drops_matching_lines() -> None:
    from autogovern.verify import remove_unsupported_claims

    content = "# System card\n\nThe agent uses GPT-4.\n\nOther content.\n"
    result = remove_unsupported_claims(content, ["The agent uses GPT-4"])
    assert "GPT-4" not in result
    assert "Other content" in result
    assert "# System card" in result


def test_remove_unsupported_claims_noop_when_empty() -> None:
    from autogovern.verify import remove_unsupported_claims

    content = "# Doc\n\nBody.\n"
    assert remove_unsupported_claims(content, []) == content
    assert remove_unsupported_claims(content, [""]) == content


def test_remove_unsupported_claims_case_insensitive() -> None:
    from autogovern.verify import remove_unsupported_claims

    content = "# Doc\n\nThe Agent Uses GPT-4.\n\nKept.\n"
    result = remove_unsupported_claims(content, ["the agent uses gpt-4"])
    assert "GPT-4" not in result
    assert "Kept" in result


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_generate_cli_with_verifier(
    gen_repo: Path,
    config: Config,
    matching_context: ContextManifest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI generate runs the verifier and writes the ledger."""
    import os

    os.environ["AUTOGOVERN_TEST_KEY"] = "sk-test"
    (gen_repo / ".autogovern").mkdir(exist_ok=True)
    (gen_repo / ".autogovern" / "config.yaml").write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False)
    )
    (gen_repo / ".autogovern" / "context.yaml").write_text(
        yaml.safe_dump(matching_context.model_dump(mode="json"), sort_keys=False)
    )
    monkeypatch.chdir(gen_repo)

    import autogovern.cli as cli_mod

    def _fake_build_provider(cfg: Config) -> ProviderClient:
        return _make_verify_mock_provider(cfg, verification=_UNSUPPORTED_VERIFICATION)

    monkeypatch.setattr(cli_mod, "build_provider", _fake_build_provider)

    result = runner.invoke(app, ["generate", str(gen_repo)])
    assert result.exit_code == 0, result.output
    assert (gen_repo / GOV / "ATTENTION.md").is_file()
    att = (gen_repo / GOV / "ATTENTION.md").read_text()
    assert RESOLVING_INPUT in att


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a document into (frontmatter_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.index("\n---", 3)
    fm = yaml.safe_load(text[4:end])
    if not isinstance(fm, dict):
        fm = {}
    body = text[end + 4 :]
    return fm, body
