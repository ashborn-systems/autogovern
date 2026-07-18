---
name: agentic-governance
description: Build and continuously run a complete governance programme for an agentic AI project. Use this skill whenever the user wants to govern, control, oversee, audit, or document an AI agent or agentic system — including requests like "build a governance plan for my agent", "create the governance documentation", "set up oversight and controls for this agent", "run governance for my deployment", "produce a deployment blueprint", "do a risk assessment for my agent", or "keep my agent compliant over time". It runs alongside the agentic-business-case skill: that skill plans the agent, this skill governs it. The skill has two modes — a build mode that produces the full governance documentation set, and a run mode that executes a repeatable ongoing-governance loop designed to be invoked continuously so the project stays governed in perpetuity. Exhaustive interviewing of the user is expected to capture every governance input the plan needs.
---

# Agentic governance builder and operator

Takes an agentic AI project — ideally one that already has a business plan from a companion business-case skill (`agentic-business-case`) — and does two things:

1. **Build mode** — produces a complete governance plan and documentation set: a governance register entry, a risk → control mapping, a deployment blueprint, an agent/model card, a monitoring and incident-response plan, and a completed pre-deployment checklist.
2. **Run mode** — executes a repeatable ongoing-governance loop (monitoring review, audit-log review, drift and boundary checks, periodic re-assessment, version and change control, regulatory-change watch, red-team cadence, and decommissioning criteria). Run mode is designed to be invoked repeatedly so a live agent stays governed over its entire lifetime.

The work applies to any enterprise. Do not assume a specific organisation, sector, or regulatory regime unless the user states it.

This skill is self-contained. Everything it needs is in this directory (`references/`); it has no external dependencies and does not require the business-case skill to be present.

## Required reading before starting

Read these in order — do not skip any:

1. `references/governance-frameworks.md` — the knowledge base and source of truth. Every control, risk vector, testing method, metric, and regulatory principle this skill applies is defined here, with citations.
2. `references/governance-artefacts.md` — the template for every documentation artefact this skill produces.
3. `references/ongoing-governance-runbook.md` — the perpetual-operation loop: what to check, on what cadence, and how to record it.
4. `references/formatting.md` — production rules for output: one currency throughout, derive any figures from a single calculation block, write notes as continuous prose, and preserve user edits to any supplied document.
5. **Prose style** — if an oxford-markdown skill is available in your environment, follow it for prose structure; otherwise use the fallback markdown style at the end of this file. Either way, the writing rules below override conflicting style conventions for generated deliverables.

## Build mode

### Step 1 — Interview the user exhaustively

The default is to ask, not to assume. If a business plan already exists, read it first and carry over everything it establishes (problem, design, systems, owner, HITL thresholds); only ask for what is missing. Otherwise, gather across multiple rounds until every artefact can be completed with real inputs.

Cover at least:

- **Autonomy and impact** — what the agent does autonomously; whether a human is in-the-loop or on-the-loop; what it can execute that is irreversible or high-value
- **Systems and data access** — every tool, API, database, and model the agent touches; read versus write per system; whether it ingests external content (which forces indirect-injection testing); personal or sensitive data involved, its classification and residency, and whether only organisation-approved model providers may be used
- **Risk vectors in play** — which of the six governance risk vectors apply (autonomy/loss of control, real-world impact, complexity/transparency, accountability, data access/security, errors at scale), plus the relevant red-team attack vectors
- **Regulatory exposure** — applicable regimes (GDPR, CCPA, sector rules, EU AI Act), transparency-disclosure obligations, and the deployment-liability position
- **Ownership and oversight** — the named human owner; who monitors; who can authorise deactivation; existing approval thresholds
- **HITL thresholds** — the exact financial, confidence, or risk thresholds that must trigger human approval, and the actions on the never-execute list
- **Failure and recovery** — the kill switch mechanism, the rollback to the manual process, and the incident-response chain
- **Cadence** — how often the agent should be re-tested, re-assessed, and red-teamed, proportional to its privilege and risk

If the user asks to assume a value, construct a credible default from the guide and label it as an assumption.

### Step 2 — Run the first-principles risk assessment

