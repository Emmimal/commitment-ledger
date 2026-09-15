# Archived: Earlier Agent Protocol Plan

This document describes an earlier live-agent experiment that was
considered during development.

It is no longer part of the implementation or evaluation described
in this repository.

The final project uses deterministic Python transcripts and a
standard-library-only Commitment Ledger.

The authentication task structure and dependency relationships defined
below did carry forward into the final implementation (see
`ledger.py`'s `DEPENDENCY_MAP` and the task description in the main
README). Everything else here — model/version selection, the live
pilot procedure, the API runtime, temperature, and the blind
dialogue-coverage gate — belongs to the abandoned direction and is not
part of the current project.

---

# Task and Agent Protocol Specification

**Status: to be frozen before any model is run.** Once the chat-only pilot generates its first dialogue, nothing in this document may change without discarding that dialogue and starting over — a changed task or prompt after generation would contaminate the blind coverage corpus.

**Scope reminder:** this document defines the *experiment-generation setup* (task, agents, protocol). It does not touch Detector v1 or the Commitment Ledger implementation, both already frozen. Any external model used here is an experiment-generation dependency, not a dependency of the shipped ledger/detector, which remain pure Python/stdlib.

---

## 1. Task Specification

**Task name:** Minimal User Authentication Feature

**Why this task:** it decomposes into a small number of components with real dependencies, is small enough to run in a bounded number of turns, and creates natural opportunities for every failure mode the experiment measures — missed commitments, duplicate work, conflicting edits, and dependency-notification failures — without needing an artificial "coordination benchmark" framing.

**Components** (the shared task description given to both agents verbatim):

| Component | Path | Depends on |
|---|---|---|
| User model | `models/user.py` | — |
| User repository (create/get/delete) | `repository/users.py` | User model |
| Auth middleware | `middleware/auth.py` | User model |
| Login endpoint | `/login` | User repository, Auth middleware |
| Tests | `tests/test_auth.py` | All of the above |

**Task description given to agents (verbatim, frozen):**

> You and another engineer are jointly implementing a minimal user authentication feature for a small API. The feature needs: a User model, a user repository with create/get/delete operations, auth middleware, a `/login` endpoint, and tests. Neither of you has been assigned specific pieces in advance — figure out between yourselves who does what, and let each other know as you go. You do not need to write actual code in this conversation; just talk through the plan and coordinate the work the way you normally would.

**Why no pre-assigned division of labor:** this is deliberate. Pre-assigning ownership would suppress exactly the natural-language claiming behavior ("I'll take X," "I'll handle Y") the detector needs to be tested against. Leaving ownership open also creates genuine risk of duplicate claims and gaps, which is the point.

**Why "you do not need to write actual code" for the pilot:** the pilot's only job is harvesting natural coordination dialogue for the blind coverage test. It is not scored for task success, code correctness, or test-passing — those metrics belong to Phase 2 (the official comparison), not the pilot. Keeping the pilot to planning dialogue only avoids needing an actual code-execution harness before the detector has even cleared its coverage gate.

---

## 2. Agent Roles

- **Agent A** and **Agent B** — symmetric in capability and instructions. Neither is designated a lead. Both receive the identical task description above.
- No third agent, no human-in-the-loop moderator, no arbiter.

---

## 3. Model, Version, and Temperature — OPEN, must be filled before execution

This is the one section deliberately left as a placeholder rather than a default choice, because it requires your own model access and credentials to actually run — I can draft the runner script, but executing it needs your environment, the same as the `ANTHROPIC_API_KEY`-gated scripts in the relationship-density and reconciliation projects.

To freeze, record here before the pilot runs:

```
model: <exact model name and version string>
temperature: <value>
max_tokens per turn: <value>
API/runtime: <e.g. Anthropic API, local model, etc.>
```

Whatever is chosen, it is used identically for the pilot and for the official Phase 2 chat-only condition — this is one of the "same" parameters, not a pilot-only choice.

