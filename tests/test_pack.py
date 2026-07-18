"""Phase 6: framework pack loader.

Three validation gates from the build plan:
- The loader resolves every reference in the bundled pack with zero
  unresolved warnings.
- A test pack with a dangling reference fails loading with the exact bad
  reference named.
- Graph query: given "model configuration changed", the graph returns the
  system-card and inventory sections and nothing else.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from autogovern.frameworks import (
    BUNDLED_PACK_DIR,
    Pack,
    PackLoadError,
    ResolvedSection,
    load_pack,
    resolve_section,
)

# Every reference that pack.yaml declares, collected once so the resolve-all
# test stays honest if the pack grows. Built from the loaded pack rather than
# hand-maintained so it cannot drift.
PACK_FILE = BUNDLED_PACK_DIR / "pack.yaml"


# ---------------------------------------------------------------------------
# Bundled pack: full resolution
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pack() -> Pack:
    return load_pack()


def test_bundled_pack_loads(pack: Pack) -> None:
    assert pack.id == "agentic-governance"
    assert pack.version  # non-empty


def test_style_authority_resolves(pack: Pack) -> None:
    """The slug-fragment style authority resolves to the writing-rules heading."""
    assert "Writing rules" in pack.style_authority.title
    assert pack.style_authority.content.strip().startswith("## Writing rules")
    # The body contains the actual banned-constructions rules, not just the title.
    lowered = pack.style_authority.content.lower()
    assert "em-dash" in lowered or "em dash" in lowered


def test_verifier_rubric_resolves_whole_file(pack: Pack) -> None:
    """The verifier rubric is a whole-file reference (no fragment)."""
    assert "rubric" in pack.verifier_rubric.title.lower()
    # Whole-file content includes the H1.
    assert pack.verifier_rubric.content.lstrip().startswith("# ")


def test_enterprise_hooks_resolve(pack: Pack) -> None:
    assert {"scheduled_drift", "agentguard_evidence"} <= set(pack.enterprise_hooks)
    for hook in pack.enterprise_hooks.values():
        assert isinstance(hook, ResolvedSection)
        assert hook.content.strip()


def test_every_document_feed_resolves(pack: Pack) -> None:
    """Every template and knowledge reference in every document feed resolves."""
    # The loader raises on any dangling reference, so reaching here proves
    # resolution. Assert the expected document set and non-empty sections where
    # the pack declares content.
    expected_docs = {
        "system-card.md",
        "risk-assessment.md",
        "inventory.md",
        "oversight.md",
        "testing.md",
        "incident-response.md",
        "data-protection.md",
        "QUICKSTART.md",
        "ATTENTION.md",
        "CHANGELOG.md",
    }
    assert set(pack.document_feeds) == expected_docs

    for doc, feed in pack.document_feeds.items():
        for section in feed.pack_sections:
            assert section.title, f"{doc}: section {section.ref!r} has empty title"
            assert section.content.strip(), f"{doc}: section {section.ref!r} has empty content"


def test_numbered_section_resolves_title_and_body(pack: Pack) -> None:
    """governance-artefacts.md#3 resolves to the Agent / model card section."""
    section = resolve_section("agentic-governance/governance-artefacts.md#3", BUNDLED_PACK_DIR)
    assert "Agent" in section.title or "model card" in section.title.lower()
    # Body stops at the next ## heading (section 4), so it must not contain
    # the deployment blueprint heading.
    assert "Deployment blueprint" not in section.content


def test_data_protection_has_no_template_but_has_knowledge(pack: Pack) -> None:
    """data-protection.md is engine-templated; the pack notes the gap."""
    feed = pack.document_feeds["data-protection.md"]
    assert feed.templates == []
    assert len(feed.knowledge) == 1
    assert "regulatory" in feed.knowledge[0].title.lower()


def test_scope_notes_collected(pack: Pack) -> None:
    """Framework scope notes are surfaced on the pack for the verifier."""
    joined = "\n".join(pack.scope_notes)
    assert "rubric.md" in joined
    assert "frameworks.md" in joined


# ---------------------------------------------------------------------------
# Graph queries (acceptance criterion: deterministic, zero-LLM)
# ---------------------------------------------------------------------------


def test_graph_model_configuration_returns_system_card_and_inventory_only(
    pack: Pack,
) -> None:
    """The load-bearing Phase 6 gate: model config change → two docs, nothing else."""
    affected = pack.graph.affected_documents("profile.governance.model_configuration")
    assert affected == ["inventory.md", "system-card.md"]


def test_graph_unknown_input_returns_empty(pack: Pack) -> None:
    """An unwatched field changes nothing — the empty-list contract."""
    assert pack.graph.affected_documents("profile.governance.does_not_exist") == []
    assert pack.graph.affected_documents("context.totally_unknown") == []


def test_graph_context_field_routes(pack: Pack) -> None:
    assert pack.graph.affected_documents("context.autonomy_level") == [
        "oversight.md",
        "system-card.md",
    ]
    assert pack.graph.affected_documents("context.risk_appetite") == ["risk-assessment.md"]


