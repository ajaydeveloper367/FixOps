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

| Stage | Success signal |
|-------|------------------|
| **Early** | For a known alert shape, the system returns a structured checklist of what was checked, with at least one concrete evidence pointer |
| **Mid** | Multi-hop investigations (e.g. collection → graph → worker chain) complete with a decision log and bounded context |
| **Mature** | Human-gated remediation with verification; institutional knowledge (RAG or equivalent) improves repeat incidents |

---

## Related docs

| File | Role |
|------|------|
| `context/comparison/DECISIONS.md` | Locked architecture and implementation decisions |
| `.cursor/rules/fixops-agentic-northstar.mdc` | Consolidated target spec for greenfield implementation |
| `context/comparison/fixops-architecture-master.html` | Master architecture diagram (SVG + Mermaid) |

---

*Infinity-Sentinel / FixOps · Last updated: 2026-04-24*
