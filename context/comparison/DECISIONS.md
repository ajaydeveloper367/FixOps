# Decisions Log — Infinity-Sentinel

> A living record of every meaningful decision made during design and implementation.
> **Why this file exists:** so that future sessions — AI or human — don't re-debate
> settled questions, and so the reasoning behind every choice is preserved, not just
> the choice itself.

---

## How to use this file

When you make a decision during implementation, add an entry here:

```
### ID-XXX · Short title
**Decision**: what was decided (one sentence)
**Why**: the reasoning that made this the right call
**Rejected alternatives**: what was considered and why it lost
**Status**: LOCKED | REVISIT IF <condition> | SUPERSEDED BY ID-XXX
**Date**: YYYY-MM-DD
```

LOCKED = do not re-open without a very good reason.
REVISIT IF = conditions under which this should be reconsidered.
SUPERSEDED = this decision was replaced; see the new entry.

---

## Architecture Decisions (pre-implementation, all LOCKED)

### AD-001 · One controller, many domain workers

**Decision**: A single controller orchestrates all workers. Workers do not call each other.
**Why**: Predictable, auditable, easy to debug. If an investigation goes wrong there
is exactly one place to trace: the controller's decision log. Peer-to-peer worker
communication creates invisible reasoning paths.
**Rejected alternatives**:
- Peer-to-peer worker mesh — workers triggering other workers makes tracing hard
- Fully autonomous worker swarm — unpredictable, untestable, no approval gate
**Status**: LOCKED
**Date**: 2026-04

---

### AD-002 · Routing is rules-first, LLM is only for entity extraction

**Decision**: LLM extracts the entity (name, type, alert class) from the raw alert.
Deterministic rules then decide which worker runs. The LLM does not choose the next
investigation step.
**Why**: LLM routing is non-deterministic, hard to test, and produces different paths
for identical alerts depending on context. Rules can be unit-tested, explained to
stakeholders, and audited in post-mortems.
**Rejected alternatives**:
- Full LLM routing ("ask the model what to check next") — produces valid-sounding
  but untraceable paths; a bad routing decision has no audit trail
- Regex-only entity extraction — too brittle for varied alert formats
**Status**: LOCKED
**Date**: 2026-04

---

### AD-003 · Execution is always human-gated

**Decision**: No remediation executes without explicit human approval.
Flow: suggest → human approves → execute → verify. No exceptions in production.
Auto-remediation is a configurable opt-in for lower environments only.
**Why**: Trust is built incrementally. One autonomous action that causes an outage
destroys months of credibility. The cost of a human approval step is negligible
compared to that risk.
**Rejected alternatives**:
- Auto-execute with notification — rejected; notification is not approval
- Auto-execute for "safe" actions only — rejected; "safe" is context-dependent and
  hard to define reliably at build time
**Status**: LOCKED for prod. Configurable for dev/staging.
**Date**: 2026-04

---

### AD-004 · Two metadata layers: Inventory and Dataflow Graph

**Decision**: Keep two separate metadata structures.
- **Inventory** — routing and access: where is this entity, what cluster, what
  credentials, who owns it, can it be restarted?
- **Dataflow Graph** — ownership and dependency: who produces this data, who
  consumes it, what does it depend on?
**Why**: Mixing routing metadata with dependency graphs produces a single monolithic
config that is unmaintainable at scale. Separating them means: Inventory stays thin
and stable (human-maintained), Graph can be large and auto-derived.
**Rejected alternatives**:
- One flat service config combining all fields — gets unwieldy, harder to auto-derive
- LLM guessing relationships from logs — produces hallucinated dependencies
**Status**: LOCKED
**Date**: 2026-04

---

### AD-005 · Staged context loading (3 stages, hard token limits)

**Decision**: Stage 1 = always run (cheap: alert + inventory + graph). Stage 2 = only
if Stage 1 is inconclusive (logs, metrics, DAG run status). Stage 3 = only if still
unclear (code, configs, runbooks, traces). Hard token and tool-call limits per stage.
**Why**: Loading everything upfront is expensive, slow, and noisy. Most incidents are
resolved at Stage 1 or 2. Stage 3 tool calls (code retrieval, trace fetching) are
expensive and should only happen when necessary.
**Rejected alternatives**:
- Load everything upfront — too expensive per investigation; also degrades LLM
  reasoning quality by burying the signal in noise
- No staged limits — investigations could spin indefinitely on complex edge cases
**Status**: LOCKED
**Date**: 2026-04

---

### AD-006 · Worker output is structured JSON (fixed contract)

**Decision**: Every worker returns exactly:
```json
{
  "checked": ["what was inspected"],
  "findings": ["what was found"],
  "evidence_refs": ["log line IDs, metric timestamps, config keys"],
  "ruled_out": ["what was eliminated and why"],
  "confidence": 0.0,
  "next_suggested_check": "optional hint to controller"
}
```
**Why**: Structured output is testable, parseable, and forces workers to be precise
about what they know vs. what they don't. Freeform output makes the controller
dependent on text parsing, which is brittle.
**Rejected alternatives**:
- Freeform worker text summary — hard to parse, hard to test, hard to chain
- Workers returning raw log/metric dumps — token-expensive and leaks raw infra data
  between agents
**Status**: LOCKED
**Date**: 2026-04

---

### AD-007 · Everything goes through tool adapters

**Decision**: Workers never call infrastructure directly. All K8s, Airflow, Kafka,
Mongo, Prometheus, Loki, GitHub, Confluence calls go through adapter interfaces.
**Why**: Adapters can be mocked for testing (Phase 1 runs entirely on fake data),
swapped for different backends, rate-limited, and audited. Direct infra calls
from workers make the system untestable and hard to port.
**Rejected alternatives**:
- Workers with direct SDK calls — works faster initially but breaks testability
  and makes future swaps expensive
