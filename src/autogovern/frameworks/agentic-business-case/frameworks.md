# Frameworks reference — Oxford Saïd Generative and Agentic AI

All frameworks from the programme, condensed for application. Apply them in the order listed — each feeds the next.

## Table of contents

1. AI adoption matrix (architecture selection)
2. Feasibility–desirability matrix (opportunity targeting)
3. 7-point agentic viability checklist (workflow suitability)
4. The rule of ten (value threshold)
5. PROFIT framework (business case)
6. Build-versus-buy framework (sourcing decision)
7. Five-phase agent design (architecture)
8. Hidden costs of deployment (financial realism)
9. Governance lifecycle — 5 steps (operational controls)
10. Six governance risk vectors (risk identification)
11. Three layers of autonomy (testing scope)
12. Testing methodologies and metrics
13. Simulation sandbox environments
14. Regulatory landscape and first-principles risk assessment
15. MCP and A2A (integration protocols)
16. Pre-deployment checklist (final audit)

---

## 1. AI adoption matrix

Maps AI deployments on two axes: task complexity (y) and level of integration/autonomy (x). Four clusters:

| Cluster | Complexity | Integration | Function |
|---|---|---|---|
| Traditional AI | Low — standardised, high-volume | Prediction + human sign-off | Statistical models (regression, decision trees); e.g. loan scoring |
| LLM-based assistants | Low to high | Advisory, human in control | Copilots, RAG, productivity; e.g. CRM-embedded drafting assistant |
| Agentic AI | Moderate — standardised enough to script | Autonomous execution | Multi-step workflow automation; e.g. KYC review agent |
| LLM-augmented judgement | High — bespoke, high-stakes | Advisory with proprietary data | Fine-tuned LLMs/SLMs enhancing expert decisions; e.g. credit memo drafting |

**Use:** justify why the proposed problem sits in the agentic cluster, and name which clusters were rejected and why. Agents suit processes standardised enough to script, repeatable enough to justify overhead, and where execution (not advice) adds the value.

## 2. Feasibility–desirability matrix (Shao et al., 2025)

Two axes: can AI do the task (feasibility)? Does the workforce want it automated (desirability)? Populated through dialogue with the workforce — managers alone build it from expectation, not reality.

| Quadrant | Feasible | Desirable | Strategy |
|---|---|---|---|
| Green zone | Yes | Yes | Immediate automation target |
| Red zone | Yes | No | Avoid automating; consider augmentation instead — automation here triggers resistance |
| Opportunity zone | No | Yes | R&D pipeline; sequence for later |
| Low-priority | No | No | Deprioritise |

Three workforce-as-stakeholder factors shape governance: **performance stakes** (consequences of error), **trust** (workforce confidence in the agent), and **stringency** (regulatory constraints on autonomy).

**Use:** place the proposed workflow in the green zone with evidence, or explain mitigation if near the red zone. Address the "perceived as desirable, trustworthy, useful" question on the strategic justification slide directly with this framework.

## 3. The 7-point agentic viability checklist

Strong candidates satisfy five or more:

1. **Multi-step workflows** — gathering, deciding, acting across stages (single-step → use a prompt)
2. **Information-heavy tasks** — large volumes of text/unstructured data to extract, summarise, categorise
3. **Clear but flexible decision rules** — judgement within recognisable patterns; between deterministic (use traditional automation) and ambiguous (keep human)
4. **High variation in input data and outcomes** — diverse inputs, consistent underlying process
5. **Digital inputs and outputs** — no physical/offline steps blocking end-to-end automation
6. **Access to tools or systems** — CRMs, databases, APIs; without these, the agent only generates text
7. **High volume or repetition** — frequency drives ROI and improvement opportunity

**Use:** score the use case explicitly (e.g. 6/7, naming the miss). Present as a checklist visual or table on the strategic justification slide.

## 4. The rule of ten

Will the AI-enabled task deliver a 10× order-of-magnitude improvement — 10× lower cost, 10× faster execution, or 10× greater capacity? Not absolute, but if the deployment cannot credibly approach this, the complexity overhead rarely justifies it. Anthropic's guidance applies: find the simplest solution possible; agentic systems trade latency and cost for task performance.

**Use:** state which 10× vector the proposal targets and quantify it.

## 5. PROFIT framework

