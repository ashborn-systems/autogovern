# Formatting

Production rules for the agentic-governance skill's output. Most governance deliverables are markdown documents; the rules below apply to them, with the deck-specific rules retained for the rare case the skill also produces a slide artefact. This file is self-contained.

## Currency

Default to USD unless the user specifies otherwise. If figures appear, state the conversion rate and date whenever an original figure is in another currency (for example, '£40k salary equivalent, converted at 1.3382 on 10 June 2026 = $53.5k'). Keep one currency across the whole document — never mix symbols.

## Derived figures: single calculation block

Where a governance document includes any derived figures (for example, a cost-of-control estimate or a risk-exposure number), define them once in a single calculation block and reference that block everywhere else. Never place raw arithmetic inline across multiple sections. When a source figure changes, the dependent figures then update from one place.

## Prose style in tables and notes

Write caption text, register cells, and notes as continuous prose, not label-colon fragments. 'Amber: the human gate. Every invoice passes it.' is the failure mode. Write what happens in plain sentences: 'Every invoice passes through the amber human review gate before anything is staged.'

## Preserving user edits

If the user supplies an edited version of a governance document, extract all of their text first and treat it as canonical. Apply only the specific changes requested. Do not touch surrounding wording, headings, parentheticals, or factual additions. Use targeted string replacement for small changes and full-box rewrites only where a section must be replaced wholesale.

## Deck rules (only if producing a slide artefact)

If the skill is asked to produce a slide deck rather than markdown:

- **Title card text colour** — detect the background before setting text colour. Use white for the main title and subtitle on a dark background; never apply dark text to a dark background, or it becomes invisible in the rendered file.
- **Bullet suppression** — templates often inject bullets on left-column placeholders. Suppress them explicitly on every text frame written to (zero the bullet mark and the hanging indent), or the template overrides the content.
- **Heading font size** — cap section heading placeholders at 20pt bold; do not let a heading auto-size upward and overflow into the body on content-heavy slides.
- **Removing stale template shapes** — before writing content to a template slide, delete any shape whose text carries placeholder instruction text (for example, text beginning with 'Note:').
