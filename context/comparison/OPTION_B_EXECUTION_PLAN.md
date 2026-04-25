# FixOps Option B Execution Plan (Gap Closure)

This file is the operational checklist for continuing implementation without losing track.
It is derived from:

- `.cursor/rules/fixops-agentic-northstar.mdc`
- `context/comparison/GOAL.md`
- `context/comparison/DECISIONS.md`
- references under `context/exampleProjects/`

## Scope Guardrails

- Keep controller and workers as separate HTTP services.
- Keep two ingress endpoints:
  - strict normalized: `POST /v1/investigations/run`
  - planner-backed flexible: `POST /v1/investigations/run-planned`
- Keep rules-first routing (LLM extracts entity only, never chooses worker).
- Keep AD-006 compact worker contract between services.

## B1: Example Projects Mapping (Adopt / Reject)

### Adopt

- MCP/toolset breadth patterns (HolmesGPT/IncidentFox) behind FixOps interfaces.
- Adapter boundary discipline for infrastructure access and testability.
- Integration fixture strategy for real-world observability edge-cases (labels, partial data, time windows).
- Credential isolation patterns where secrets stay outside orchestration prompts.
- Better operational docs style for "how to run and validate" each integration path.

### Reject

- Chat-first orchestration as the primary control plane.
- Agent mesh / skill-orchestrator architecture replacing controller-owned orchestration.
- Product-level multi-tenant control-plane topology from reference repos.

### Why

- AD-011 allows MCP and adapters; references are for tooling harvest.
- AD-001/AD-002/AD-014 require controller-owned deterministic orchestration.

## B2: Locked Priority Order

### P0 (Correctness/Safety first)

1. Enforce staged budget behavior (AD-005): explicit stage progression and caps.
2. Make confidence gates drive deterministic next step decisions (AD-008).
3. Ensure decision log captures key controller transitions and HIL actions.
4. Add/adjust tests to lock P0 behavior.

### P1 (Architecture completeness)

5. Add missing domain worker stubs + routing + tests:
   - `worker-pipeline`
   - `worker-db`
   - `worker-app-rca`
6. Harden worker-owned credentials with pluggable backends (AD-012).

### P2 (Knowledge and tool strategy hardening)

7. Implement bounded institutional retrieval in RCA path (AD-009).
8. Expand MCP/adapters strategy and document deterministic usage policy (AD-011/AD-007).
9. Run end-to-end acceptance matrix and publish final closure report.

## Working Rule (Do Not Lose Track)

If ad-hoc testing interrupts implementation:

1. Record test result.
2. Map it to impacted item(s) in this plan.
3. Resume from the next unchecked item in locked order.

