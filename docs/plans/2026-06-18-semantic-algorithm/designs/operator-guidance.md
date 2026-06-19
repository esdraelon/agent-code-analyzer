# Design: Operator Guidance and Documentation

## Purpose

Explain how the semantic algorithm layer works, how it is refreshed, and how it is queried.

## How it works

This is a runbook, not an algorithm. The documentation should describe the lifecycle in the same order the branch lives through it:

- build the semantic record model
- generate descriptions
- refresh incrementally on file changes
- query the descriptions through MCP
- verify the results

## How it is used

- New implementers can follow the folder without reading the whole codebase.
- Operators can decide when to run a full rebuild.
- Reviewers can compare the docs to the shipped behavior.

## Design pattern

**Runbook / Playbook**

Why it fits:
- documentation should guide action, not merely describe it
- a playbook keeps lifecycle order explicit
- it provides a stable operator contract for the branch

## Verification targets

- The docs match the actual implementation.
- The lifecycle order is obvious.
- The folder can serve as a handoff artifact for future work.
