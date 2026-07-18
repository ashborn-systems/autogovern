# Ongoing governance runbook

The perpetual-operation loop for run mode. It is designed to be invoked repeatedly so a live agent stays governed over its entire lifetime. Run it on a schedule and on triggers (model update, prompt change, tool or permission change, scope change, incident, or regulatory change). The authoritative definitions for the controls, metrics, and risk vectors referenced below are in `governance-frameworks.md` (a sibling file in this directory).

## Cadence

Set intensity proportional to the agent's privilege and risk. A read-only, low-impact agent needs a lighter cadence than a write-enabled, high-value one.

| Activity | Default cadence | Trigger-based |
|---|---|---|
| Monitoring and alert review | Each run (e.g. weekly) | On any escalation alert |
| Audit-log review | Each run | On any boundary violation |
| Golden-dataset regression | On every model, prompt, tool, or permission change | — |
| First-principles re-assessment | Quarterly | On scope, data, or model change |
| Red-team / adversarial testing | Proportional to risk (e.g. quarterly to annually) | On a new attack surface |
| Regulatory-change review | Quarterly | On a known regulatory development |
| Version and change control | Continuous | On any proposed change |
| Decommissioning review | Annually | When decommissioning criteria are met |

## The loop — what each run does

### 1. Monitoring and alerts

Review the dashboard and every escalation alert since the last run. Confirm active agents, tools, and datasets match the register. Investigate anomalous access patterns.

### 2. Audit-log review

Read the immutable log for the period. Check the governance metrics:

- **Boundary violation rate** — any attempt to access unapproved tools, data, or actions; this is the key signal
- **Step efficiency** — rising step counts indicate reasoning drift
- **Tool call reliability** — falling reliability indicates integration or model degradation

### 3. Regression testing

If the model, prompt, tools, or permissions changed since the last run, re-run the golden dataset (50–100 known-trajectory scenarios). Investigate any regression before it reaches production. Block the change if a regression is unresolved.

### 4. First-principles re-assessment

On the periodic schedule, or whenever scope, data, or the model changed, re-answer the four questions: the operational limit if guardrails fail; the failure and adversarial vectors; the quantified consequence at scale; and whether oversight still matches risk. Confirm the risk → control mapping still holds and update it if the agent's surface changed.

### 5. Red-team cadence

Check whether adversarial testing is due. When due, run crescendo testing and, for high-privilege agents, meta-testing (agent-vs-agent) against the four attack vectors. Record results and feed any new vulnerability into the controls.

### 6. Version and change control

No change to a live agent without review and re-testing. Version the agent, its prompts, its tools, and its permissions in the central library. Require sign-off from the named owner before promoting a change.

### 7. Regulatory-change watch

Track changes to GDPR, CCPA, the EU AI Act, sector rules, and relevant state legislation. When the landscape shifts, reassess compliance, the transparency-disclosure obligation, and the deployment-liability position, and update the deployment blueprint.

### 8. Decommissioning

When the decommissioning criteria are met, revoke the agent's access, close its register entry, confirm the manual fallback is operational, and archive its logs for the required retention period.

### 9. Record and schedule

Record findings, actions, and the next review date in the register. A run that finds nothing still records the review. A run that finds an issue opens an action, assigns it to the named owner, and re-tests before closing it.

## Run log template

| Run date | Reviewer | Findings | Actions opened | Owner | Re-test result | Next review |
|---|---|---|---|---|---|---|
| | | | | | | |
