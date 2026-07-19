# Governance frameworks reference

The embedded knowledge base for the agentic-governance skill. Every governance control, risk vector, testing method, metric, and regulatory principle the skill applies is defined here. This file is self-contained — the skill depends on no external document.

Apply these alongside `governance-artefacts.md` (the documentation templates) and `ongoing-governance-runbook.md` (the perpetual-operation loop). Two principles run through all of it: autonomy granted must be proportional to the risk created, and an agent is governed by control, not by capability.

## Table of contents

1. Governance lifecycle — five steps
2. Six governance risk vectors (plus four red-team attack vectors)
3. Three layers of autonomy
4. Testing methodologies
5. Governance metrics
6. Simulation sandbox environments
7. Regulatory landscape and deployment liability
8. First-principles risk assessment
9. Accountability and ownership
10. MCP and A2A
11. Pre-deployment checklist
12. The 7-point agentic viability checklist
13. The rule of ten

---

## 1. Governance lifecycle — five steps

Governance is a capability that spans the entire agent lifecycle, not a stage bolted on after a build. Controls, testing, monitoring, and accountability are built in from the outset.

1. **Establish ownership and oversight** — before the agent is built, enter it in a central register: agent ID, name, purpose, named owner (the individual responsible for its behaviour), authorised datasets and tools, permission scope, and oversight responsibilities.
2. **Define scope and boundaries** — purpose, prohibited actions, accessible datasets and tools with explicit exclusions (for example 'no access to contracts or payroll'), bias and fairness constraints (no profiling on protected characteristics), and the AI transparency disclosure (EU AI Act Article 13 — the agent identifies itself as an AI).
3. **Test before deployment** — sandbox with synthetic data; baseline, edge cases, no-go-zone verification, and adversarial red-teaming. During testing, privileges stay limited to read-and-draft; the agent does not send to real users or write to live systems until testing is complete.
4. **Monitor continuously** — a live dashboard of active agents, tools in use, datasets accessed, and decisions made; real-time escalation alerts on sensitive content or anomalous access; a named human overseer with authority to intervene.
5. **Prepare for failure** — a kill switch (an immediately executable shutdown) and a documented rollback to the manual process.

**Use:** every governed agent has a register entry, a defined scope, a tested sandbox history, a monitoring plan, and a kill switch plus rollback before it goes live.

## 2. Six governance risk vectors

Agentic systems possess agency — they make decisions and act over time — which introduces risk vectors beyond those of a passive model. Identify which apply to the agent under governance.

1. **Autonomy and loss of control** — continuous independent action; real-time intervention mid-loop is difficult.
2. **Real-world operational impact** — a hallucination becomes an executed transaction or a corrupted live database, not a text error.
3. **Complexity and reduced transparency** — chained tools and A2A coordination make reasoning opaque and hard to audit. Prefer several narrowly scoped agents over one complex omni-agent.
4. **Accountability and ownership** — when a multi-agent system errs, tracing the failing decision node and the responsible owner is a legal and operational problem unless accountability chains are set at design time.
5. **Data access and security** — deep API access without the Principle of Least Privilege turns agents into attack surfaces (excessive exposure, unauthorised modification, indirect prompt injection).
6. **Errors at scale** — machine-speed propagation; a minor flaw can corrupt thousands of records before a human intervenes.

### The four red-team attack vectors

Red teaming an agent differs from red teaming a chatbot — the risk surface extends to what the agent can *do*, not only what it *says*. Map the surface first (tool inventory, permission audit, data-pipeline audit), then test the full reasoning, planning, and action loop.

| Attack vector | Mechanism | Target stage | Example |
|---|---|---|---|
| Goal hijacking | Multi-turn gradual drift | Reasoning and planning | Cumulative constraints that mutate a benign task into a malicious one |
| Tool orchestration abuse | Synthetic errors triggering privileged calls | Tool selection and execution | Malformed inputs that trick the agent into invoking an admin-level API |
| Memory poisoning | Modifying the RAG knowledge base | Memory retrieval | A supplier document altered to change wire-transfer routing |
| Indirect instruction injection | Hidden instructions in ingested content | Content ingestion | White-on-white text in a scraped page instructing data exfiltration |

