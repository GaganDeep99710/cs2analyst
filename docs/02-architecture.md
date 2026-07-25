# Phase 2 — System Architecture

## Shape of the system

Three runtimes, one database, one queue between them.

```
                          ┌──────────────────────────┐
   Browser ──────────────▶│  Next.js 15 (Vercel)     │
   (React 19)             │  RSC pages, route        │
        │                 │  handlers, Auth.js,      │
        │  presigned PUT  │  SSE, AI SDK streaming   │
        │                 └───────┬──────────────────┘
        ▼                         │
  ┌────────────┐                  │ enqueue / read
  │ Cloudflare │                  ▼
  │     R2     │◀───────┐   ┌──────────┐     ┌──────────────┐
  │ demos,     │        │   │  Redis   │     │  Postgres    │
  │ blobs,     │        │   │ (Upstash)│     │  + pgvector  │
  │ radar imgs │        │   │ BullMQ,  │     │  (Neon)      │
  └────────────┘        │   │ cache,   │     └──────▲───────┘
                        │   │ pub/sub  │            │
                        │   └────┬─────┘            │
                        │        │ consume          │
                        │        ▼                  │
                        │  ┌────────────────────────┴──┐
                        └──│  Python worker pool        │
                  download │  (Fly.io / Railway)        │
                           │  parse → metrics → rules   │
                           └────────────┬───────────────┘
                                        │
                                        ▼
                                ┌───────────────┐
                                │ Anthropic API │
                                └───────────────┘
```

Why a **queue, not HTTP**, between web and worker: parsing takes 40–120 seconds
and 2–4 GB of RAM. That cannot live in a request. The queue also gives us
retries, backpressure, priority (paid users first) and independent scaling for
free.

---

## Frontend

**Next.js 15 App Router, React 19, TypeScript strict.**

- **Server Components by default.** Match pages, scoreboards and reports are
  read-heavy and largely static per match — fetch on the server, ship no
  client JS for them.
- **Client Components only where interaction demands it:** the uploader, the
  round viewer canvas, the chat window, filter controls.
- **State:** TanStack Query for server state that polls (job progress), Zustand
  for the round viewer's local playback state (tick, speed, selected player).
  No global store beyond that — most state is URL state, and the round viewer
  is deep-linkable precisely because tick/round live in the query string.
- **Styling:** Tailwind + shadcn/ui, dark-first. A CS2 audience expects dark.
- **Charts:** Recharts for standard charts; hand-rolled Canvas for the radar
  viewer and heatmaps. Do not put 400 nodes in SVG.
- **Streaming:** Vercel AI SDK `useChat`/`useCompletion` for report generation
  and chat, so users see tokens rather than a spinner. A 30-second silent wait
  reads as broken; a 30-second stream reads as thinking.
- **Rendering strategy:** landing/marketing static; dashboard dynamic; public
  shared reports ISR-cached with on-demand revalidation.

## Backend (Node)

Next.js Route Handlers, not a separate API server. There's no second consumer
of this API for a long time, and colocating removes a deployment and a network
hop. The seam that *does* exist — Node ↔ Python — is the queue.

- Zod validation at every boundary, inputs and outputs.
- Prisma as the sole DB access path from Node.
- A thin service layer (`lib/services/*`) so route handlers stay ~20 lines and
  business logic stays testable without HTTP.
- Errors: a typed `AppError` hierarchy mapped to HTTP codes centrally, so no
  handler ever hand-writes a status code.

## Python worker service

- FastAPI for a health/metrics endpoint; the real work is a BullMQ-compatible
  consumer loop (`bullmq` has a Python port, or use Redis streams directly with
  a small compatible protocol — pick one and document it).
- Stages inside one job, each idempotent and checkpointed: `download →
  decompress → parse → persist_events → compute_metrics → run_rules →
  build_replay_blobs → enqueue_report`.
- Checkpointing matters: a crash in `compute_metrics` on a 90-second parse
  should not re-parse. Stage completion is recorded on the `Job` row.
- Resource profile: 4 vCPU / 8 GB per worker, one job at a time. Parsing is
  memory-hungry and mostly single-threaded.
- Scale on queue depth, not CPU. Target: queue wait under 60 seconds at p95.

## Database

**Postgres 16 (Neon) with pgvector.** Details in
[03-database.md](03-database.md). Architectural notes:

- **One database, not a warehouse.** Event volume (~500k rows/match) is large
  but Postgres handles it fine with partitioning. Introducing ClickHouse before
  you have 10k matches is premature.
