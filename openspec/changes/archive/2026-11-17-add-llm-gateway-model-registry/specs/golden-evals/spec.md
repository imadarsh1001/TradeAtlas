# Spec Delta: golden-evals

## MODIFIED Requirements

### Requirement: Live benchmark mode
In live benchmark mode the runner SHALL run the real agent per case — model id resolved from `TRADEATLAS_AGENT_MODEL` through the model registry (enabled entries only) and routed through Cloudflare AI Gateway per the `llm-model-registry` capability, data strictly hermetic (pinned extracts, committed fixtures, run-local cache; no network in the data layer) — writing one run record per case, one exported trace per completed case, and naming the model id on every record. CI SHALL NOT run live benchmark mode. The runner SHALL pace live cases apart (at least the configured inter-case delay, and never faster than the entry's RPM limit allows), SHALL apply the transport-failure policy (bounded retries, then skip-and-continue), and SHALL skip — with explicit classification in the results, never silently — any case whose projected model requests would exceed the entry's daily cap. Each live case SHALL append one line to the run ledger (persona, case id, model, outcome classification, wall duration, model touches, token usage) so successive runs can compare models on evidence, and the runner SHALL expose a per-model summary of that ledger on demand.

#### Scenario: Live benchmark records every case
- **WHEN** the buyer suite runs in live benchmark mode
- **THEN** each case produces a run record naming the model id, each completed case also produces an exported trace, and the results file records per-case pass/fail with run metadata

#### Scenario: A failing agent run scores as failed
- **WHEN** a case's agent run fails (for example, answer validation never succeeds)
- **THEN** the case is recorded and scored as failed with the failure reason, never silently dropped, and the run record exists

#### Scenario: Rate-limited and daily-capped cases are classified, not dropped
- **WHEN** a case is skipped for provider unavailability after retries, or its projected requests would exceed the entry's daily cap
- **THEN** the results file records the case with the classification (`provider-unavailable` or `daily-cap`) and the run ledger carries the same outcome, so a later run can resume exactly those cases by id

#### Scenario: Live cases are paced apart
- **WHEN** a live suite runs multiple cases against one provider entry
- **THEN** consecutive cases are separated by at least the configured inter-case delay and the entry's RPM-implied minimum interval, and replay mode performs no pacing

#### Scenario: The ledger answers which model to drop
- **WHEN** the per-model summary is requested after runs against multiple providers
- **THEN** each model is summarized from the run ledger (runs, pass rate, average duration, average model touches, transport-failure count) so the drop decision is made on recorded evidence