| Stage | Focus |
|---|---|
| **P** — Problem | Define the operational problem before the technology. Scope it, quantify impact (time lost, cost, delays). Never start from "we need an agent" |
| **R** — Research | Internal evidence (process metrics, error rates, workloads) + external (benchmarks, case studies, competitor activity) proving significance |
| **O** — Options | Compare: AI agent, workflow redesign, hiring/training, **do nothing** (the baseline — quantifies cost of inaction) |
| **F** — Financials | Costs: development/licensing, integration, data preparation, ongoing maintenance/monitoring/governance. Benefits: time savings, cost reduction, productivity, outcomes. Calculate ROI and payback period. Include risk costs (delays, failures, compliance, poor adoption). Be realistic — overstating benefits damages credibility |
| **I** — Implementation | Stages: discovery/design → development/procurement → testing/validation → deployment/scaling. Timeline, dependencies, required system access, monitoring, human oversight points |
| **T** — Team and decisions | Project owner, sponsor, task-level responsibility, stakeholders. For agents: explicit accountability for autonomous behaviour |

**Use:** the financial slide must show upfront vs ongoing costs, named benefit vectors, ROI/payback estimate, and an explicit do-nothing comparison. A strong case requires rigorous calculations of implementation effort, token overhead, and ongoing operational costs — include compute/token costs as a line item.

## 6. Build-versus-buy

| Factor | Build | Buy |
|---|---|---|
| Complexity | Bespoke, evolving workflows | Standardised use cases (support, scheduling, KYC) |
| Time | Longer cycles | Faster deployment |
| Data/integration | Deep integration with sensitive/regulated data | Off-the-shelf may lack control |
| Internal capability | Requires AI/engineering/security teams | Lower risk with limited expertise |
| Cost | Higher upfront, lower long-term, more control | Lower upfront, ongoing licensing, vendor dependency |

Most deployments are hybrid: commercial platforms + internal systems + custom integrations. For industry-universal workflows (e.g. KYC), evaluate commercial options first. Buying does not remove governance obligations.

**Use:** state the recommendation and the two or three factors that drove it.

## 7. Five-phase agent design

1. **Operational parameters** — specific outcome, workflow ownership, measurable success threshold (e.g. "autonomously resolve 60% of Tier 1 queries without escalation"); explicit out-of-scope scenarios and escalation triggers; Principle of Least Privilege (PoLP) — minimum access only, sandboxed execution to contain hallucination blast radius
2. **Workflow architecture** — trigger → execution steps → decision points → outputs, plus iteration loops (missing data) and escalation gates (hand back to human). Test: a human operator should be able to follow the map
3. **Ecosystem integration** — data pipelines (user inputs / internal data / external data; each must be accessible, structurally sound, machine-readable — poor data is the most common failure cause); tools and APIs (retrieval/writing, communication/execution); output definition (informational vs systemic action); integration sanity check (API limitations, GDPR/HIPAA constraints, latency)
4. **Platform selection** — no-code/low-code/pro-code; embedded (Microsoft Copilot Studio, Google Vertex/Gemini, AWS Bedrock, OpenAI API, Anthropic Claude) vs standalone (LangChain, n8n, Cursor); sandbox-first experimentation. Default to organisation-approved providers only, and check data residency and where data flows before sending anything to a hosted model — do not assume a public provider is permitted for sensitive data
5. **Governance design** — operational mandate (immutable priorities in the system prompt), uncertainty handling (halt vs extrapolate), never-execute list, HITL gates at exact thresholds, graceful failure degradation (halt, alert, log — never force a destructive action)

**Use:** the system design slide(s) must cover the mandate, the workflow diagram with HITL gates at named thresholds, and the named systems/APIs with access levels (read/write).

## 8. Hidden costs of deployment

The model is rarely the largest cost. Budget for: **data silos and fragmentation** (pipelines often cost more than the agent), **broken process automation** (you cannot automate a broken process), **the edge case penalty** (continuous testing/iteration of probabilistic behaviour), **regulatory and compliance friction** (inflated acceptance testing and timelines). Data preparation, process redesign, governance, testing, integration, and change management typically dominate spend.

## 9. Governance lifecycle — five steps

