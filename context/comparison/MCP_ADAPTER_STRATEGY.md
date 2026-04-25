# FixOps MCP and Adapter Strategy (AD-011 / AD-007)

This document locks **how integrations are chosen and wired** without breaking deterministic controller behavior.

## Non-negotiables

- Controller routing is deterministic and rules-first (AD-002).
- Controller chooses **worker**, not tool.
- Worker chooses tool surface inside its boundary.
- Controller and workers exchange only AD-006 payloads.

## Integration Selection Policy (Deterministic)

For each integration, pick exactly one primary execution mode:

1. **Adapter-first** when:
   - API surface is small and stable.
   - Typed SDK/httpx calls are straightforward.
   - Fastest path to deterministic tests.

2. **MCP-first** when:
   - Tool surface is broad/heterogeneous.
   - Isolation and protocol-standardization are high value.
   - Reuse from existing MCP ecosystems is available.

3. **Hybrid** only when justified:
   - Core path via adapter, optional exploratory tools via MCP.
   - Same worker output contract regardless of path.

## Current Mapping in this repo

- `worker-obs`:
  - **Primary**: adapter-first (`prometheus`, `loki`, `grafana` adapters).
  - **Supplementary**: `mcp-fixops-obs` exists as optional tool surface.
- `worker-k8s`:
  - **Primary**: adapter-first (Kubernetes client adapter).
- `worker-pipeline`, `worker-db`, `worker-app-rca`:
  - Currently AD-006 stubs; integration mode to be chosen during connector implementation.

## Guardrails for all workers

- Keep tool outputs compact before returning AD-006 fields.
- Never return raw secret values.
- Never call another worker directly.
- Respect stage/token/tool budgets from controller request.

## Adoption from reference projects

Adopt:

- MCP/toolset packaging and broad tool discoverability patterns.
- Adapter boundary discipline and integration-specific tests.

Reject:

- Chat-first orchestration replacing controller graph.
- Agent-mesh style worker-to-worker orchestration.

## Implementation checklist per new integration

1. Declare mode: `adapter-first`, `mcp-first`, or `hybrid`.
2. Document reason in service README/config comments.
3. Add unit tests for failure modes and bounded outputs.
4. Ensure AD-006 response stability under partial failures.
5. Add decision-log evidence refs in worker outputs.
