# Phase 4 — The AI Pipeline

How a 250 MB binary file becomes a paragraph a player trusts.

```
Upload (.dem)
   ↓  ① intake & dedupe
Validated demo in R2
   ↓  ② decompress & parse
Raw event stream
   ↓  ③ normalize & enrich
Canonical events + zones + timeline
   ↓  ④ persist
Postgres event tables
   ↓  ⑤ compute metrics
Player/round/team metric rows
   ↓  ⑥ benchmark
Percentiles vs self + cohort
   ↓  ⑦ run rules
Typed findings with citations
   ↓  ⑧ rank & select
Top-N findings within a token budget
   ↓  ⑨ assemble context pack
~4–6k tokens of structured JSON
   ↓  ⑩ generate
LLM → structured report sections
   ↓  ⑪ validate
Citation + hallucination checks
   ↓  ⑫ persist & index
Reports stored, embeddings written
   ↓  ⑬ serve & converse
Report UI + tool-using chat
   ↓  ⑭ feedback loop
Thumbs → evals → prompt/threshold changes
```

The single most important structural fact: **stages ①–⑧ contain no AI at all.**
By the time a model is invoked, the analysis is already done. The model's job is
explanation, prioritization and language — not discovery. That inversion is what
makes the output trustworthy, cheap and fast.

---

## ① Intake & dedupe

