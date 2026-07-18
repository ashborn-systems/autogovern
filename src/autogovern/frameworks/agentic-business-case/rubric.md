# Quality rubric — agentic AI business case

A general quality rubric for an agentic AI business case, adapted from the Oxford Saïd programme's marking criteria. Each section states what a **strong** case looks like, plus the failure modes that weaken it. Audit the finished plan and deck against every line here before delivering.

## Problem definition and justification

A strong case shows:
- Sophisticated understanding of the organisational bottleneck — quantified, scoped to specific workflows and stakeholders
- Compelling, evidence-based justification for agentic AI
- **Critical appraisal of alternative AI and non-AI paths** — explicitly name and reject the other AI adoption matrix clusters, plus non-AI options (process redesign, hiring)
- Disciplined judgement about technological fit and systemic constraints

Weakens when: suitability is asserted rather than proven; alternatives are not considered; the problem is generic.

## Financial rationale and value creation

A strong case shows:
- Diverse benefit vectors mapped: savings, efficiency, risk reduction — not a single number
- **Rigorous calculations of implementation effort, token overhead, and ongoing operational costs** — include compute/token costs, data preparation, governance, and maintenance as explicit line items, not just licence fees
- Mastery over variables and assumptions — state assumptions explicitly and show sensitivity (e.g. payback at conservative vs expected volumes)
- ROI and payback period calculated, with a do-nothing baseline

Weakens when: analysis is generic; ongoing/compute costs are missing; benefits are overstated without assumptions shown.

## Quality and clarity of agent design

A strong case shows:
- Highly integrated design tightly mapped to the strategic need stated in the problem definition
- **Exact interaction of goals, data streams, tool APIs, and oversight hooks** — named systems with read/write access levels
- HITL gates at exact thresholds (financial amounts, confidence scores, risk categories) — not vague "human review where needed"
- A workflow diagram: trigger → nodes → decision logic → escalation gates → outputs
- Critical evaluation of constraints and deployment realities (data quality, legacy API limitations, latency)

Weakens when: triggers, permissions, decision nodes, or oversight hooks are absent; choices are generic or disconnected from the problem.

## Risk, governance, and responsible deployment

A strong case shows:
- Deep insight into systemic, ethical, legal, and security threats — including **instruction injection**, plus the relevant subset of: goal hijacking, memory poisoning, tool orchestration abuse, errors at scale, accountability gaps
- **Proportionate, practical, integrated controls**: technical guardrails, audit logging, and emergency kill switches explicitly
- Sandbox testing protocol named (shadow mode / digital twin / red-teaming) and matched to the agent's privilege level
- Controls mapped one-to-one against the identified risks (a risk → mitigation table works well)

Weakens when: risks are generic; mitigations are not mapped to the agent's actual capabilities; kill switch/logging absent.

## Strategic communication and coherence

A strong case shows:
- Dense yet clear and concise — slide text in short statements, not paragraphs
- High-impact visual design: diagrams and frameworks rendered visually, not described in prose
- **Seamless strategic narrative** — each section references and reinforces the previous (the design solves the stated problem; the risks map to the design; the financials price the design)
- 8–12 slides; consistent heading style; executive register

Weakens when: sections are disconnected; content is descriptive rather than persuasive; walls of text.

## Realism, feasibility, and judgement

A strong case shows:
- **Strategic restraint demonstrated explicitly** — name at least one thing deliberately NOT automated or deferred (e.g. red-zone tasks kept human, phase-2 scope excluded from v1)
- Internal constraints acknowledged: data quality, personnel readiness, organisational change capacity
- An architecture the enterprise can realistically sustain — staffing for monitoring, maintenance budget, named owner
- Phased rollout rather than big-bang deployment

Weakens when: overly optimistic about implementation friction; disconnected from organisational readiness; speculative capabilities assumed.

## Cross-cutting quality signals

- Frameworks applied **visibly and by name** (viability checklist scored, PROFIT stages labelled, matrix quadrant stated)
- Numbers carry stated assumptions
- One consistent currency throughout (default USD; convert and note rate if source figures differ)
- Every key question the case should answer is addressed somewhere in the deck — no obvious gap left open