1. **Establish ownership and oversight** — central agent register: ID, named owner, permissions, authorised datasets, oversight responsibility
2. **Define scope and boundaries** — purpose, prohibited actions, dataset/tool exclusions, bias and fairness constraints, AI transparency disclosure (EU AI Act Article 13)
3. **Test before deployment** — sandbox with synthetic data; baseline + edge cases + no-go-zone verification + adversarial red-teaming; read-and-draft-only privileges during testing
4. **Monitor continuously** — live dashboard (agents, tools, datasets, decisions), real-time escalation alerts, named human overseer
5. **Prepare for failure** — kill switch + documented rollback to the manual process

## 10. Six governance risk vectors

1. **Autonomy and loss of control** — continuous independent action; intervention difficult mid-loop
2. **Real-world operational impact** — hallucination becomes an executed transaction, not a text error
3. **Complexity and reduced transparency** — chained tools and A2A make reasoning opaque; prefer multiple narrow agents over one omni-agent
4. **Accountability and ownership** — who owns an autonomous outcome; trace the failing decision node
5. **Data access and security** — without PoLP, agents are attack surfaces (excessive exposure, unauthorised modification, indirect prompt injection)
6. **Errors at scale** — machine-speed propagation; thousands of corrupted records before human intervention

Plus the four red-team attack vectors: **goal hijacking** (multi-turn drift), **tool orchestration abuse** (synthetic errors triggering privileged calls), **memory poisoning** (malicious content in the RAG knowledge base), **indirect instruction injection** (hidden instructions in ingested content — a named, high-priority risk vector whenever the agent ingests external content).

## 11. Three layers of autonomy (testing scope)

- **Perception** — context adherence (grounding vs hallucination); indirect injection resistance
- **Reasoning** — plan stability, logic loop avoidance, negation handling ("never use tool X")
- **Action** — parameter accuracy in tool calls; excessive agency / scope creep under adversarial pressure

## 12. Testing methodologies and metrics

Methodologies: **LLM-as-a-judge** (teacher model grades decision traces at scale), **adversarial crescendo testing** (10–20 escalating prompts to find multi-turn vulnerabilities), **golden datasets** (50–100 known-trajectory scenarios re-run on every model/prompt update to catch regressions).

Metrics: **tool call reliability** (correct API formatting/execution rate), **boundary violation rate** (attempts to access unapproved tools/data — the key governance metric), **step efficiency** (turns to completion; drift indicator), **sub-goal completion** (where long chains break), **Pass@k** (success probability within k attempts — robustness).

## 13. Simulation sandbox environments

- **Shadow mode** — real production traffic, execution layer decoupled; outbound calls intercepted. Best for pre-deployment benchmarking against real conditions
- **Digital twin** — fully synthetic replica (mock databases, simulated CRM); full read/write to observe unrestricted behaviour
- **Meta-testing (agent-vs-agent)** — attacker agent probes the target with injection and adversarial escalation

Testing rigour proportional to privileges: write-enabled agents need far more validation than read-only.

## 14. Regulatory landscape and first-principles risk assessment

Existing law applies in full: data protection (GDPR/CCPA), IP, cybersecurity and product liability, sector-specific regulation. EU AI Act: GPAI transparency, risk-based oversight; AI disclosure obligation. **Deployment liability principle:** once an organisation integrates/fine-tunes a model into its workflows, liability shifts to the deployer — compliance risk cannot be outsourced to the foundation model provider.

First-principles questions: (1) absolute operational limit if guardrails fail; (2) specific failure/adversarial vectors; (3) quantified consequence of failure at scale; (4) does oversight match risk severity? Autonomy proportional to risk.

## 15. MCP and A2A

- **MCP (Model Context Protocol)** — agent-to-tool. Universal abstraction layer: services documented in natural language; any agent connects without custom integration code
- **A2A (Agent-to-Agent)** — agent-to-agent. Task delegation, plan synchronisation, state tracking, supervisor–worker topologies; agent cards enable discovery

**Use:** in the system design, name whether integrations are MCP-based and whether the architecture is single-agent or supervisor–worker A2A.

## 16. Pre-deployment checklist (final audit)

1. Problem clearly identified and refined?
2. Agent demonstrated more appropriate than simpler tools, process redesign, or human alternatives?
3. Benefits evaluated against financial, operational, governance, and maintenance costs?
4. Goals, scope, permissions, and escalation pathways defined?
5. Governance, compliance, accountability, and ownership requirements identified?
6. Tested against baseline, edge cases, and failure states in a secure environment?
7. Monitoring, human oversight, and rollback procedures established?
8. Deployment blueprint covering governance, monitoring, and operation across the lifecycle?