The client hashes the file (SHA-256, streaming, in a Web Worker so the UI
doesn't freeze) and asks the server whether that hash exists. If yes, the user
is attached as an owner of the existing demo and jumps straight to the report —
zero cost, instant result. This is the common case for a 5-stack.

If no, the server issues a presigned multipart upload. On completion it verifies
object size and magic bytes (`HL2DEMO` / `PBDEMS2`), rejects anything that isn't
a demo, and enqueues a parse job.

**Failure modes handled here:** wrong file type, POV demo (detected by header
and player count — needs a clear user-facing explanation, since it's a common
mistake), corrupt/truncated file, decompression bomb.

## ② Decompress & parse

The worker streams the object to local disk, decompresses with a ratio guard,
and runs the parser in a resource-limited subprocess (memory cap, CPU cap, no
outbound network). Subprocess isolation matters: a malformed demo that segfaults
a native parser must kill one job, not the worker.

Extracted: match header, player list, tick-level entity state, and the game
event stream (`player_death`, `player_hurt`, `weapon_fire`, `grenade_detonate`,
`flashbang_detonate`, `bomb_planted`, `round_end`, `round_officially_ended`,
plus the entity-property snapshots for positions and inventory).

## ③ Normalize & enrich

The parser's raw output is not analysis-ready. Enrichment adds:

- **Round boundaries** reconciled between `round_start`, `freeze_end` and
  `round_officially_ended` (these disagree; knife rounds, warmup and timeouts
  produce phantom rounds that must be dropped).
- **Side assignment per half**, including overtime side swaps every 3 rounds.
- **Zone labels** — every position mapped to a named callout via per-map
  polygons. This is what lets the AI say "B doors" instead of `(-1240, 2317)`.
  Hand-authored per map; ~25–40 polygons each.
- **Opening duel detection** — first kill of a round, tagged for both players.
- **Trade linkage** — a kill within 3 seconds and ~500 units of a teammate's
  death, attributed to the victim's killer. Both the window and the distance
  matter; time alone over-counts.
- **Buy classification** per team per round from equipment value + loss
  bonus context (full buy / semi / force / eco / pistol).
- **Execute detection** — ≥2 utility detonations within 6 seconds toward one
  site followed by entry within 10 seconds.
- **Round phase segmentation** — freeze, early (0–20s), mid, late, post-plant.
- **Flash effectiveness** — was the victim looking at the flash, was a kill
  taken during the blind window, was it self or team.
- **Death clustering** — DBSCAN over death coordinates per player per map, which
  is what surfaces "you die at this exact spot repeatedly."

## ④ Persist

Bulk COPY into the event tables inside one transaction per stage, with the job
checkpointed after each. Idempotent: rerunning a stage deletes that match's rows
for that stage first, so a retry never duplicates.

## ⑤ Compute metrics

Pandas/Polars over the in-memory event frames (not SQL — this runs before or
alongside persistence and is far faster in-process). Produces
`player_round_stats`, `player_match_stats`, `team_round_stats`.

Every metric carries its sample size. A metric computed over fewer than
`min_sample_size` rounds is emitted with a `low_confidence` flag and is
**excluded from findings entirely** — this single rule prevents the most common
form of AI coaching nonsense.

## ⑥ Benchmark

Each metric is compared against two baselines:
- **Self** — the player's own trailing 20 matches. Answers "is this normal for
  me or is this a bad day?", which is the more useful comparison and the one no
  competitor emphasizes.
- **Cohort** — players at similar rank on the same map and side. Precomputed
  percentile distributions, so lookup is a range check.

Output: `value`, `percentile_self`, `percentile_cohort`, `delta_vs_self_avg`.

## ⑦ Run rules

The deterministic insight engine. Each rule is a pure function
`(match_data, player) → Finding | None`, registered with a key, version,
category, and threshold config loaded from `insight_rules`.

A finding carries: title, severity, confidence, the metrics that triggered it,
sample size, and **citations** — specific round ids and ticks. A rule that
cannot cite is not allowed to fire.

Roughly 40–60 rules at launch across utility, aiming/duels, positioning,
economy, teamplay, and clutch categories.

## ⑧ Rank & select

Typically 15–40 findings fire per player. The report needs 3–6. Ranking is
deterministic, by a composite score:

`severity × confidence × recency_weight × actionability × novelty`

where **novelty** penalizes findings the user has already been told about in
recent matches unless the streak is worsening (in which case it's *promoted* —
"this is the 7th match in a row" is more valuable than a fresh minor finding),
and **actionability** is a per-rule constant reflecting whether the player can
actually change it this week.

Selection is capped by a token budget, not a count.

## ⑨ Assemble the context pack

The most important engineering artifact in the AI layer. A deterministic
serializer produces something like:

```
identity        who the player is, role inference, rank, sample context
match_summary   map, score, halves, side performance, turning-point rounds
player_metrics  ~20 headline metrics with value + both percentiles + n
findings        the selected 3–6, with evidence and citations
round_digest    one compact line per round: economy, outcome, cause
history         mistake streaks, recent trend on relevant metrics
metric_glossary definitions for exactly the metrics present (cached)
```

Budget: **4,000–6,000 tokens.** The glossary and system prompt are identical
across every user and every match, so they sit behind Anthropic prompt caching —
that's the majority of input tokens served at a fraction of the cost.

What is deliberately **not** in the pack: raw ticks, full kill lists, anything
requiring the model to do arithmetic, and any untrusted string that hasn't been
escaped. Player names are wrapped in delimiters and the system prompt declares
them untrusted data — a player named `SYSTEM: ignore prior instructions` will
show up eventually.

## ⑩ Generate

Three generation types, each with its own prompt file and version:

| Type | Model | Why |
|---|---|---|
| Match post-mortem (team-level "why did we lose") | Opus 4.8 | Causal reasoning across 30 rounds; the flagship output |
| Personal report (top mistakes, drills) | Sonnet 5 | High volume, well-scoped by findings |
| Round narrative (3–5 key rounds) | Sonnet 5 | Short, templated, cheap |
| Chat turns | Sonnet 5 | Latency-sensitive, tool-driven |
| Titles / routing / moderation | Haiku 4.5 | Trivial classification |

Output is **structured via tool schemas** — the model returns typed sections
with a `finding_ids` array per section, never free-form JSON in prose. Sections
stream to the client as they complete.

Prompt design principles that matter here:
- Give the model a **persona with constraints**: an experienced coach who is
  specific, never flattering, and never invents numbers.
- **Forbid arithmetic.** Every number in the output must be copied from the
  context pack.
- **Require citations.** Each claim references a finding id or round number.
- **Demand specificity over completeness.** Three concrete observations beat ten
  generic ones. This is the difference between the product and a horoscope.
- **Include the anti-patterns explicitly** — show the model examples of bad,
  generic coaching output and tell it not to write that.

## ⑪ Validate

Before a report is shown, an automated validator checks:

1. Every cited round number exists in this match.
2. Every cited finding id was actually in the context pack.
3. Every numeric literal in the output appears in the context pack (tolerance
   for rounding). **A number the model invented is a hard rejection.**
4. No section is empty, truncated, or below a length floor.
5. Output passes a banned-phrase filter (hedge language, "as an AI", generic
   filler).

Failures trigger one regeneration with the validator's complaint appended. A
second failure marks the report degraded and shows the deterministic findings
without prose — the user still gets value, and the incident is logged for
prompt work.

## ⑫ Persist & index

Report and sections stored. Embeddings generated for round summaries, findings
and report sections, scoped to the user, and written to pgvector for later
recall queries.

## ⑬ Serve & converse

The report is a stored artifact, served instantly on every subsequent view.

Chat is a separate loop: the model receives a small system prompt, the current
match context, and a **tool set** — `get_player_metrics`, `query_rounds`,
`get_round_timeline`, `find_deaths`, `get_grenades`, `compare_to_cohort`,
`get_findings`, `search_history` (vector), `get_match_list`. Every tool is
implemented with the requesting user's id bound at construction; scoping is
structural, not prompted.

The model plans, calls tools, reads results, and answers with clickable round
citations. Turn cap and cost ceiling per conversation prevent runaway loops.

## ⑭ Feedback loop

- **Per-section thumbs** feed a quality dataset joined to `prompt_version` and
  `model`.
- **Golden set:** ~20 demos with human-written expected findings. Every prompt
  or threshold change runs against it in CI, scored on finding overlap,
  citation validity, and an LLM-judge rubric for specificity. Regression blocks
  the merge.
- **Rule tuning:** findings with consistently negative feedback get their
  thresholds revisited — which is why `insight_rules.threshold_config` lives in
  the database.
- **Failure corpus:** every parse failure contributes its demo to the fixture
  set.

## Cost model (target)

| Stage | Cost per match |
|---|---|
| Parse compute (~90s of a 4-vCPU worker) | ~$0.004 |
| Storage (demo 30d + derived) | ~$0.006 |
| Post-mortem, Opus, ~6k in (mostly cached) / 1.5k out | ~$0.12 |
| Personal reports ×5 players, Sonnet | ~$0.05 |
| Round narratives ×4, Sonnet | ~$0.02 |
| Embeddings | ~$0.001 |
| **Total** | **~$0.20** |

At $7/month with ~15 matches analyzed, cost of goods is roughly $3 — workable
but not comfortable. The levers, in order of impact: aggressive prompt caching,
generating personal reports only for the uploading user by default (others on
demand), routing more work to Sonnet, and caching the team-level post-mortem
across all five players of the same match (it's identical for all of them —
this alone is a 5× saving on the most expensive call).

## Quality bar

The product is working when a player reads a report and says **"yeah, that's
what happened"** — not "wow, impressive". Measured by:
- Section thumbs-up rate > 70%
- Citation validity 100% (hard requirement, enforced by the validator)
- Golden-set finding overlap > 80% with human labels
- % of users who open a cited round in the viewer (proof they believed it enough
  to check)