**Status**: LOCKED
**Date**: 2026-04

---

### AD-008 · Confidence scoring gates escalation and conclusion

**Decision**: Each worker produces a confidence score 0.0–1.0.
- ≥ 0.85 → controller concludes, moves to approval gate
- 0.50–0.84 → escalate to next worker or deeper stage
- < 0.50 → flag low confidence, do not present as RCA without more evidence
**Why**: Without a numeric gate, the controller either over-escalates (expensive) or
under-investigates (wrong conclusions). The score makes escalation decisions auditable
and testable.
**Rejected alternatives**:
- LLM decides when to stop — non-deterministic stopping conditions
- Always run all workers — expensive, slow, noisy
**Status**: LOCKED (thresholds are tunable)
**Date**: 2026-04

---

### AD-009 · RAG layer for institutional knowledge

**Decision**: pgvector-backed semantic retrieval over Confluence runbooks, past RCA
reports, service READMEs, DAG docs, and monitoring runbooks. Top-3 chunks
(≈300 tokens) injected into worker context per investigation.
**Update paths**: Confluence webhook → re-embed on page update. GitHub post-merge
hook → re-embed changed READMEs/docstrings. Auto-index on RCA completion.
Weekly full re-index as safety net.
**Why**: Generic LLM knowledge does not know that "dp-service OOM was fixed by
reducing BATCH_SIZE 3 months ago". RAG bridges the gap between what the model
knows generically and what the engineering team has documented specifically.
**Rejected alternatives**:
- Full runbook loading — 3,000+ tokens per runbook vs. ~300 for top-3 chunks;
  burns token budget that should go to observability data
- No RAG at all — loses accumulated institutional knowledge; every investigation
  starts from zero
**Status**: LOCKED (design). Implementation phase: after core investigation flow works.
**Date**: 2026-04

---

### AD-010 · Inventory is YAML in Git, loaded into a queryable DB

**Decision**: Inventory source of truth is YAML files in a Git repo. At runtime,
loaded into Postgres (or Mongo). Validated on every update.
**Why**: Git-versioned inventory means changes are reviewed, auditable, and
rollback-able. Stale inventory is the #1 cause of wrong routing — Git history
makes the problem visible.
**Keep it thin**: Only stable routing metadata per entity. Not every DAG detail.
**Status**: LOCKED
**Date**: 2026-04

---

## Implementation Decisions (add as you go)

### ID-001 · [Template — copy this for each new decision]
**Decision**:
**Why**:
**Rejected alternatives**:
**Status**: LOCKED | REVISIT IF
**Date**: YYYY-MM-DD

---

## Open Questions (resolve before the relevant phase)

| # | Question | Context | Resolve before |
|---|---|---|---|
| OQ-01 | Framework: LangGraph vs custom state machine? | LangGraph fits the controller-worker graph naturally but adds a dependency and learning curve. Custom state machine is more portable. | Phase 1 code start |
| OQ-02 | Workers as graph nodes, services, or MCP servers? | Graph nodes = single process, easy to start. MCP servers = independently deployable, more operational overhead. | Phase 2 |
| OQ-03 | Approval UX: Slack bot, web dashboard, or ticket? | Depends on what the on-call team actually uses. | Phase 5 |
| OQ-04 | How aggressive is auto-remediation in dev/staging? | Risk tolerance question. A restart in dev is fine; a topic purge is not. | Phase 5 |
| OQ-05 | Incident history storage: Postgres, Mongo, or file? | Affects RAG indexing pipeline design. | Phase 3 (RAG) |
| OQ-06 | Single shared Executor or per-domain Executor? | Single is simpler. Per-domain allows domain-specific verification logic. | Phase 5 |
| OQ-07 | How to handle multi-owner entities (shared Kafka topics)? | Primary-owner field + producer/consumer priority rules is the current plan. | Phase 4 |

---

## Pending implementation (do not lose)

### Mode B — Interactive / conversational entry

**Status**: **PENDING** — build after **Mode A** (alert-driven investigation: ingest alert → controller → workers → RCA) is stable.

**What it is**: User asks follow-ups or ad-hoc questions in natural language, but answers still go through **rules-first routing** and the **same worker contract + evidence chain**. Raw chat must become a **bounded structured intent** (fixed JSON schema), not LLM-freeform tool selection.

**Where to include it when implementing**:

| Area | Responsibility |
|------|----------------|
| **Entry surface** | New path alongside alert ingestion: e.g. HTTP endpoint, CLI subcommand, Slack thread, or web chat — all call into the controller pipeline. |
| **Intent layer** (controller-adjacent) | Parse/translate user text → `InvestigationIntent` (optional LLM **only** with strict JSON schema + validation); enforce allowlists (namespaces, entities, read-only). |
| **Controller core** | Reuse orchestration: treat validated intent as **synthetic alert + session**; same routing table, inventory/graph lookups, worker calls, confidence gates, **decision log**. |
| **Session / follow-up state** | Track conversation thread id, prior steps, and token budget for multi-turn; extend controller state machine, not workers. |
| **Logs / “listen”** | Log pulls or tails stay behind **observability worker + adapter**; controller **decides when** to invoke per stage/rules — not an unbounded side channel. |

**Related**: OQ-03 (approval/chat UX) may overlap when Mode B ships; keep Mode B read-only until approval flow exists for anything mutating.

---

## Superseded Decisions

*None yet.*

---

*Infinity-Sentinel / FixOps · Chandrika Prasad · Last updated: 2026-04-22*
