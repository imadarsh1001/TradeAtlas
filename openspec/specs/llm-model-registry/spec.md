# llm-model-registry Specification

## Purpose
All live LLM traffic is governed by a versioned model registry and routed through Cloudflare AI Gateway: which models may be used (enabled flags), how they are reached (routes, BYOK vs explicit keys), how they are called (per-entry parameters, timeouts, RPM limits, daily caps), and what happens when a provider misbehaves (bounded retries, then skip-and-continue) — so model choice is a reviewed configuration decision, not an implicit environment default.

## Requirements

### Requirement: Registry-governed model resolution
The system SHALL resolve every live chat-model selection through a checked-in model registry. A selector (registry key or raw model id) SHALL match at most one entry; a disabled entry SHALL be rejected with an error naming the entry and its notes; an unknown selector SHALL be rejected with an error naming the enabled alternatives.

#### Scenario: Disabled entry is rejected with its reason
- **WHEN** a live run selects a model whose registry entry is disabled
- **THEN** the run fails with an error naming the entry key, the model id, and the entry's notes (the documented reason it is off)

#### Scenario: Unknown selector names the alternatives
- **WHEN** a live run names a model id or key absent from the registry
- **THEN** the run fails with an error listing the enabled registry keys

#### Scenario: Resolution by key or model id
- **WHEN** the selector equals a registry key (e.g. `groq`) or a registry model id (e.g. `qwen/qwen3.8-27b`)
- **THEN** both resolve to the same entry, and every record and trace continues to name the raw model id

### Requirement: Gateway routing is mandatory for live models
Every live chat model SHALL be constructed against the Cloudflare AI Gateway URL derived from configured account and gateway identifiers, sending the gateway authorization header; the system SHALL NOT fall back to a direct provider endpoint. Gateway credentials SHALL be read from the environment (with the repo `.env` loaded) and their absence SHALL fail with a named error before any case runs. Authentication follows the entry's mode per the scenarios below.

#### Scenario: Gateway credentials absent fails fast
- **WHEN** a live run starts without the gateway account/gateway/authorization configuration present
- **THEN** it fails with a clear error naming the missing variable, before any case executes

#### Scenario: BYOK sends no provider key
- **WHEN** a model is built for a BYOK entry
- **THEN** requests carry the gateway authorization header and no provider `Authorization` header (the gateway injects the stored key)

#### Scenario: Non-BYOK resolves the named provider key
- **WHEN** a model is built for a non-BYOK entry
- **THEN** the provider key comes from the entry's named environment variable, and an unresolvable key fails with an error naming that variable (a gateway token is never sent as a provider key)

### Requirement: Entry parameters are honored verbatim
A live model SHALL be constructed with its entry's parameters applied exactly as written in the registry. Its request timeout SHALL come from the entry when set, falling back to the system default (300 seconds) when unset; retries stay bounded at the system constant.

#### Scenario: Entry params reach the built model
- **WHEN** a live model is built from an entry declaring specific call parameters
- **THEN** the constructed model carries those parameters and the entry's timeout (or the default when unset)

#### Scenario: Slow models are declared, not tuned around
- **WHEN** an entry documents high provider latency in its notes
- **THEN** its timeout lives in the entry (so enabling it is a one-line registry change), and the default timeout applies only to entries without one

### Requirement: Google route support in the agent path
Google-provider entries (AI Studio and Vertex routes through the gateway) SHALL be constructible for agent runs, sending the same structured-output contract as the OpenAI-compatible path: the answer JSON schema sent non-strictly and the model output validated client-side against the answer schema, so an unvalidated answer is never emitted. A Google entry SHALL NOT be selectable until a successful live smoke test has been recorded for it.

#### Scenario: Google structured output validates client-side
- **WHEN** an agent run on a Google entry produces output that does not conform to the answer schema
- **THEN** the run fails with the validation error and emits no answer

#### Scenario: Unproved Google entries stay disabled
- **WHEN** a Google entry has not passed a recorded live smoke test
- **THEN** the entry is disabled in the registry and selecting it fails naming the entry

### Requirement: Transport-failure policy for live suites
During a live suite run, a case failing with a transport-class error SHALL be retried with backoff up to three attempts; if all attempts fail, the case SHALL be classified `provider-unavailable` (retryable, resumable by case ids) and the suite SHALL continue with the remaining cases. Genuine model failures SHALL NOT be retried and remain recorded as failed. No classification SHALL silently drop a case.

#### Scenario: Transient rate limit is retried then skipped
- **WHEN** a case's provider keeps returning rate-limit responses across three attempts
- **THEN** the case is marked provider-unavailable and retryable, and the next case runs

#### Scenario: One flaky provider never kills the session
- **WHEN** a provider becomes unresponsive mid-suite
- **THEN** the remaining cases are attempted under the same policy, and the results file records every skipped case with its classification

#### Scenario: Misbehaviour is not retried
- **WHEN** a case's run fails with a model-behaviour failure (for example the answer schema never validates)
- **THEN** the case is recorded as failed without transport retries