Always test indirect instruction injection if the agent ingests any external content.

## 3. Three layers of autonomy

Because agents perceive, reason, and act, test each layer independently rather than only the final output.

- **Perception** — context adherence (grounding versus hallucination) and resistance to indirect injection.
- **Reasoning** — plan stability across repeated runs, avoidance of unproductive logic loops, and adherence to negative constraints ('never use tool X').
- **Action** — parameter accuracy in tool calls (correct types and syntax) and resistance to excessive agency or scope creep under adversarial pressure.

## 4. Testing methodologies

- **LLM-as-a-judge** — a superior, aligned teacher model grades the student agent's decision traces, auditing its chain of thought and API selections at scale without human review of every interaction.
- **Adversarial crescendo testing** — automated red-team scripts run 10–20 escalating prompts to find vulnerabilities that emerge only after repeated adversarial interaction.
- **Golden datasets** — 50–100 known-trajectory, multi-step scenarios re-run on every model or prompt update to detect logic regressions before deployment.

## 5. Governance metrics

Accuracy alone is insufficient for multi-step systems. Track these across the execution lifecycle.

| Metric | What it measures | Why it matters |
|---|---|---|
| Tool call reliability | Rate of correctly formatted and executed API or tool calls | Enterprise agents depend on external systems; high reliability indicates safe tool use |
| Boundary violation rate | Attempts to access unapproved tools, data, or actions | The key governance metric; a low rate confirms the agent stays in scope |
| Step efficiency | Reasoning steps or turns to completion | Excess indicates inefficiency, cost overrun, or reasoning drift |
| Sub-goal completion | Intermediate objectives completed before a chain fails | Shows where long chains break down |
| Pass@k | Probability of success within k attempts | Robustness across repeated runs, not a single outcome |

## 6. Simulation sandbox environments

Autonomous systems are never tested in live production. Rigour is proportional to privilege — a write-enabled agent needs far more validation than a read-only one.

- **Shadow mode** — real production traffic, execution layer decoupled, outbound calls intercepted and blocked. Best for benchmarking against real conditions and comparing with existing human workflows.
- **Digital twin** — a fully synthetic, isolated replica (mock databases, simulated CRM) with full read/write access for unrestricted observation of behaviour.
- **Meta-testing (agent-vs-agent)** — a dedicated attacker agent probes the target with injection and progressively escalating adversarial interaction to surface latent vulnerabilities.

## 7. Regulatory landscape and deployment liability

Bespoke legislation for autonomous agents is embryonic, but existing law applies in full.

- **Data protection and privacy** — GDPR, CCPA; autonomous ingestion and processing of personal data.
- **Intellectual property** — liability for autonomous content generation and proprietary data scraping.
- **Cybersecurity and product liability** — accountability for systemic breaches or operational damage from algorithmic errors.
- **Sector-specific regulation** — finance, healthcare, aviation, and other regulated industries carry additional mandates.
- **EU AI Act** — transparency obligations, risk-based oversight, and disclosure for general-purpose AI; its principles are the likely template for future agentic rules. Article 13 covers the AI-disclosure obligation.
- **US state-level legislation** — emerging in the absence of federal law; obligations vary by state and can create multi-jurisdictional requirements.

**Deployment liability principle** — once an organisation integrates or fine-tunes a model into its workflows, liability shifts to the deployer. You cannot outsource compliance risk to the foundation model provider.

## 8. First-principles risk assessment

Because agent-specific regulation is still evolving, do not rely solely on external checklists. Ask:

1. What is the absolute operational limit of what this agent could execute if its guardrails fail?
2. What specific technical, logical, or adversarial vectors could cause it to fail?
3. If it fails at scale, what is the quantifiable consequence — financial, legal, reputational, or societal?
4. Does the level of human oversight match the severity of the risk?

**Proportionality rule** — the autonomy granted to a system should be proportional to the risk it creates. As the consequences of failure rise, apply stronger oversight, stricter controls, and more rigorous human-in-the-loop safeguards.

## 9. Accountability and ownership

