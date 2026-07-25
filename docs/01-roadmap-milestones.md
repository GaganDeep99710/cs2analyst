# Phase 1 — Milestone Roadmap

Fourteen milestones from empty repo to production. Each one is independently
shippable and leaves the product in a working state.

Difficulty scale: **1** trivial · **2** routine · **3** real work · **4** hard,
expect surprises · **5** the thing that could sink the project.

Estimates assume one experienced developer working with AI assistance, ~4
focused hours/day.

---

## Milestone 0 — Foundation & Project Skeleton

**What gets built**
Monorepo layout (`apps/web` Next.js, `services/parser` Python, `packages/shared`
TypeScript types). TypeScript strict mode, ESLint, Prettier, Ruff + Black on the
Python side. Local Postgres via Docker Compose (or `embedded-postgres` as the
existing repo does). Prisma initialized. Environment variable schema validated
with Zod at boot so a missing key fails loudly at startup, not at 2am in a
request handler. Base design system: Tailwind config, shadcn/ui install, dark
theme as default, typography scale, the CS2-flavored color tokens.

**Why it matters**
Every hour spent here is repaid five times. The specific high-leverage items are
strict TS (the shared types between parser output and frontend are where bugs
will live) and env validation (this product has ~15 secrets across S3, Postgres,
Redis, Anthropic, Steam, Stripe — silent misconfiguration is the default failure
mode otherwise).

**Dependencies** None.
**Difficulty** 2. **Estimate** 3–4 days.
**Technologies** pnpm workspaces, Next.js 15, TypeScript 5.7, Tailwind 3.4,
shadcn/ui, Prisma 6, Docker Compose, Python 3.12, uv, Ruff.
**Database changes** Initial migration: empty schema + Prisma baseline.
**APIs** `GET /api/health` returning DB/Redis/S3 reachability.
**AI requirements** None.
**Expected output** `pnpm dev` serves a dark-themed landing shell at
localhost:3000; `/api/health` returns all-green; Python service responds to a
health ping; CI runs lint + typecheck on push.

---

## Milestone 1 — Authentication & Accounts

**What gets built**
Auth.js (NextAuth v5) with **Steam OpenID as the primary provider** plus email
magic link as fallback. Steam matters because SteamID64 is the join key for
everything: it's how we identify "you" inside a demo file without asking you to
pick your name from a dropdown. Session handling, protected route middleware,
`/settings/account`, account deletion (GDPR — hard requirement, not a nice to
have), and the `User` / `Account` / `Session` / `SteamProfile` tables.

**Why it matters**
Without SteamID linkage every report has to start with "which player are you?",
which is friction on the single most important flow. Steam auth turns player
identification into a solved problem for the rest of the product's life.

**Dependencies** Milestone 0.
**Difficulty** 2 (3 if Steam OpenID fights you — it's OpenID 2.0, legacy, and
Auth.js has no first-class provider; expect to write a custom provider).
**Technologies** Auth.js v5, Steam OpenID 2.0, Steam Web API
(`GetPlayerSummaries` for avatar/nickname), Prisma adapter, Resend for email.
**Database changes** `User`, `Account`, `Session`, `VerificationToken`,
`SteamProfile`.
**APIs** `/api/auth/*`, `GET /api/me`, `DELETE /api/me`.
**AI requirements** None.
**Expected output** Sign in with Steam, land on an empty dashboard showing your
Steam avatar and SteamID64, sign out, delete account and have every row cascade.

---

## Milestone 2 — Upload, Storage & Job Queue

**What gets built**
Demo upload accepting `.dem`, `.dem.bz2`, and `.dem.gz` (Valve serves bz2;
FACEIT serves gz). Files are 50–400 MB, so uploads go **direct to object storage
via presigned URLs** — never through the Next.js server, which would blow
serverless request limits and cost. Client-side chunking with resume. SHA-256
content hash computed client-side and checked server-side for dedupe (the same
demo uploaded by five teammates must parse once). Redis-backed queue, a job
lifecycle state machine, and the `Demo` / `Job` tables.

