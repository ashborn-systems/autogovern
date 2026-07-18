# Governance artefacts — templates

Templates for every document the build mode produces. Fill each with the user's real inputs. Keep one currency throughout, derive any figures from a single calculation block, and write in the analyst register defined in SKILL.md (no em-dashes, no inflation). The authoritative definitions for every control and risk vector are in `governance-frameworks.md` (a sibling file in this directory).

## 1. Central agent register entry

| Field | Value |
|---|---|
| Agent ID | |
| Name | |
| Purpose | |
| Owner (named individual) | |
| Sponsor / accountable executive | |
| Authorised datasets | |
| Authorised tools and APIs | |
| Permission scope (read / write per system) | |
| Autonomy level (in-the-loop / on-the-loop) | |
| Oversight responsibilities | |
| Status (in design / testing / live / decommissioned) | |
| Date entered / last reviewed / next review | |

## 2. Risk to control mapping

Map every applicable risk one-to-one to a named control. Always include the four mandatory controls: audit logging, kill switch and rollback, the sandbox protocol matched to privilege, and the AI transparency disclosure.

| Risk (named vector) | Likelihood | Impact | Control (named mechanism) | Owner |
|---|---|---|---|---|
| Indirect instruction injection via ingested content | | | Input sanitisation; perception-layer injection testing in sandbox | |
| Errors at scale (machine-speed propagation) | | | Rate limiting; boundary-violation monitoring; kill switch | |
| Accountability gap | | | Central register; named owner; immutable audit logging | |
| Data access and security | | | Principle of Least Privilege across all integrations | |
| Autonomy and loss of control | | | HITL gate at [exact threshold]; graceful failure degradation | |
| Real-world operational impact | | | Approval gate before irreversible actions; never-execute list | |

Add a row for every risk vector that applies to this agent. Leave no mandatory control unmapped.

## 3. Agent / model card

- **Operational mandate** — the agent's role and immutable priorities
- **Authorised actions** — what it is designed to execute
- **Prohibited actions** — the never-execute list
- **Target audience** — intended users, departments, or workflows
- **Data pipelines** — ingestion schema and required formatting; execution outputs
- **Tool and model inventory** — every external API, database, SaaS platform, and foundation model relied upon
- **Testing summary** — conditions tested, validation dimensions, metrics achieved (tool-call reliability, boundary-violation rate, step efficiency, sub-goal completion, Pass@k)
- **Known limitations** — edge cases where logic degrades; known hallucination vectors
- **Security and ethical implications** — data privacy and fairness considerations
- **Appropriate operational contexts** — where the agent may and may not be used

## 4. Deployment blueprint

### Technical controls

- PoLP enforced across all integrations
- Sandbox with synthetic data before any live access
- Red-teaming and adversarial crescendo testing complete
- Immutable activity logging from day one
- Kill switch and rollback documented and tested

### Procedural controls

- HITL escalation pathways with explicit financial and operational thresholds
- Approval gates for high-risk or high-value actions
- Central register entry complete
- Golden dataset established for regression testing on every model or prompt update
- Shadow-mode or digital-twin validation complete before release

### Organisational accountability

- Named owner, legally and operationally accountable
- Documented incident-response plan
- Lifecycle schedule — red-team cadence, model-update protocol, decommissioning criteria
- Regulatory and compliance mapping, including a deployment-liability assessment

### Ethical and operational principles

- AI transparency disclosure to all users
- Fairness and non-discrimination monitoring with explicit scope constraints
- Documented uncertainty handling (halt versus extrapolate)
- Defined human-deference criteria

## 5. Monitoring and incident-response plan

- **Live dashboard scope** — active agents, tools in use, datasets accessed, decisions made
- **Escalation alerts** — the conditions that trigger an alert (sensitive content, anomalous access, boundary violation) and who receives it
- **Named overseer** — the operator who receives alerts and can intervene
- **Incident-response chain** — who identifies anomalies, who escalates, who authorises deactivation, and how the kill switch and rollback are invoked
- **Post-incident review** — how findings feed back into controls and the register

## 6. Pre-deployment checklist

| # | Check | Status | Evidence |
|---|---|---|---|
| 1 | Problem clearly identified and refined | | |
| 2 | Agent shown more appropriate than simpler tools, redesign, or human alternatives | | |
| 3 | Benefits evaluated against financial, operational, governance, and maintenance costs | | |
| 4 | Goals, scope, permissions, and escalation pathways defined | | |
| 5 | Governance, compliance, accountability, and ownership requirements identified | | |
| 6 | Tested against baseline, edge cases, and failure states in a secure environment | | |
| 7 | Monitoring, human oversight, and rollback procedures established | | |
| 8 | Deployment blueprint covering governance, monitoring, and operation across the lifecycle | | |
