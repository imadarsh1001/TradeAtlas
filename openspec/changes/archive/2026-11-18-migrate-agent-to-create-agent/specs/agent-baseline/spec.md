# Spec Delta: agent-baseline

## MODIFIED Requirements

### Requirement: Single agent over the evidence-card tools
The system SHALL provide one agent that answers natural-language questions using exactly the seven evidence-card tools (daily mandi prices, benchmark hub summary, spot weekly prices, macro supply balance, delivered cost, price anomalies, series coverage), and the agent's tool set SHALL stay in parity with the MCP server's tool surface (same tool names and argument names). The agent SHALL be constructed with the framework's current recommended API (`langchain.agents.create_agent`) — not a deprecated constructor — and the migration SHALL be gated on the committed trace set replaying to identical tool-call sequences and validated answers, so framework modernization never changes measured behaviour.

#### Scenario: Tool-set parity with the MCP server
- **WHEN** the agent's bound tool set is enumerated
- **THEN** it contains exactly the seven evidence-card tools with the same names and argument names the MCP server exposes for them

#### Scenario: Answer is produced from tool evidence
- **WHEN** the agent answers a question whose evidence requires tool data
- **THEN** the answer's figures trace to envelopes returned by tool calls made during that run

#### Scenario: Framework migration preserves measured behaviour
- **WHEN** the committed 25-case trace set is replayed through the migrated agent
- **THEN** every case produces the same evidence-tool-call sequence (the framework's structured-output tool call excepted) and the same validated pass/fail outcome as recorded, and no case's outcome changes because of the migration
