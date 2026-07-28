# Analysis Client Boundary

The worker uses a two-stage model cascade:

- filter model: `OPENAI_FILTER_MODEL`, default `gpt-5-nano`
- analysis model: `OPENAI_ANALYSIS_MODEL`, default `gpt-5-mini`

Escalation model configuration remains available as `OPENAI_ESCALATION_MODEL`
for later high-uncertainty routing.

## Production Client

`OpenAIJsonClassificationClient` is the production client. `worker-service`
constructs it only after startup validation confirms `OPENAI_API_KEY` exists.

The client returns structured JSON that is parsed into `EventClassification`.
Malformed model output fails the job instead of inventing a classification.

## Replay Client

`ReplayClassificationClient` is the deterministic fixture client for tests and
scenario runs. It maps model names to ordered fixture responses and records every
call, so tests can prove which model path was used.

Use it for:

- relevant trigger replay
- irrelevant event replay
- reinforcement replay
- contradiction replay
- malformed model-output replay

Replay fixtures keep paper-trading scenarios deterministic while preserving the
same worker path used by the real client.