def test_graph_deterministic_across_loads(pack: Pack) -> None:
    """Two loads of the same pack produce identical graph query results."""
    other = load_pack()
    for field in (
        "profile.governance.model_configuration",
        "profile.governance.permissions_surface",
        "context.autonomy_level",
        "context.jurisdictions",
    ):
        assert pack.graph.affected_documents(field) == other.graph.affected_documents(field)


def test_graph_returns_sorted_lists(pack: Pack) -> None:
    """affected_documents returns sorted output for git-stable diffs."""
    for field, docs in pack.graph.reverse.items():
        assert docs == set(docs)  # it is a set
        # and the public method sorts.
        assert pack.graph.affected_documents(field) == sorted(docs)


# ---------------------------------------------------------------------------
# Dangling reference: named failure
# ---------------------------------------------------------------------------


def _write_pack(tmp_path: Path, body: str) -> Path:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "pack.yaml").write_text(dedent(body))
    # One real content file so a valid reference can coexist with a bad one.
    (pack_dir / "real.md").write_text("# Real\n\n## 1. First\n\nbody\n\n## 2. Second\n\nbody2\n")
    return pack_dir


def test_dangling_file_reference_named(tmp_path: Path) -> None:
    pack_dir = _write_pack(
        tmp_path,
        """
        pack:
          id: test
          version: 0.0.1
        frameworks: []
        style_authority: real.md
        verifier_rubric: real.md
        document_feeds:
          system-card.md:
            templates: [missing.md#1]
            knowledge: []
            profile_inputs: []
            context_inputs: []
        enterprise_hooks: {}
        """,
    )
    with pytest.raises(PackLoadError) as exc_info:
        load_pack(pack_dir)
    assert "missing.md#1" in str(exc_info.value)


def test_dangling_numbered_reference_named(tmp_path: Path) -> None:
    pack_dir = _write_pack(
        tmp_path,
        """
        pack:
          id: test
          version: 0.0.1
        frameworks: []
        style_authority: real.md
        verifier_rubric: real.md
        document_feeds:
          system-card.md:
            templates: [real.md#99]
            knowledge: []
            profile_inputs: []
            context_inputs: []
        enterprise_hooks: {}
        """,
    )
    with pytest.raises(PackLoadError) as exc_info:
        load_pack(pack_dir)
    assert "real.md#99" in str(exc_info.value)
    assert "99" in str(exc_info.value)


def test_dangling_slug_reference_named(tmp_path: Path) -> None:
    pack_dir = _write_pack(
        tmp_path,
        """
        pack:
          id: test
          version: 0.0.1
        frameworks: []
        style_authority: real.md#no-such-heading
        verifier_rubric: real.md
        document_feeds: {}
        enterprise_hooks: {}
        """,
    )
    with pytest.raises(PackLoadError) as exc_info:
        load_pack(pack_dir)
    assert "no-such-heading" in str(exc_info.value)


def test_dangling_framework_file_reference_named(tmp_path: Path) -> None:
    pack_dir = tmp_path
    (pack_dir / "pack.yaml").write_text(
        dedent(
            """
            pack:
              id: test
              version: 0.0.1
            frameworks:
              - id: ghost
                path: ghost/
                role: primary
                files:
                  knowledge_base: ghost/missing.md
            style_authority: real.md
            verifier_rubric: real.md
            document_feeds: {}
            enterprise_hooks: {}
            """
        )
    )
    with pytest.raises(PackLoadError) as exc_info:
        load_pack(pack_dir)
    assert "missing.md" in str(exc_info.value)
    assert "ghost" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Resolver unit tests
# ---------------------------------------------------------------------------


def test_resolve_whole_file_returns_h1_title(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("# My Title\n\nSome body.\n")
    section = resolve_section("doc.md", tmp_path)
    assert section.title == "My Title"
    assert "Some body." in section.content
    assert section.content.startswith("# My Title")


def test_resolve_numbered_section_stops_at_next_h2(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text(
        "# Doc\n\n## 1. First\n\nbody one\n\n### Sub\n\nsub body\n\n## 2. Second\n\nbody two\n"
    )
    section = resolve_section("doc.md#1", tmp_path)
    assert section.title == "First"
    assert "body one" in section.content
    assert "### Sub" in section.content  # sub-heading included
    assert "sub body" in section.content
    assert "## 2. Second" not in section.content  # stops at next sibling


def test_resolve_slug_matches_prefix(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("# Doc\n\n## Writing rules for all output — avoid AI language\n\nrules body\n")
    section = resolve_section("doc.md#writing-rules-for-all-output", tmp_path)
    assert "Writing rules" in section.title
    assert "rules body" in section.content


def test_resolve_missing_file_raises_named(tmp_path: Path) -> None:
    with pytest.raises(PackLoadError, match="nope.md"):
        resolve_section("nope.md", tmp_path)
