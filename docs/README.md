# AI CS2 Analyst — Engineering Blueprint

> **Status:** Planning only. No code has been written for this product.
> **Author role:** CTO / architect blueprint, written 2026-07-21.

## The one-sentence product

Upload a CS2 demo, and instead of 400 statistics you get a coach: a written
match post-mortem that explains *why* you lost, what your recurring mistakes
are, and what to practice — plus a chat window where you can interrogate the
demo in plain English.

## Why this can win

Every existing CS2 stats site (Leetify, Scope.gg, CSStats, refrag) is a
**dashboard**. They compute a number, put it in a card, and leave the
interpretation to the player. Interpretation is the hard part and the part
players actually want. The wedge is:

1. **Narrative over numbers.** "You lost because you burned 4 of 5 flashes on
   the A execute in the first 3 rounds of each half and had nothing left for
   retakes" beats `Flash assists: 1.2/round`.
2. **Causality over correlation.** Round-level reconstruction lets us say what
   *caused* the round loss, not just who had bad stats in it.
3. **Conversation.** A chat interface over a structured demo index means the
   product answers questions we never anticipated.

The moat is not the LLM (anyone can call one). The moat is the **structured
event index** — a demo compressed into a compact, queryable, LLM-legible
representation. That's the hard engineering, and it's what Phase 4 is about.

## Reading order

| File | Phase | Contents |
|---|---|---|
| [01-roadmap-milestones.md](01-roadmap-milestones.md) | 1 | 14 milestones, dependencies, difficulty, tech, DB, APIs, AI, outputs |
| [02-architecture.md](02-architecture.md) | 2 | System architecture end to end |
| [03-database.md](03-database.md) | 3 | Every table, relationship, index, rationale |
| [04-ai-pipeline.md](04-ai-pipeline.md) | 4 | Demo → insight, every step |
| [05-ux.md](05-ux.md) | 5 | Every screen, mobile, empty/error states |
| [06-mvp.md](06-mvp.md) | 6 | The 30-day cut line |
| [07-task-roadmap.md](07-task-roadmap.md) | 7 | 240 tasks, each < 3 hours |

## The five decisions that shape everything

Stated up front because everything downstream depends on them.

### 1. Parsing runs in Python, not Node
CS2 (Source 2) demos are protobuf. The mature parsers are `demoparser2`
(Rust core, Python bindings, returns pandas DataFrames) and `awpy` (analysis
layer on top of it). The Go option, `demoinfocs-golang`, is faster but you'd
write the entire analytics layer by hand. Python gives us DataFrames, which is
the right shape for the metric work in Milestone 5–7. **Decision: Python worker
service, Node/Next.js for everything user-facing.** Two languages, clean seam
(a queue), no shared code.

### 2. The LLM never sees the demo
It sees a **context pack** — a few thousand tokens of structured JSON we
assemble deterministically. Raw demos are 100–300 MB and a single round has
thousands of ticks. Every quality problem in this product reduces to "was the
context pack good?" not "was the prompt good?".

### 3. Metrics are computed, insights are generated
Hard split. `Opening duel win rate on B site as CT = 22%` is arithmetic in
Python and must be *exactly right and reproducible*. "You're over-peeking B
doors early" is the LLM's job. Never let the LLM do arithmetic; never let
Python write prose. This split is also the anti-hallucination strategy: every
claim in a report carries a citation to a computed metric or a specific round.

### 4. Manual upload first, integrations later
Valve match-sharing codes and FACEIT ingest are a huge unlock but a huge
distraction. MVP: drag a `.dem` in. Milestone 10 automates it.

### 5. Reuse the Instant Smokes stack
Next.js 15 App Router, TypeScript, Prisma, Postgres, Tailwind + shadcn/ui,
TanStack Query, Zod — same as the existing repo. New pieces are only the ones
the product genuinely requires: object storage, a queue, a Python worker,
pgvector, and the LLM layer. Familiarity is worth weeks.

## Assumptions I'm making (challenge any of these)

- Target user is a rank-caring player (Premier 10k–25k / FACEIT 5–10), solo or
  in a 5-stack, who already watches their own demos and finds it slow.
- Willingness to pay is real but low: ~$5–8/mo. Pricing must survive an LLM
  cost of well under $0.50 per analyzed match.
- Launch scope is 5v5 competitive on Active Duty maps. No Wingman, no Danger
  Zone, no workshop maps.
- Solo builder (you) plus me, not a funded team. Milestone sizing reflects that.