Every autonomous system has an explicitly designated human owner. This is non-negotiable for any agent with write access, financial execution authority, or access to sensitive data. Without this chain of custody, incident response and auditing are structurally impossible. AI must not police itself: automated testing is necessary at scale but must carry explicit independence safeguards. Governance also defines the agent's full lifecycle — red-team cadence, the conditions for updating its foundation model, and the criteria for safe decommissioning.

## 10. MCP and A2A

Two protocols turn isolated agents into composable infrastructure, and both shape the governance surface.

- **MCP (Model Context Protocol)** — agent-to-tool. A universal abstraction layer that lets any agent connect to a documented service without custom integration code. Governance implication: every MCP-connected service is part of the agent's permission and data-pipeline surface and must be audited.
- **A2A (Agent-to-Agent)** — agent-to-agent. Task delegation, plan synchronisation, and state tracking, frequently in a supervisor–worker topology, with agent cards enabling discovery. Governance implication: A2A compounds complexity and opacity, so accountability chains and the model/agent cards that peers read must be explicit.

## 11. Pre-deployment checklist

An eight-point verification before an agent is built or deployed.

1. Problem clearly identified and refined.
2. An agent shown more appropriate than simpler tools, process redesign, or human alternatives.
3. Benefits evaluated against financial, operational, governance, and maintenance costs.
4. Goals, scope, permissions, and escalation pathways defined.
5. Governance, compliance, accountability, and ownership requirements identified.
6. Tested against baseline, edge cases, and failure states in a secure environment.
7. Monitoring, human oversight, and rollback procedures established.
8. A deployment blueprint defines how the agent is governed, monitored, and operated across its lifecycle.

## 12. The 7-point agentic viability checklist

A strong candidate for agentic automation satisfies five or more of the following. Score the use case explicitly in the system card, naming any miss.

1. **Multi-step workflows** — gathering, deciding, acting across stages (single-step tasks should use a prompt, not an agent).
2. **Information-heavy tasks** — large volumes of text or unstructured data to extract, summarise, categorise.
3. **Clear but flexible decision rules** — judgement within recognisable patterns, between deterministic (use traditional automation) and ambiguous (keep human).
4. **High variation in input data and outcomes** — diverse inputs over a consistent underlying process.
5. **Digital inputs and outputs** — no physical or offline steps blocking end-to-end automation.
6. **Access to tools or systems** — CRMs, databases, APIs. Without these, the agent only generates text.
7. **High volume or repetition** — frequency drives ROI and improvement opportunity.

## 13. The rule of ten

Will the AI-enabled task deliver a 10× order-of-magnitude improvement: 10× lower cost, 10× faster execution, or 10× greater capacity? The threshold is not absolute, but if the deployment cannot credibly approach it, the complexity overhead rarely justifies the agent. Anthropic's guidance applies: find the simplest solution possible, because agentic systems trade latency and cost for task performance. State which 10× vector the deployment targets and quantify it in the system card.

## References

Frameworks and principles are drawn from the Oxford Saïd Generative and Agentic AI programme (Professors Matthias Holweg and Michael Wooldridge, Academic Directors) and the sources below.

- Anthropic — Schluntz, E. and Zhang, B. (2024) 'Building effective agents'. Available at: anthropic.com/engineering/building-effective-agents.
- Hacker, P. and Holweg, M. (2026) 'A pragmatic approach to regulating AI agents'.
- IAPS — 'AI Agent Governance: a field guide'. Available at: iaps.ai/research/ai-agent-governance.
- ICO — 'ICO Tech Futures: Agentic AI'.
- NCSC — 'Thinking carefully before adopting agentic AI'. Available at: ncsc.gov.uk.
- Sapkota, R., Roumeliotis, K. I. and Karkee, M. (2025) 'AI agents vs. agentic AI: a conceptual taxonomy, applications and challenges', Information Fusion, 126, p. 103599.
- Yao, S. et al. (2023) 'ReAct: Synergizing Reasoning and Acting in Language Models', Google Research.
- EU AI Act — transparency, risk-based oversight, and disclosure obligations (Article 13).
- AIUC-1 — the standard for AI agent security, safety, and reliability. Available at: aiuc-1.com.
