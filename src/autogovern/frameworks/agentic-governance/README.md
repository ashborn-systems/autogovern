# agentic-governance

An Agent Skill that builds and then continuously runs a governance programme for an agentic AI project. It has a build mode that produces the full governance documentation set, and a run mode that executes a repeatable ongoing-governance loop designed to be invoked indefinitely so a live agent stays governed over its entire lifetime.

It runs alongside a companion business-case skill (`agentic-business-case`): that skill plans the agent, this one governs it. It does not require the business-case skill to be present.

## When to use it

Use it whenever someone wants to govern, control, oversee, audit, or document an AI agent, produce a deployment blueprint or risk assessment, set up oversight and controls, or keep an agent compliant over time.

## What it produces

**Build mode** — a central agent register entry, a risk-to-control mapping, an agent/model card, a deployment blueprint, a monitoring and incident-response plan, and a completed pre-deployment checklist.

**Run mode** — a recorded governance review on each invocation: monitoring and audit-log review, regression testing on change, periodic first-principles re-assessment, red-team cadence checks, version and change control, regulatory-change watch, and decommissioning when criteria are met.

## How to invoke it

This is an Agent Skill. Place the directory where your agent runtime discovers skills, then ask the agent to build a governance plan for your agent, or to run a governance review. The agent reads `SKILL.md` and follows it. The skill is self-contained: everything it needs is in this directory.

## Files

| Path | Purpose |
|---|---|
| `SKILL.md` | The instructions the agent follows: build mode and run mode |
| `references/governance-frameworks.md` | The knowledge base and source of truth: every control, risk vector, testing method, metric, and regulatory principle, with citations |
| `references/governance-artefacts.md` | Templates for every documentation artefact build mode produces |
| `references/ongoing-governance-runbook.md` | The perpetual-operation loop: what to check, on what cadence, and how to record it |
| `references/formatting.md` | Output production rules (currency, single calculation block, prose style, user edits) |

## Writing style

Output follows a risk-officer register, not a marketing one. The skill bans em-dashes, contrastive negation, rhetorical triplets, significance inflation (crucial, robust, seamless, transformative, leverage, delve, landscape, journey, empower, and similar), copula avoidance (serves as, stands as), and meta-signposting (It's worth noting, Importantly, Notably). The test: a reader should hear a risk officer, not a language model.

## Frameworks used

Every framework the skill applies, with a short description and its source. Full definitions are in `references/governance-frameworks.md`.

| Framework | Description | Source |
|---|---|---|
| Governance lifecycle (five steps) | Establish ownership and oversight, define scope and boundaries, test before deployment, monitor continuously, prepare for failure (kill switch and rollback) | Oxford Saïd programme |
| Six governance risk vectors | Autonomy and loss of control, real-world operational impact, complexity and reduced transparency, accountability and ownership, data access and security, errors at scale | Oxford Saïd programme |
| Four red-team attack vectors | Goal hijacking, tool orchestration abuse, memory poisoning, indirect instruction injection | Oxford Saïd programme |
| Three layers of autonomy | Test perception, reasoning, and action independently | Oxford Saïd programme |
| Testing methodologies | LLM-as-a-judge, adversarial crescendo testing, golden datasets | Oxford Saïd programme |
| Five governance metrics | Tool-call reliability, boundary-violation rate, step efficiency, sub-goal completion, Pass@k | Oxford Saïd programme |
| Simulation environments | Shadow mode, digital twin, meta-testing (agent-vs-agent), with rigour proportional to privilege | Oxford Saïd programme |
| First-principles risk assessment | Four questions on the operational limit, failure vectors, quantified consequence at scale, and oversight adequacy, plus the proportionality rule | Hacker and Holweg (2026); programme material |
| Regulatory landscape and deployment liability | Existing law applies in full (GDPR, CCPA, IP, product liability, sector rules); the EU AI Act sets the template; liability shifts to the deployer once a model is integrated | EU AI Act; Hacker and Holweg (2026) |
| Accountability and ownership | A named human owner for every autonomous system; explicit accountability chains; AI must not police itself | Oxford Saïd programme |
| MCP and A2A | Model Context Protocol (agent-to-tool) and Agent-to-Agent coordination, and their effect on the governance and audit surface | Anthropic (MCP); programme material (A2A) |
| Pre-deployment checklist | An eight-point final verification before an agent is built or deployed | Oxford Saïd programme |

## References

- Anthropic — Schluntz, E. and Zhang, B. (2024) 'Building effective agents'.
- Hacker, P. and Holweg, M. (2026) 'A pragmatic approach to regulating AI agents'.
- IAPS — 'AI Agent Governance: a field guide'.
- ICO — 'ICO Tech Futures: Agentic AI'.
- NCSC — 'Thinking carefully before adopting agentic AI'.
- Sapkota, R., Roumeliotis, K. I. and Karkee, M. (2025) 'AI agents vs. agentic AI: a conceptual taxonomy, applications and challenges', _Information Fusion_, 126.
- Yao, S. et al. (2023) 'ReAct: Synergizing Reasoning and Acting in Language Models'.
- EU AI Act — transparency, risk-based oversight, and disclosure obligations (Article 13).
- AIUC-1 — the standard for AI agent security, safety, and reliability.

## Attribution

Frameworks are drawn from the Oxford Saïd Generative and Agentic AI programme (Academic Directors: Professors Matthias Holweg and Michael Wooldridge) and the sources listed above. All instructional content is generic and applies to any enterprise.
