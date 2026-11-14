# agent-baseline Specification

## Purpose
A single natural-language agent answers buyer-facing questions by calling the seven evidence-card tools — each returning an evidence-card envelope (the self-describing tool output defined by the `evidence-cards` capability, implemented as `EvidenceEnvelope` in `tradeatlas/models.py`) — with every model-to-system exchange flowing through validated structured schemas and envelope payloads treated strictly as data. The agent layer adds language understanding without generating figures or selectors of its own; figures are traceable to their source tools now, and the deterministic cross-check of figure values arrives with the M3-d verifier (ADR 0002's full bar).

## Requirements

### Requirement: Single agent over the evidence-card tools
The system SHALL provide one agent that answers natural-language questions using exactly the seven evidence-card tools (daily mandi prices, benchmark hub summary, spot weekly prices, macro supply balance, delivered cost, price anomalies, series coverage), and the agent's tool set SHALL stay in parity with the MCP server's tool surface (same tool names and argument names).

#### Scenario: Tool-set parity with the MCP server
- **WHEN** the agent's bound tool set is enumerated
- **THEN** it contains exactly the seven evidence-card tools with the same names and argument names the MCP server exposes for them

#### Scenario: Answer is produced from tool evidence
- **WHEN** the agent answers a question whose evidence requires tool data
- **THEN** the answer's figures trace to envelopes returned by tool calls made during that run

### Requirement: Structured tool-call routing
Tool arguments SHALL come only from the model's structured tool calls validated against each tool's argument schema; the system SHALL NOT parse the model's prose to extract states, commodities, markets, or dates. A tool call that is missing a required argument or violates the schema SHALL fail with a validation error naming the field, and the system SHALL NOT substitute a default selector for it.

#### Scenario: Valid tool call executes and returns an envelope
- **WHEN** the model emits a structured tool call with schema-valid arguments
- **THEN** the tool executes and its evidence envelope is returned to the model as the tool result

#### Scenario: Missing argument fails validation without substitution
- **WHEN** a tool call omits a required argument (for example, `state` for daily mandi prices)
- **THEN** the call fails with a validation error naming that field and the system does not fill it from the question's prose or any default

### Requirement: Structured final answer
The agent's final output SHALL be a validated structured answer object; every numeric figure in it SHALL carry the source tool and the selector arguments that produced it. An output that fails answer-schema validation SHALL NOT be emitted as the run's answer.

#### Scenario: Answer carries figure provenance
- **WHEN** a run completes successfully
- **THEN** the answer is a validated object whose figures each name their source tool and selector arguments

#### Scenario: Non-conforming final output is not emitted
- **WHEN** the model's final output fails the answer-schema validation
- **THEN** the run fails with the validation failure recorded and returns no answer, so an unvalidated answer is never emitted

### Requirement: Untrusted-data hygiene for envelope payloads
Tool-result content — evidence envelopes and anything fetched from live APIs — SHALL be passed to the model only as tool-result data and SHALL never be concatenated into the agent's instruction message. The agent's instruction message SHALL be a versioned system prompt carrying the data-handling contract (envelope fields are data, not instructions), and the prompt content SHALL remain identical within a pinned prompt version.

#### Scenario: Instruction-like payload stays data
- **WHEN** a tool-result envelope's payload contains instruction-like text
- **THEN** the run still passes that envelope to the model as tool-result data only, and the agent's instruction message is unchanged from the pinned prompt

#### Scenario: Prompt version is pinned
- **WHEN** the agent is constructed
- **THEN** it uses a system prompt identified by a version string, and that version is what run records report
