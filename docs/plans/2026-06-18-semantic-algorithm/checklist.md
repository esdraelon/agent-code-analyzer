# Semantic Algorithm Implementation Checklist

Use this as the execution checklist for the milestone branch.

## Steering
- Pull from `origin` and branch from `main` after each remote merge.
- Each milestone gets its own branch.
- Keep **95% new-line coverage** on the changed milestone scope.
- Keep **90% total coverage** for the repository.
- After each milestone, validate MCP with the ORK3 integration snapshot suite (`uv run python scripts/ork3_eval_snapshot.py`).

## Milestone 0 — Agent abstraction and Hermes adapter POC
- [x] Agent request/response contract is normalized
- [x] Wrapper/factory selects the concrete backend
- [x] Fake backend returns `No detail here`
- [x] Fake backend writes trace logs when configured
- [x] Hermes shell adapter exists
- [x] Hermes library adapter exists
- [x] Tests cover the wrapper and both Hermes modes

## Milestone 1 — Semantic record model and stable identities
- [x] Define the canonical semantic record value object
- [x] Confirm scope coverage for package/module/file/class/method/chunk
- [x] Define stable identity derivation rules
- [x] Separate record construction from storage mapping
- [x] Add tests for identity stability and lineage

## Milestone 2 — Semantic writer abstraction with a stub backend
- [x] Define the narrow writer interface
- [x] Implement the deliberate no-response sentinel
- [x] Distinguish sentinel output from transport/runtime failure
- [x] Wire the stub backend into the indexing path
- [x] Add tests for the stub path and failure path

## Milestone 3 — Tree-sitter-aware chunking and scope partitioning
- [ ] Add AST-aware chunk boundary logic
- [ ] Split dense methods at meaningful control-flow regions
- [ ] Preserve parent method lineage for chunks
- [ ] Keep small methods whole when appropriate
- [ ] Add tests for split/no-split behavior

## Milestone 4 — Full-project mass ingestion
- [ ] Walk the project root once and discover semantic scopes
- [ ] Generate descriptions for every supported semantic level
- [ ] Persist descriptions and embeddings through the existing storage layers
- [ ] Make rebuilds idempotent
- [ ] Add tests for duplicate avoidance and stable counts

## Milestone 5 — Piecewise updates from fswatch diffs
- [ ] Batch noisy file-system events into one update window
- [ ] Normalize add/modify/delete/move events
- [ ] Map changed lines back to the owning semantic scope
- [ ] Invalidate and replace affected records only
- [ ] Add tests for edit/delete/move/fallback cases

## Milestone 6 — MCP surface for semantic description indexing
- [ ] Expose a full rebuild command
- [ ] Expose a piecewise refresh command
- [ ] Keep existing search and parse tools intact
- [ ] Document mode selection in the operator prompt
- [ ] Add tests or checks for command registration

## Milestone 7 — Retrieval and quality checks
- [ ] Route architecture questions to high-level summaries
- [ ] Route behavior questions to lower-level summaries
- [ ] Preserve project scoping and lexical fallback
- [ ] Add a repeatable retrieval quality harness
- [ ] Verify ranking usefulness and latency

## Milestone 8 — Documentation and operator guidance
- [ ] Explain semantic descriptions and their scope levels
- [ ] Explain rebuild vs diff refresh usage
- [ ] Explain the stub/fake/real backend split
- [ ] Keep docs synchronized with shipped behavior
- [ ] Move the plan to `docs/complete/` when done

## Branch exit criteria
- [ ] All milestone checklist items are complete or intentionally deferred
- [ ] Tracking ledger reflects the latest milestone state
- [ ] Working tree is clean
- [ ] Branch is pushed to `origin`