Job states: `uploaded → queued → parsing → parsed → analyzing → complete`, with
`failed` and `cancelled` reachable from any state, and a `retry_count`.

**Why it matters**
This is the product's front door and its biggest reliability surface. A 300 MB
upload that dies at 94% on hotel wifi is a churned user. Dedupe by content hash
is not an optimization — it's the difference between a 5-stack costing you 1
parse or 5.

**Dependencies** Milestone 1.
**Difficulty** 3. Large-file upload is always fiddlier than it looks.
**Technologies** Cloudflare R2 (S3-compatible, **zero egress fees** — decisive
when you're serving back demo-derived assets, and R2 is roughly 1/4 of S3 for
storage), presigned multipart uploads, BullMQ + Redis (Upstash), uppy or a
custom uploader.
**Database changes** `Demo`, `DemoUpload`, `Job`.
**APIs** `POST /api/demos/presign`, `POST /api/demos/complete`,
`GET /api/demos`, `GET /api/demos/:id`, `DELETE /api/demos/:id`.
**AI requirements** None.
**Expected output** Drag a 250 MB demo onto the page, watch a real progress bar,
refresh mid-upload and have it resume, see the demo appear in a list as
`queued`. Upload the same file again and get an instant "already analyzed" link.

---

## Milestone 3 — Demo Parsing (the core engineering risk)

**What gets built**
The Python parser service. Pulls a job, streams the demo from R2 to local disk,
decompresses, parses, and emits a normalized event set:

- **Match header** — map, tickrate, server, date, final score, mode detection.
- **Players** — SteamID64, name, team per half, side swaps.
- **Rounds** — start/end tick, winner, end reason (elimination / bomb / defuse /
  time), economy at freeze-time end, buy classification.
- **Kills** — attacker, victim, weapon, headshot, wallbang, through-smoke,
  no-scope, attacker/victim positions and view angles, flash duration on victim,
  assisters, trade window linkage.
- **Damage** — every hit, hitgroup, HP removed, armor.
- **Grenades** — thrown/detonated, type, throw position, throw angle, detonation
  position, trajectory samples, flash victims + duration, molotov damage,
  smoke bloom volume.
- **Bomb** — plant/defuse/explode with tick, site, position, defuse-kit flag.
- **Positional ticks** — decimated to ~4 Hz (not the native 64/128) with
  position, view angle, HP, armor, active weapon, ducking/scoped flags. This is
  the single largest data volume decision in the product.

Also: a **canonical map coordinate transform** (world coords → radar image
pixels, per map, using the `.txt` radar metadata Valve ships) and callout
resolution (world position → "B doors", "Cat", "Mid"), which needs a hand-built
polygon set per map.

**Why it matters**
Every downstream feature is a function of this output. If parsing is wrong, the
AI confidently lies. If parsing is slow, unit economics break. This is the
milestone most likely to eat double its estimate — CS2 demos have edge cases
(POV demos vs GOTV, MR12 vs MR15, overtime, coaches, disconnects/reconnects,
substitutes, ESEA/FACEIT config differences).

**Dependencies** Milestone 2.
**Difficulty** 5. **Estimate** 2–3 weeks.
**Technologies** Python 3.12, `demoparser2`, `awpy` (map metadata + coordinate
transforms), pandas, Polars if pandas gets slow, `boto3`, Pydantic for the
output contract.
**Database changes** `Match`, `MatchPlayer`, `Round`, `Kill`, `Damage`,
`Grenade`, `BombEvent`, `PlayerTick`. `PlayerTick` and `Damage` should be
partitioned by `match_id` from day one — retrofitting partitioning later is
painful.
**APIs** Internal only: worker consumes queue, writes DB, publishes progress to
Redis pub/sub.
**AI requirements** None yet — but the output schema **is** the AI's world
model, so design it as if an LLM will read it, because one will.
**Expected output** A parsed 30-round MR12 demo, in under 90 seconds, producing
~10k kills/damage/grenade rows and ~450k decimated tick rows, with a CLI that
prints a round-by-round summary you can eyeball against the actual demo in-game.

---