- `PlayerTick` and `Damage` partitioned by hash of `match_id`.
- Neon branching gives per-PR ephemeral databases in CI — genuinely useful for
  migration testing.
- Read replica once report reads compete with worker writes.
- **Retention policy from day one:** raw `.dem` files deleted after 30 days
  (free) / 180 days (pro); `PlayerTick` rows dropped after 90 days but replay
  blobs retained since they're 40× smaller. Storage is the sneaky cost center.

## Authentication

Auth.js v5, database sessions (not JWT — we need instant revocation for account
deletion and plan downgrades).

- **Steam OpenID 2.0** primary. Requires a custom provider; Steam returns only
  a SteamID64, so we enrich via `GetPlayerSummaries`.
- Email magic link (Resend) as fallback and for account recovery, since Steam
  gives us no email.
- Roles: `user`, `admin`. Team roles arrive with the team milestone.
- Authorization lives in the service layer via a single `assertCanAccess(user,
  resource)` helper. Never in the UI, and never — critically — expressed only
  in an LLM prompt.

## Storage

**Cloudflare R2**, three buckets:

| Bucket | Contents | Access | Lifecycle |
|---|---|---|---|
| `demos` | raw uploads | private, presigned | 30/180-day expiry |
| `artifacts` | replay blobs, heatmap PNGs, OG images | public-read via CDN | permanent |
| `static` | radar images, map metadata | public, immutable | permanent |

Uploads are presigned multipart directly from the browser. The server issues the
presign and later verifies the object exists and matches the declared hash — the
client is never trusted about what it uploaded.

## Queue

**BullMQ on Upstash Redis.** Queues:

- `parse` — heavy, concurrency = worker count, priority by plan.
- `report` — LLM generation, higher concurrency (IO-bound), separate so a
  parsing backlog never blocks report generation.
- `ingest` — polling Valve/FACEIT, scheduled repeatable jobs.
- `maintenance` — rollups, retention deletion, benchmark recomputation.

Dead-letter queue after 3 attempts with exponential backoff. Failed jobs are
inspectable and replayable from an admin page — not from a shell.

## Caching

Layered, cheapest first:

1. **Anthropic prompt caching** — system prompt + metric dictionary + tool
   schemas are identical across every request. Biggest cost lever in the system.
2. **Redis** — computed metrics, cohort benchmarks (recomputed nightly),
   session lookups, rate-limit counters.
3. **Next.js data cache / ISR** — public report pages, marketing.
4. **CDN** — replay blobs and radar images, immutable with hashed URLs.
5. **Browser** — replay blobs in IndexedDB so re-watching a round is instant.

Reports themselves are **generated once and stored**, never regenerated on read.
A report is an artifact, not a view.

## LLM integration

- Provider: Anthropic. **Sonnet 5** as the workhorse (round narratives, chat
  turns, findings prioritization); **Opus 4.8** for the headline match
  post-mortem and progress reports where reasoning depth shows; **Haiku 4.5**
  for cheap classification (title generation, intent routing, moderation).
- **Structured output via tool schemas**, never "return JSON please".
- **Prompt versioning** — every prompt is a versioned file; every generation
  records its version, model and token counts.
- **A cost ceiling per job.** A runaway agentic chat loop must hit a hard stop.
- **Eval harness** — golden set of demos with human-labeled expected findings;
  run on every prompt change; block deploy on regression.
- **Injection defense** — demo-derived strings (player names, clan tags, chat)
  are wrapped in delimiters, escaped, length-capped, and the system prompt
  states they are untrusted data. Player names are attacker-controlled: a name
  like `[ignore previous instructions]` will appear eventually.

## Deployment

| Component | Host | Rationale |
|---|---|---|
| Next.js | Vercel | Zero-config for this stack, good streaming support |
| Python workers | Fly.io | Cheap persistent CPU/RAM, scale-to-zero, regional |
| Postgres | Neon | Branching, autoscaling, pgvector included |
| Redis | Upstash | Serverless pricing, BullMQ compatible |
| Object storage | Cloudflare R2 | Zero egress — decisive here |

Environments: `local` (Docker Compose) → `preview` (per-PR, Neon branch) →
`production`. Migrations run as a gated deploy step, never automatically on boot.

## CI/CD

GitHub Actions:

1. **On PR:** lint (ESLint + Ruff), typecheck (tsc + mypy), unit tests, Prisma
   migration dry-run against a Neon branch, build, Playwright smoke on the
   preview URL.
2. **Parser regression job:** run the fixture corpus through the parser and diff
   metric output against committed snapshots. This is the most valuable test in
   the repo — it catches the silent-wrongness class of bug that unit tests miss.
3. **Eval job:** on any prompt file change, run the LLM golden set and post
   scores as a PR comment.
4. **On merge to main:** deploy web, build and deploy worker image, run
   migrations, smoke test, auto-rollback on health check failure.

## Monitoring

- **Errors:** Sentry, both runtimes, with release tracking and source maps.
- **Logs:** structured JSON with a `trace_id` threaded from the browser request
  through the queue job into the LLM call. Axiom or Better Stack.
- **Traces:** OpenTelemetry across the web → queue → worker → Anthropic span.
  Without this, "why did that match take 11 minutes?" is unanswerable.
- **Metrics dashboards:** queue depth and wait time, parse duration p50/p95,
  parse failure rate by map and demo source, LLM cost/day and cost/report,
  token cache hit rate, report generation latency, DB connection saturation.
- **Alerts:** queue depth > 100, parse failure rate > 5%, LLM daily spend over
  budget, p95 end-to-end > 10 min, any DLQ arrival.

## Analytics

PostHog (self-host or cloud). The events that matter are funnel and value
events, not vanity:

`signup → steam_linked → demo_upload_started → demo_upload_completed →
parse_completed → report_viewed → report_section_expanded →
report_feedback_given → chat_message_sent → round_viewer_opened →
second_demo_uploaded → subscribed`

The two north-star metrics: **% of uploads that reach a viewed report** (product
health) and **% of users who upload a second demo within 7 days** (value proof).
Plus per-section thumbs up/down, which doubles as the LLM quality signal.

## Error handling

- **Typed errors** across both runtimes, with stable machine-readable codes.
- **User-facing failures explain and offer a path.** "This demo is a POV
  recording; we need a GOTV demo — here's how to get one" is a support ticket
  avoided. Generic "Something went wrong" is unacceptable for parse failures
  because parse failures will be common early.
- **Partial success is a first-class state.** If metrics computed but the LLM
  failed, show the match page with the stats and a retry on the report. Never
  throw away 90 seconds of parsing because a generation timed out.
- **Idempotency everywhere.** Every job stage can rerun safely; webhook handlers
  key on event id.
- **Automatic failure capture:** a parse failure stores the demo hash, parser
  version and stack trace so the fixture corpus grows from real failures.

## Scaling strategy

Bottlenecks in the order they will actually bite:

1. **Worker CPU** (first, and by far). Horizontal: more Fly machines, scale on
   queue depth. Each machine handles ~30–40 demos/hour.
2. **LLM cost and rate limits** (second). Mitigations: prompt caching, model
   tiering, per-plan quotas, batching non-urgent generations.
3. **Postgres write throughput** from tick inserts (third). Mitigations: COPY
   instead of INSERT, partitioning, dropping tick retention, and eventually
   moving ticks out of Postgres entirely into columnar files in R2 (Parquet)
   read on demand. Design the tick access path behind an interface now so this
   swap is possible later.
4. **Postgres read load** (fourth). Read replica, materialized rollups.

Explicit non-goals for v1: multi-region, real-time live-match analysis,
self-serve on-prem. All three are large and none serve the core promise.

## Security

- **Upload safety:** validate magic bytes, cap size (500 MB), decompress with a
  bomb guard (ratio + absolute output cap), parse in a resource-limited
  container with no outbound network beyond R2 and Postgres. A demo file is
  untrusted input being fed to a native-code parser — treat it that way.
- **Access control** enforced in the service layer, with a test asserting every
  match endpoint 404s for a non-owner.
- **LLM tools are user-scoped at the implementation level**, so a prompt cannot
  talk the model into cross-user reads.
- **Prompt injection** from demo strings: delimit, escape, cap, and instruct.
- **Secrets** in the platform secret store; nothing in the repo; rotation
  documented.
- **Rate limits** per user and per IP on upload, chat and report generation.
- **PII** is minimal by design: SteamID, email, avatar. Documented data map,
  export and hard-delete flows. Demos contain other players' data too — the
  privacy policy must address that, and public sharing should anonymize
  non-consenting players' names by default.
- **Dependencies:** Dependabot, `pip-audit`, `npm audit` in CI.
