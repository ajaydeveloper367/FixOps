# Infinity-Sentinel — Project Goal

> **The north star. Read this before reading anything else.**
> Implementation may change. Deployment patterns may change. This does not.

---

## The Problem

When an alert fires at 3am, on-call engineers spend 30–90 minutes manually
correlating logs, metrics, configs, runbooks, and Slack history just to understand
what broke and why. This is slow, error-prone, and burns skilled engineers on
mechanical, repetitive investigation work.

---

## The Goal

An agentic AI system that investigates operational incidents autonomously —
walking the dependency chain, gathering targeted evidence, forming a structured
root cause analysis, and proposing a fix — so the on-call engineer receives a
clear, evidence-backed answer instead of a dashboard to stare at.

The engineer's job shifts from **detective** to **decision-maker**.

---

## What this system guarantees (non-negotiables)

These are invariants. They hold regardless of implementation pattern, framework,
or deployment topology.

**1. No action executes without human approval.**
Ever. Not in prod, not in staging. Auto-remediation is a configurable option for
lower environments only, and only when explicitly enabled. The default is always:
suggest → human approves → execute → verify.

**2. Routing is deterministic, not LLM-freeform.**
The LLM extracts the entity from an alert. Deterministic rules decide which worker
investigates. The LLM does not choose where to look next — the controller does.
This makes the system testable, auditable, and explainable.

**3. Every conclusion requires an evidence chain.**
RCA is not the loudest symptom. It is the chain:
`alert → upstream check → root signal → proposed cause → supporting evidence`.
A confident-sounding answer without evidence is not an acceptable output.

**4. Workers never see each other's raw data.**
All inter-worker communication goes through the controller, carrying only compact
structured findings. No raw log dumps passed between agents.

---

## What is deliberately flexible

These may differ by environment, phase, or system. Changing them does not
violate the goal.

- **Implementation pattern** — single agent, multi-agent, graph-based, service-per-worker, all valid
- **Framework** — LangGraph, custom state machine, LangChain, raw Python
- **Deployment** — monolith to start, split later, different patterns per environment
- **Model vendors** — GPT-4o, Claude Sonnet, open-source — the worker output contract is what matters, not the model behind it
- **Approval UX** — Slack bot, web dashboard, ticket system, CLI — whatever the team uses
- **Remediation aggressiveness** — configurable per environment

---

## The one test

> "If an on-call engineer reads the system's output without looking at a single
> dashboard, do they know what broke, why it broke, what to do, and what the
> system already ruled out?"

If **yes** — the system is doing its job.
If **no** — something in the design or output quality needs to be fixed.

---

## What success looks like at different stages

| Stage | What "working" means |
|---|---|
| Phase 1 | Full investigation flow works end-to-end on mocked data. Controller routes correctly. Workers return structured findings. |
| Phase 2 | Real K8s + Prometheus + Loki alerts produce a valid RCA with evidence. On-call engineer says "that's correct". |
| Phase 3 | Data pipeline alerts (Airflow, Kafka, Mongo) handled. DAG failure traced upstream automatically. |
| Phase 4 | Routing is fully deterministic from live inventory. No manual lookup needed. |
| Phase 5 | Approved remediation executes and verifies. Engineer trust is established. |
| Long-term | The system is the first thing the on-call engineer reads, not the last. |

---

## Related files

| File | Purpose |
|---|---|
| `.cursor/rules/agentic-ops-system.mdc` | Locked architectural decisions — the HOW |
| `DECISIONS.md` | Living log of implementation decisions and trade-offs |
| `tools-architecture.html` | Detailed tooling, worker contracts, RAG, confidence scoring |
| `system-architecture.html` | System map, investigation flow, build phases |
| `system-data-examples.html` | End-to-end example investigations with real data |

---

*Infinity-Sentinel · Chandrika Prasad*