Before writing controls, answer the four first-principles questions from `references/governance-frameworks.md` (section 8): the absolute operational limit if guardrails fail; the specific failure and adversarial vectors; the quantified consequence of failure at scale; and whether oversight matches risk severity. Set the governance intensity from the answer — autonomy granted must be proportional to risk created.

### Step 3 — Produce the governance documentation set

Using `references/governance-artefacts.md`, produce each artefact, filled with the user's real inputs:

- **Central agent register entry** — ID, name, purpose, named owner, authorised datasets and tools, permission scope, oversight responsibilities
- **Risk → control mapping** — every applicable risk vector mapped one-to-one to a named control; always include audit logging, kill switch and rollback, the sandbox protocol matched to privilege, and the AI transparency disclosure
- **Agent / model card** — how the agent was built, tested, and is intended to be used; conditions tested, validation dimensions, appropriate contexts
- **Deployment blueprint** — technical controls, procedural controls, organisational accountability, and ethical and operational principles (the consolidated checklist in `references/governance-artefacts.md`)
- **Monitoring and incident-response plan** — the live dashboard scope, escalation alerts, the named overseer, and the documented response chain (who identifies, who escalates, who deactivates)
- **Pre-deployment checklist** — the eight-point check with status and evidence per item

### Step 4 — Audit and deliver

Confirm every applicable control from `references/governance-frameworks.md` is present and mapped, the eight-point checklist passes, and the owner and recovery procedures are named and testable. Deliver the documentation set with a short summary of residual risks and any assumptions to verify. Then set up run mode by recording the review cadence.

## Run mode — perpetual governance

Run mode executes the ongoing-governance loop in `references/ongoing-governance-runbook.md`. It is designed to be invoked repeatedly (on a schedule or on a trigger such as a model update, a scope change, or an incident) so the project stays governed indefinitely. Each run:

1. Reviews the monitoring dashboard and escalation alerts since the last run
2. Reviews the audit log for boundary violations, anomalous access, and drift in step efficiency
3. Re-runs the golden dataset if the model, prompt, tools, or permissions changed, and investigates any regression
4. Re-runs the first-principles risk assessment on the periodic schedule, or whenever scope, data, or model changed, and confirms the risk → control mapping still holds
5. Checks the red-team cadence and triggers adversarial testing when due
6. Applies version and change control — no change to a live agent without review and re-testing
7. Watches for regulatory change (GDPR, EU AI Act, sector and state rules) and reassesses compliance and the deployment-liability position when the landscape shifts
8. Applies decommissioning criteria when met — revoke access, close the register entry, confirm the manual fallback
9. Records findings, actions, and the next review date, and updates the affected artefacts

A run that finds nothing still records the review and the next date. A run that finds an issue opens an action, assigns it to the named owner, and re-tests before closing.

## Writing rules for all output — avoid common AI language, ticks, and style

These rules apply to every artefact and summary generated. They override conflicting conventions in any other style guide, including oxford-markdown. The test: a reader should hear a risk officer, not a language model.

Banned constructions:

- **Em-dashes** anywhere. Use commas, colons, parentheses, or restructure. Headings carry no separator punctuation; definitions use `**Term**: definition`
- **Contrastive negation** — "not X, but Y", "rather than X, this is Y". State the positive claim directly
- **Rhetorical triplets** for cadence. Lists of three are fine when the content genuinely has three items
- **Significance inflation** — crucial, critical, robust, comprehensive, seamless, transformative, game-changing, cutting-edge, unlock, leverage (as a verb), delve, landscape, journey, empower
- **Copula avoidance** — "serves as", "stands as", "acts as", "functions as". Write "is"
- **Meta-signposting and hedged emphasis** — "It's worth noting", "Importantly", "In essence", "Notably", "Let's explore"
- **"Not only X but also Y"**

Write plain declarative sentences, concrete thresholds and figures, and verbs that name the actual control.

## Fallback markdown style (if no oxford-markdown skill present)

British English throughout. Oxford commas. Sentence case for headings; `#` for the document title only, `##` for sections, `###` for subsections. Tables for parallel comparisons and registers. `**Term**: definition` with no terminal full stop. Concise prose, no walls of text, no marketing inflation. All writing rules above apply.