## Milestone 4 — Match Overview UI

**What gets built**
Read-only match pages: scoreboard (K/D/A, ADR, HS%, KAST, rating), round timeline
strip with win/loss and end-reason icons, economy graph, per-round expansion
showing the kill feed. Demo library with filters (map, date, result, mode).
Real-time job progress via SSE.

**Why it matters**
It's the proof the parser works, and it's the trust-building surface. Users will
not believe AI insight from a product whose scoreboard is visibly wrong. Ship
this *before* any AI so you debug parsing against your own eyes.

**Dependencies** Milestone 3.
**Difficulty** 3.
**Technologies** Next.js RSC for data fetching, TanStack Query for the live job
polling, Recharts or visx for the economy graph, SSE for progress.
**Database changes** None (read paths only). Add covering indexes as the query
patterns reveal themselves.
**APIs** `GET /api/matches/:id`, `/api/matches/:id/rounds`,
`/api/matches/:id/scoreboard`, `GET /api/jobs/:id/stream`.
**AI requirements** None.
**Expected output** A match page you'd be willing to screenshot for a landing
page, with numbers that match what CSStats/Leetify report for the same demo
(±small rounding). **This cross-check is a required exit criterion.**

---

## Milestone 5 — Metrics & Analytics Engine

**What gets built**
The deterministic analytics layer — the vocabulary the AI will speak in. Roughly
five families:

*Core:* ADR, KAST, HS%, opening kill/death rate, trade kill/death rate,
multi-kills, clutch attempts and conversions by situation (1v1…1v5), impact
rating, HLTV 2.0-style rating.

*Utility:* flash assists, enemies flashed with time-blinded buckets, **self- and
teammate-flash counts** (highly diagnostic), utility damage, smoke usefulness
(did it block a real sightline into a contested area?), utility left unthrown at
round end (a top-3 recurring mistake in real play), nade timing vs. execute start.

*Positional:* opening duel win rate segmented by map zone and side, time-to-first-
contact, map-control area over time, common death locations, rotation timing,
off-angle vs. default-angle deaths, crossfire participation.

*Economic:* buy classification (full/force/eco/semi), economic damage per round,
save discipline, weapon value lost, forced-buy win rate.

*Team:* execute detection (grouped utility + entry within a window), site hit
distribution, spread vs. stack, retake success by site, post-plant conversion.

Each metric emits **value, percentile vs. the user's own history, percentile vs.
peer rank cohort, and n (sample size)**. Sample size travels with the metric
everywhere so nothing ever claims a trend from three rounds.

**Why it matters**
This is where the product's actual intelligence lives. The LLM is a translation
layer over these numbers. Weak metrics → generic coaching that reads like a
horoscope, which is the #1 failure mode of AI coaching products.

**Dependencies** Milestone 3.
**Difficulty** 4. Individually easy, collectively large, and each needs
validating against real demos.
**Technologies** Python, pandas/Polars, NumPy, Shapely (zone polygons),
`awpy` nav mesh for area/distance work.
**Database changes** `PlayerMatchStats`, `PlayerRoundStats`, `TeamRoundStats`,
`MetricDefinition` (a registry: id, name, unit, direction — "higher is better" —
description, formula doc), `MetricValue`, `BenchmarkCohort`.
**APIs** `GET /api/matches/:id/metrics`, `GET /api/players/:id/metrics?window=`.
**AI requirements** None, but `MetricDefinition.description` is written *for the
LLM to read* — it's a prompt asset, not developer docs.
**Expected output** A metrics JSON per player per match, and a CLI diff tool that
shows metric drift between parser versions so you know when you've broken
something.

---

## Milestone 6 — Round Reconstruction & 2D Viewer

**What gets built**
A 2D replay: radar image per map, dots for players with team color and view
cones, grenade trajectories and smoke/molly footprints, bomb state, scrubbable
timeline, play/pause/speed, keyboard shortcuts, and jump-to-event. Deep-linkable
to a round and tick so an AI insight can say "watch this" and mean it.