---

## 4. System Prompt (frozen, verbatim)

Given to both agents identically, with only the agent's own label (`A` or `B`) substituted:

> You are Agent {LABEL}, a software engineer working with one other engineer (Agent {OTHER_LABEL}) on a shared coding task. You communicate by sending messages back and forth in a shared channel. Speak naturally, the way a real engineer would when coordinating with a teammate — including making plans, offering to take on specific pieces of work, asking questions, and reporting progress. Do not use any special formatting, markup, or structured notation for your commitments — just talk normally. You will receive the task description as the first message.

**Why "do not use any special formatting":** the coverage test only means something if agents are speaking naturally, not accidentally structuring their language to look machine-parseable.

---

## 5. Communication Protocol

- **Channel:** single shared chat channel, both agents see all prior messages.
- **Turn order:** strict alternation, Agent A then Agent B, starting with Agent A.
- **Message budget:** 30 messages total (15 per agent), frozen. This scale matches the communication-budget precedent from [[relationship-density-layer]] (which used 35) — kept slightly smaller here since this task has fewer components and agents than that project's 8-agent setup.
- **Stopping conditions:** the run ends when either (a) both agents have explicitly agreed the plan is complete, or (b) the 30-message budget is exhausted, whichever comes first. Reaching the budget without agreement is recorded, not treated as an error — it's a legitimate data point for later, even though the pilot itself isn't scored.
- **Tool availability:** none for the pilot. No file writes, no code execution, no external calls from within the agent turns themselves. Pure dialogue.

---

## 6. Evaluation Rules for the Pilot Run

None. The pilot is not scored for task success, coordination quality, or any outcome metric. Its sole output is the raw transcript, which then feeds:

1. Extraction of ~50 genuine first-person commitment opportunities (identified independently by a human reviewer, without reference to what Detector v1 does or doesn't catch).
2. Independent gold-labeling of those ~50 opportunities.
3. Running Detector v1 against the transcript and computing coverage as already frozen: `commitments captured / genuine commitments identified`.

---

## 7. Pilot vs. Official Chat-Only Condition

Identical in every parameter above (model, temperature, system prompt, agent roles, task structure minus instance/seed, communication protocol, turn budget, tool availability, stopping conditions).

**Only difference:** the specific task instance/seed. If randomness is introduced anywhere in task instantiation (e.g. varied component names, varied scenario framing) in Phase 2, the pilot uses a distinct, separately recorded seed — and its output is never merged into or scored as part of the Phase 2 treatment comparison.

---

## 8. Freeze Checklist (Phase 0 → Phase 1 gate)

Before the pilot is run, confirm all of the following are frozen and recorded:

- [x] Detector v1 (grammar, verb vocabulary, concrete-object rules, documented limitations)
- [x] Task specification (Section 1)
- [x] Agent roles (Section 2)
- [ ] Model / version / temperature (Section 3 — **pending**)
- [x] System prompt (Section 4)
- [x] Communication protocol (Section 5)
- [x] Evaluation rules for the pilot (Section 6)

Only once every box is checked does Phase 1 (the actual pilot run) begin.

---

## 9. What Happens After the Pilot

Per the locked coverage protocol:

- Coverage ≥ 80% → PASS. Detector v1 and this protocol both stay frozen. Proceed to Phase 2 (official chat-only vs. chat+ledger comparison), reusing every frozen parameter above except the task instance/seed.
- Coverage < 80% → FAIL. No changes to the grammar based on the pilot corpus's specific misses beyond documenting *why* it failed. Revise to Detector v2, rerun the full 150-row regression set from scratch, then collect an entirely new pilot run (new seed) for a fresh blind corpus — the failed corpus is never reused as a second attempt.

---

## Amendment Log

*(empty — first entry goes here if the task, prompt, or protocol needs to change before the pilot has been run; once the pilot has run, this document is frozen and any change requires discarding that pilot's dialogue)*
