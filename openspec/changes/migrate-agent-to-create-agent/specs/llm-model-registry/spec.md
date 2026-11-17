# Spec Delta: llm-model-registry

## MODIFIED Requirements

### Requirement: Google route support in the agent path
Google-provider entries (AI Studio and Vertex routes through the gateway) SHALL be constructible for agent runs, participating in the same structured-output contract as the OpenAI-compatible path — under the current framework the structured answer is delivered via the structured-output tool strategy (the answer schema expressed as a tool call), and the model output is validated client-side against the answer schema at extraction, so an unvalidated answer is never emitted. A Google entry SHALL NOT be selectable until a successful live smoke test has been recorded for it.

#### Scenario: Google structured output validates client-side
- **WHEN** an agent run on a Google entry produces output that does not conform to the answer schema
- **THEN** the run fails with the validation error and emits no answer

#### Scenario: Unproved Google entries stay disabled
- **WHEN** a Google entry has not passed a recorded live smoke test
- **THEN** the entry is disabled in the registry and selecting it fails naming the entry