**Why it matters**
Two reasons. Users trust what they can see — this is the evidence layer that
makes AI claims verifiable. And it's the demo-able moment that sells the product
in a tweet.

**Dependencies** Milestones 3, 4.
**Difficulty** 4. Rendering is fine; smooth interpolation, tick decimation and
payload size are the real problems.
**Technologies** Canvas 2D (not SVG — hundreds of moving nodes) or PixiJS,
radar images extracted from game files, a binary tick payload
(Float32Array over an ArrayBuffer, not JSON — a round of JSON ticks is ~5 MB,
the binary version is ~200 KB), Zustand for player state.
**Database changes** `RoundReplayBlob` — precomputed per-round binary tick blob
stored in R2, referenced by URL, cached aggressively.
**APIs** `GET /api/rounds/:id/replay` returning the blob URL + metadata.
**AI requirements** None.
**Expected output** Scrub a round at 60fps with grenades and smokes rendering,
on a mid-range laptop, with under 400 KB transferred per round.

---

## Milestone 7 — Insight Detection Engine

**What gets built**
A rule engine that converts metrics into **candidate insights** before any LLM
runs. Each rule is a named, versioned, tested predicate over match data, and
emits a typed finding with severity, confidence, supporting metrics, and
citations to specific rounds/ticks.

Example rule families:
- *Utility waste* — died with ≥2 nades unthrown in ≥40% of rounds.
- *Opening duel leak* — opening duel WR < 40% with n ≥ 8, localized to a zone.
- *Trade failure* — teammate died within 3s of you ≥N times with no trade
  attempt.
- *Over-rotation* — left site before contact was confirmed, N times.
- *Economy* — force-bought into a lost round N times, costing X.
- *Flash discipline* — teammate-flash duration above cohort p90.
- *Positional repetition* — died at the same coordinate cluster ≥3 times
  (the strongest single "recurring mistake" signal in practice).
- *Clutch* — 1vX conversion far below cohort, with situational breakdown.

**Why it matters**
This is the anti-hallucination architecture. The LLM is never asked "find
problems in this data" — it is handed pre-verified findings and asked to explain
and prioritize them. Every sentence it writes can be traced to a rule that
fired. This is also what makes the product *cheap*: findings are small, and the
LLM sees a page of them instead of a match.

**Dependencies** Milestone 5.
**Difficulty** 4. The engineering is easy; getting the thresholds right requires
looking at a lot of real demos.
**Technologies** Python, a declarative rule registry, pytest with recorded demo
fixtures.
**Database changes** `InsightRule`, `Finding`, `FindingCitation`.
**APIs** `GET /api/matches/:id/findings`.
**AI requirements** None — this is deliberately pre-AI. The rules are the
grounding.
**Expected output** For any parsed match, 5–20 findings per player, each with a
severity, an evidence list, and round/tick citations that resolve in the viewer.

---

## Milestone 8 — LLM Integration & Match Reports

**What gets built**
Context pack assembly (findings + metrics + round summaries + player identity,
budgeted to a token ceiling), the prompt system, and generation of:
- a **match post-mortem**: why the match was lost/won, 3 turning-point rounds,
  team-level read, per-player read;
- a **personal report**: top 3 mistakes, one thing to keep doing, one drill;
- **round narratives** for the 3–5 most decisive rounds.

Plus the production concerns: structured output via tool-use schemas (not
"please return JSON"), prompt caching on the static system prompt and metric
dictionary, streaming to the client, cost accounting per generation, retries
with backoff, and a **citation validator** that rejects any generated claim
referencing a round or metric that doesn't exist.

**Why it matters**
This is the product. Everything before it was scaffolding.

