# Spec Delta: golden-evals

## MODIFIED Requirements

### Requirement: Agent evidence-fidelity scoring
`agent-evidence-fidelity` cases SHALL be scored from the run record: the case passes when every answer figure's source tool names a tool executed in that run and its selector AGREES with that tool call's schema-canonical arguments — on every argument the call meaningfully set, the figure's selector states the same value; record-level extra keys the model cites from the envelope's records (market, variety, grade) are permitted, a contradicted value is not — and each expected figure value equals the case's checked-in expectation rounded to 2 decimals, and every expected summary signal is satisfied: a signal given as a string SHALL appear (case-insensitive) in the answer's summary, and a signal given as a list of alternative substrings SHALL be satisfied when ANY one alternative appears.

#### Scenario: A figure traced to an uninvoked tool fails fidelity
- **WHEN** an agent answer cites a figure whose selector does not match any executed tool call in canonical form
- **THEN** the case fails and the results file records the offending figure

#### Scenario: A drifted value fails fidelity against the checked-in expectation
- **WHEN** the underlying computation's output changes and the answer's figure no longer equals the case's checked-in expectation
- **THEN** the case fails, recording both values

#### Scenario: A spelling variant satisfies an any-of signal
- **WHEN** a case's summary signal is a list of alternatives (for example `["quintal","qtl"]`) and the answer's summary contains any one of them
- **THEN** the signal is satisfied; an answer containing none of the alternatives fails it

### Requirement: Live benchmark mode
In live benchmark mode the runner SHALL run the real agent per case — model id resolved from `TRADEATLAS_AGENT_MODEL` through the model registry (enabled entries only) and routed through Cloudflare AI Gateway per the `llm-model-registry` capability, data strictly hermetic (pinned extracts, committed fixtures, run-local cache; no network in the data layer) — writing one run record per attempt (transport retries write additional records; results reference the final attempt), one exported trace per completed case, and naming the model id on every record. CI SHALL NOT run live benchmark mode. The runner SHALL pace live cases apart (at least the configured inter-case delay, and never faster than the entry's RPM limit allows), SHALL apply the transport-failure policy (bounded retries, then skip-and-continue), and SHALL skip — with explicit classification in the results, never silently — any case whose projected model requests would exceed the entry's daily cap. Each live case SHALL append one line to the run ledger (persona, case id, model, outcome classification, wall duration, model touches, token usage) so successive runs can compare models on evidence, and the runner SHALL expose a per-model summary of that ledger on demand, with pass rates reported over executed runs only and accompanied by a bootstrap 95% confidence interval and a Wilson score interval so small-sample comparisons are honest about their uncertainty.

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
- **THEN** each model is summarized from the run ledger (runs, pass rate with 95% confidence bounds, average duration, average model touches, transport-failure count) so the drop decision is made on recorded evidence with its uncertainty stated

## ADDED Requirements

### Requirement: Trajectory invariants on agent calls
Every agent case SHALL additionally be scored on deterministic trajectory properties derived from the run record. The duplicate-call invariant: a run that executes two successful calls with the same tool name and identical schema-canonical arguments SHALL fail the case. When the case rubric pins `expected_calls`, each pinned call SHALL be satisfied by an executed successful call under the agreement rule in its scenario.

#### Scenario: A wasteful duplicate call fails the case
- **WHEN** a run executes the same tool twice with identical schema-canonical arguments and both calls succeed
- **THEN** the case fails naming the duplicated call

#### Scenario: A rejected attempt followed by a corrected call is not a violation
- **WHEN** a run's first call fails schema validation and the corrected call succeeds with different canonical arguments
- **THEN** the duplicate-call invariant holds and the case is not failed for it

#### Scenario: A pinned expected call is enforced
- **WHEN** a case pins an expected call that the run never executed successfully
- **THEN** the case fails naming the missing call

#### Scenario: A pinned call with extra executed arguments still matches
- **WHEN** a case pins a call's meaningful arguments and the executed call set additional optional arguments without contradicting the pin
- **THEN** the pinned call is satisfied

### Requirement: Efficiency budgets are recorded, not enforced
When a case rubric pins `efficiency_budget`, the run's model-touch count SHALL be recorded against it and reported — but SHALL NOT affect pass/fail until calibrated against campaign data by a future reviewed change.

#### Scenario: Efficiency budget is recorded, not enforced
- **WHEN** a case pins an efficiency budget and the run's model touches exceed it before calibration
- **THEN** the results record the exceedance and the calibration marker, and the case's pass/fail is unaffected

### Requirement: Judged quality layer (non-gating)
A judged quality layer SHALL score live-run evidence with a pytest-integrated evaluation framework (summary relevance and answer-vs-evidence faithfulness initially), SHALL run only on live evidence (never in CI or replay), SHALL record judged scores separately with the deterministic-outcome pairing preserved, and SHALL NEVER change any gate pass/fail. Judge LLMs SHALL resolve through the model registry via a dedicated selector.

#### Scenario: Judged scores never flip a gate
- **WHEN** the quality layer scores a case whose deterministic outcome failed (or returns arbitrarily poor judged scores for a passing case)
- **THEN** the deterministic results file is byte-identical to what it would be without the layer, and the judged scores live only in the quality output

#### Scenario: Judges run through the registry
- **WHEN** the quality layer resolves its judge model
- **THEN** the selector must name an enabled registry entry (gateway-routed), and an unknown or disabled selector fails with a named error

#### Scenario: The layer never runs in CI
- **WHEN** replay verification or the pytest suite executes
- **THEN** no judge model is constructed and no judged metric is invoked
