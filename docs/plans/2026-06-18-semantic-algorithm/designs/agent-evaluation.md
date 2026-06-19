# Design: Agent Evaluation Strategy

## Purpose

Provide a strategy-pattern wrapper for agent calls so the evaluation workflow can use a fake agent now and real agents later.

## How it works

The caller uses a stable agent strategy interface. The strategy registry is described as having at least two entries:

- `fake` — documented for the evaluation workflow
- `real` — reserved for future backends

The fake strategy does three things on every request:

1. parses the prompt enough to determine the response shape
2. logs the request and parsed response metadata to disk
3. returns a valid placeholder response that always contains `No detail here`

When the prompt expects structured output, the fake strategy mirrors that shape with placeholder values so downstream validation can keep running.

## How it is used

- Build and review the semantic plan without spending model tokens.
- Exercise request logging and prompt-shape handling before the real agent exists.
- Keep the evaluation path deterministic for tests.

## Design pattern

**Strategy + Null Object + Adapter**

Why it fits:
- Strategy lets the caller swap between fake and real agents
- Null Object gives the fake agent a harmless default behavior
- Adapter keeps the logging / feedback hook separate from future provider details

## Verification targets

- The fake strategy logs requests to disk.
- The fake strategy always emits `No detail here` as the feedback text.
- Structured prompts receive structurally valid placeholder output.
- The real strategy entry exists but remains unimplemented.