**Dependencies** Milestone 7.
**Difficulty** 4. Wiring is a day; getting the output to read like a good coach
rather than a LinkedIn post is two weeks of iteration.
**Technologies** Anthropic API. **Claude Sonnet 5** for the per-round and
routine generations, **Claude Opus 4.8** for the headline match post-mortem
where reasoning quality is most visible. Prompt caching (1-hour TTL) on the
system prompt + metric dictionary — this is a large cost lever since those
tokens are identical across every user. Streaming via the Vercel AI SDK.
**Database changes** `Report`, `ReportSection`, `LlmGeneration` (model, prompt
version, input/output tokens, cost, latency, cache hit rate), `PromptVersion`.
**APIs** `POST /api/matches/:id/report`, `GET /api/reports/:id`,
`GET /api/reports/:id/stream`.
**AI requirements** Prompt versioning from the first commit; every generation
records which prompt version produced it, or you can never explain a quality
regression. Golden-set eval harness: ~20 demos with human-written expected
findings, scored on every prompt change.
**Expected output** A match report that a Premier player reads and says "yeah,
that's actually what happened" — measured by a thumbs up/down on every section
from real users.

---

## Milestone 9 — Conversational AI Chat

**What gets built**
The "talk to your demo" surface. Chat with **tool use over the structured
index**, not RAG-over-text. The model gets tools like `query_rounds`,
`get_player_metrics`, `find_deaths_in_zone`, `compare_to_cohort`,
`get_round_timeline`, `search_similar_situations`. It plans, calls tools,
reads results, answers with citations that render as clickable round links.

pgvector enters here, but narrowly: embeddings over *round summary text* and
*findings* to support "have I made this mistake before?" across a user's whole
history. Vector search is the fallback for fuzzy recall; structured tools handle
everything precise.

**Why it matters**
It's the differentiator and the retention driver. Reports are read once; chat
brings people back.

**Dependencies** Milestone 8.
**Difficulty** 4.
**Technologies** Anthropic tool use, Vercel AI SDK for streaming UI, pgvector +
Voyage embeddings, per-user rate limiting.
**Database changes** `Conversation`, `Message`, `ToolCall`, `Embedding`
(pgvector, HNSW index).
**APIs** `POST /api/chat`, `GET /api/conversations`.
**AI requirements** Tool schemas are the real design work. Hard scoping: every
tool call is filtered to demos the requesting user can access — an unscoped tool
is a data leak, so scoping lives in the tool implementation, never in the prompt.
**Expected output** Ask "why did we lose the second half?" and get an answer that
cites five specific rounds and is correct.

---

## Milestone 10 — Automatic Demo Ingestion

**What gets built**
Valve match-sharing-code ingestion (user pastes an auth code + share code once;
we walk the match history chain via `GetNextMatchSharingCode`, download from
Valve's CDN, and auto-analyze). FACEIT OAuth + webhook ingestion. Optional folder
watcher for local demos.

**Why it matters**
Converts the product from a tool you remember to use into a service that's just
there after every match. This is the single biggest retention lever in the
roadmap.

**Dependencies** Milestone 8.
**Difficulty** 4 — undocumented Valve surface area, rate limits, and the Game
Coordinator path is genuinely annoying.
**Technologies** Steam Web API, `boiler-writter` or a GC client for share-code
resolution, FACEIT Data API + webhooks.
**Database changes** `DemoSource`, `IngestConnection`, `IngestCursor`.
**APIs** `POST /api/ingest/steam/connect`, `/api/ingest/faceit/callback`,
`POST /api/webhooks/faceit`.
**AI requirements** None.
**Expected output** Finish a Premier match, get a push/email 6 minutes later:
"Your Mirage match is analyzed."

---

## Milestone 11 — Player Profile & Longitudinal Trends

**What gets built**
The cross-match view: rating over time, per-map strength, recurring-mistake
tracking (is the flash discipline finding still firing 20 matches later?),
improvement scoring, role inference (entry / support / lurk / AWP / IGL) from
behavior rather than self-report, and a periodic "progress report" generation.

**Why it matters**
Single-match analysis is a novelty. "You've cut your unthrown-utility rate from
41% to 18% over six weeks" is the thing people pay monthly for and screenshot.

**Dependencies** Milestones 5, 8.
**Difficulty** 3.
**Technologies** Materialized views or a nightly rollup job, Recharts.
**Database changes** `PlayerAggregate` (rollup by player × map × side × window),
`ProgressReport`, `MistakeStreak`.
**APIs** `GET /api/players/:id/profile`, `/api/players/:id/trends`.
**AI requirements** A distinct prompt: comparative/longitudinal, not single-match.
**Expected output** A profile page that shows a curve going the right way.

---

## Milestone 12 — Monetization, Limits & Billing

**What gets built**
Stripe. Free tier (3 demos/month, basic report, no chat). Pro (~$7/mo,
unlimited-ish demos, full reports, chat, trends, auto-ingest). Team tier later.
Quota enforcement at the queue level, usage metering, customer portal, dunning.

**Why it matters**
LLM and parsing costs are real per-unit costs. Unmetered free usage is how this
product dies quietly with a large bill.

**Dependencies** Milestone 8.
**Difficulty** 3. Stripe webhooks are always more work than expected.
**Technologies** Stripe Checkout + Billing Portal + webhooks.
**Database changes** `Subscription`, `Plan`, `UsageRecord`, `QuotaCounter`.
**APIs** `POST /api/billing/checkout`, `/api/webhooks/stripe`, `GET /api/usage`.
**AI requirements** Per-generation cost tracking must already exist (M8) so you
can see gross margin per user, per plan, per day.
**Expected output** A working paywall and a dashboard showing revenue vs. LLM
spend.

---

## Milestone 13 — Production Hardening

**What gets built**
Observability (Sentry, structured logs, OpenTelemetry traces spanning web →
queue → worker → LLM), autoscaling worker pool, dead-letter queue with a replay
UI, rate limiting, abuse prevention (upload bombs, prompt injection via demo
player names — a real vector, since player names are attacker-controlled text
that reaches the LLM), backups + restore drill, load testing, a status page,
GDPR data export.

**Why it matters**
The first time 500 people upload at once should not be the first time you learn
what breaks.

**Dependencies** All.
**Difficulty** 4.
**Technologies** Sentry, Axiom or Better Stack, OTel, Grafana, k6, Upstash rate
limiting.
**Database changes** `AuditLog`, `SystemEvent`.
**APIs** `/api/admin/*` behind role checks.
**AI requirements** Prompt-injection defense: player names, clan tags and chat
text from demos are untrusted input. They must be delimited, escaped, and never
interpreted as instructions.
**Expected output** A documented runbook, a restore you have actually performed,
and a load test showing 100 concurrent parses without collapse.

---

## Milestone 14 — Growth Surfaces

**What gets built**
Public shareable match reports (OG images auto-generated per report — this is
the cheapest acquisition channel a product like this has), team/5-stack shared
workspaces, a Discord bot, referral credits, SEO map guides seeded by aggregate
data.

**Dependencies** Milestone 12.
**Difficulty** 3.
**Expected output** Organic signups you didn't pay for.

---

## Dependency graph

```
M0 Foundation
 └─ M1 Auth
     └─ M2 Upload + Queue
         └─ M3 Parsing ◀── the critical path
             ├─ M4 Match UI
             ├─ M6 Round Viewer
             └─ M5 Metrics
                 └─ M7 Insight Rules
                     └─ M8 LLM Reports ◀── the product
                         ├─ M9 Chat
                         ├─ M10 Auto-ingest
                         ├─ M11 Profiles
                         └─ M12 Billing
                             └─ M13 Hardening
                                 └─ M14 Growth
```

**The critical path is M0 → M1 → M2 → M3 → M5 → M7 → M8.** Everything else is
parallelizable or deferrable. If schedule slips, cut M6 and M9 before touching
that spine.

## Where the schedule risk actually is

1. **M3 parsing edge cases** — overtime, MR12 vs MR15, reconnects, POV demos,
   FACEIT vs Valve config differences. Mitigate by collecting 30 varied demos as
   a fixture corpus *before* writing the parser, not after.
2. **M8 output quality** — the gap between "it generates text" and "it generates
   good coaching" is the longest unmeasured stretch in this plan. Mitigate with
   the golden-set eval harness built at the same time as the first prompt.
3. **Unit cost** — if a match costs $2 to analyze, there is no business.
   Mitigate by tracking cost per report from the first generation and treating
   it as a product metric.
