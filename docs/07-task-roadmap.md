# Phase 7 — Development Task Roadmap

240 tasks. Each sized under 3 hours. Ordered so that every task's dependencies
come before it, and so the product is in a demonstrable state at the end of each
block.

**How to use this:** give me one task number at a time. Each task states its
deliverable concretely enough to be implemented without re-deriving context.

Legend: 🔴 MVP-critical · 🟡 MVP · ⚪ post-MVP

---

## Block A — Foundation (Tasks 1–18) 🔴

1. Initialize pnpm workspace monorepo: `apps/web`, `services/parser`,
   `packages/shared`, root `package.json`, `pnpm-workspace.yaml`.
2. Scaffold Next.js 15 app in `apps/web` with App Router, TypeScript strict,
   `src/` layout, path aliases.
3. Configure ESLint 9 flat config + Prettier; add `lint` and `format` scripts;
   verify clean on the scaffold.
4. Install and configure Tailwind 3.4 with a custom theme: color tokens
   (background/surface/border/muted/accent, CT blue, T yellow, win green, loss
   red), font scale, radii.
5. Install shadcn/ui; add base components: button, card, dialog, dropdown,
   input, label, select, separator, tabs, toast, tooltip, skeleton, badge.
6. Build the app shell: root layout, dark theme via `next-themes` (dark
   default), font loading, global styles.
7. Create `packages/shared`: TypeScript config, build setup, empty export
   surface for types shared between web and generated parser contracts.
8. Docker Compose for local Postgres 16 with the `pgvector` extension enabled;
   document connection string.
9. Docker Compose for local Redis; verify connectivity from Node.
10. Initialize Prisma in `apps/web`; datasource, generator, first empty
    migration; add `prisma:*` scripts.
11. Write `src/env.ts` — Zod schema validating every env var, split
    server/client, imported at app boot so misconfiguration fails immediately.
12. Write `.env.example` documenting all variables with comments on where to
    obtain each.
13. Scaffold `services/parser`: Python 3.12, `uv`, `pyproject.toml`, Ruff +
    Black + mypy config, `src/` package layout.
14. Add FastAPI health endpoint to the parser service; Dockerfile; verify it
    runs locally.
15. Implement `GET /api/health` in Next.js checking Postgres, Redis and R2
    reachability, returning per-dependency status.
16. GitHub Actions workflow: install, lint, typecheck, build on every PR (Node).
17. GitHub Actions workflow: Ruff, mypy, pytest for the parser service.
18. Write root `README.md` with local setup instructions verified from a clean
    clone.

## Block B — Authentication (Tasks 19–32) 🔴

19. Prisma schema: `User`, `Account`, `Session`, `VerificationToken` per Auth.js
    v5; migrate.
20. Prisma schema: `SteamProfile` with unique `steamId64` and `userId`; migrate.
21. Install Auth.js v5 with the Prisma adapter; configure database sessions.
22. Implement a custom Steam OpenID 2.0 provider (realm/return-to construction,
    signature verification, SteamID64 extraction).
23. Steam Web API client: `GetPlayerSummaries`; typed response; error handling
    and timeout.
24. On sign-in, upsert `SteamProfile` from the Steam profile response; store
    avatar, persona name, country.
25. Add the email magic-link provider via Resend; design the verification email.
26. Middleware protecting `/app/*`; redirect unauthenticated users to sign-in
    preserving the intended destination.
27. Sign-in page: Steam button (with the official branding asset), email fallback
    form, error states for each failure mode.
28. Header user menu: avatar, display name, links to settings and sign-out.
29. `GET /api/me` returning the session user plus Steam profile.
30. `DELETE /api/me`: cascade-delete all user data; require typed confirmation;
    write an audit log row.
31. `/app/settings/account` page: profile display, Steam link status, delete
    account flow.
32. Integration test: full sign-in → session → protected route → sign-out cycle.

## Block C — Storage & Upload (Tasks 33–50) 🔴

33. Provision Cloudflare R2; create `demos`, `artifacts`, `static` buckets;
    configure CORS for direct browser uploads.
34. R2 client wrapper in `lib/storage`: presign multipart, complete, abort,
    head-object, delete, presigned GET.
35. Prisma schema: `Demo` (sha256 unique, storage key, size, compression,
    source, status, expiresAt) and `DemoOwner` join table; migrate.
36. `POST /api/demos/presign`: validate filename/size/hash, check for an
    existing demo by hash, return either a dedupe hit or presigned part URLs.
37. Client-side SHA-256 hashing in a Web Worker with streaming and progress
    reporting.
38. Multipart upload client: chunking, parallel part upload, per-part retry,
    overall progress and speed calculation.
39. Upload resume: persist upload state to IndexedDB; on page load, offer to
    resume incomplete uploads.
40. `POST /api/demos/complete`: finalize multipart, verify object size and magic
    bytes server-side, create the `Demo` row, enqueue a parse job.
41. Dropzone component: drag/drop, click-to-browse, file type and size
    validation, error display.
42. Upload progress component: per-file card with progress bar, speed, ETA,
    cancel.
43. `/app/upload` page composing the dropzone and progress list.
44. Help content on the upload page: where demo files live, how to download a
    Premier demo, POV vs GOTV explained.
45. `GET /api/demos` — paginated list scoped to the user with filters; and
    `GET /api/demos/:id`.
46. `DELETE /api/demos/:id` — remove ownership; delete the object only when no
    owners remain.
47. Install BullMQ; create the queue module with `parse`, `report`, `ingest`,
    `maintenance` queues and shared Redis connection config.
48. Prisma schema: `Job` (type, status, stage, attempt, priority, error fields,
    timings, workerId, parserVersion); migrate.
49. Job lifecycle service: create, transition (with legal-transition
    validation), fail, retry, complete.
50. Rate limiting on the upload endpoints (per user and per IP) using Upstash.

## Block D — Parser Foundations (Tasks 51–72) 🔴

51. Collect a fixture corpus: 15+ demos spanning 5 maps, MR12 and MR15,
    overtime, a disconnect case, FACEIT and Valve sources. Store in R2, document
    each one's characteristics.
52. Install `demoparser2` and `awpy` in the parser service; parse a fixture and
    print the header — the first real proof of life.
53. Define Pydantic models for the full parser output contract (match, players,
    rounds, kills, damages, grenades, bomb events, ticks).
54. Generate TypeScript types from the Pydantic models into `packages/shared` so
    web and parser cannot drift.
55. Worker entrypoint: Redis consumer loop, job claim, heartbeat, graceful
    shutdown on SIGTERM.
56. Job stage checkpointing: record completed stages on the `Job` row; resume
    from the last checkpoint on retry.
57. Demo download stage: stream from R2 to a temp path with progress reporting
    and disk-space guard.
58. Decompression stage: bz2 and gz support with a compression-ratio bomb guard
    and absolute output size cap.
59. Demo validation: magic bytes, header sanity, POV-vs-GOTV detection, player
    count check; emit typed rejection reasons.
60. Extract match header: map, tickrate, server name, date, duration, mode
    inference, MR12/MR15 detection.
61. Extract players: SteamID64, names, clan tags, team assignment per half, bot
    detection, connect/disconnect rounds.
62. Extract rounds: start/freeze-end/end/official-end ticks, winner, end reason;
    filter out warmup and knife rounds.
63. Handle overtime: side swaps every 3 rounds, score reconciliation, round
    numbering continuity.
64. Extract kills with full detail: participants, weapon, flags (HS, wallbang,
    through-smoke, no-scope, blind), positions, view angles, distance.
65. Extract damage events: attacker, victim, weapon, HP/armor damage, hitgroup,
    team-damage flag, positions.
66. Extract grenade events: throw and detonation ticks, positions, throw angles,
    type; correlate throw to detonation.
67. Extract flash events: per-victim blind duration, teammate/self detection,
    whether the victim was facing the flash.
68. Extract molotov/incendiary damage and smoke detonation volumes.
69. Extract bomb events including `began_plant`, `began_defuse`, aborts, and
    kit possession.
70. Extract and decimate player ticks to 4 Hz: position, angles, HP, armor,
    active weapon, flags, equipment value.
71. Parser CLI: `parse <demo> --out json`, printing a round-by-round summary for
    manual eyeball verification against the in-game demo.
72. Parser unit tests against 3 fixtures asserting round counts, final scores and
    kill totals.

## Block E — Enrichment (Tasks 73–88) 🔴

73. Import radar images and map metadata (`.txt` offsets/scale) for the 5 MVP
    maps into the `static` bucket.
74. Implement world-coordinate → radar-pixel transform per map; verify by
    plotting known positions against the radar image.
75. Author callout polygons for Mirage (~30 zones) as a JSON data file.
76. Author callout polygons for Inferno.
77. Author callout polygons for Dust2.
78. Author callout polygons for Ancient.
79. Author callout polygons for Nuke (including the two levels — Z matters
    here, unlike the other four).
80. Zone resolver: point-in-polygon lookup with a spatial index; unit-tested
    against hand-labeled coordinates.
81. Apply zone labels to all kill, death, grenade and tick positions.
82. Opening duel detection: first kill per round, tagged for attacker and victim,
    with zone and side.
83. Trade detection: link a kill to a prior teammate death within 3 seconds and
    ~500 units; record the traded kill id both directions.
84. Buy-type classification per team per round from equipment value and loss
    bonus (pistol/eco/semi/force/full).
85. Round-phase segmentation (freeze, early, mid, late, post-plant) applied to
    all events.
86. Execute detection: clustered utility toward one site followed by entry within
    a window.
87. Death-location clustering per player per map (DBSCAN over coordinates) with
    a configurable epsilon.
88. Enrichment test suite: hand-verify opening duels and trades on one fixture
    round by round.

## Block F — Persistence (Tasks 89–100) 🔴

89. Prisma schema: `Match`, `MatchPlayer`; migrate; indexes per the DB design.
90. Prisma schema: `Round`; migrate.
91. Prisma schema: `Kill`, `Damage` with hash partitioning on `matchId`;
    migrate (raw SQL for partitioning; Prisma won't express it).
92. Prisma schema: `Grenade`, `FlashEvent`, `BombEvent`; migrate.
93. Prisma schema: `PlayerTick` partitioned by `matchId`; migrate.
94. Python DB layer: SQLAlchemy Core or asyncpg connection management, matching
    the Prisma-generated schema.
95. Bulk insert via `COPY` for kills, damages, grenades and ticks; benchmark
    against a real match (target: under 10 seconds for the full write).
96. Idempotent persistence: delete-then-insert per stage scoped to `matchId` so
    retries never duplicate.
97. Persist stage wired into the worker pipeline with checkpointing.
98. Progress publishing: worker writes stage progress to Redis pub/sub with
    round-level granularity.
99. `GET /api/jobs/:id` returning status and stage; `GET /api/jobs/:id/stream`
    as SSE bridging the Redis channel.
100. End-to-end test: upload a fixture through the real API, confirm the parse
     completes and all event rows land correctly.

## Block G — Match UI (Tasks 101–116) 🔴

101. Processing page with staged progress driven by the SSE endpoint, including
     the live round counter.
102. Processing page failure states with specific, actionable copy per error
     code.
103. `GET /api/matches/:id` returning header, players and scores, access-checked.
104. Match header component: map image, score with half split, date, mode,
     duration.
105. `GET /api/matches/:id/scoreboard`; scoreboard table component sortable by
     column, with team grouping and side coloring.
106. `GET /api/matches/:id/rounds`; round timeline strip with win/loss coloring
     and end-reason icons.
107. Round detail expansion: kill feed with weapon icons and timestamps.
108. Economy chart across rounds for both teams (Recharts).
109. `/app/matches/:id` page assembling header, timeline, scoreboard, economy.
110. Demo library list rows: map, date, score, result color, status pill.
111. Demo library filters: map, result, date range, status; URL-synced.
112. `/app` dashboard: latest match card, match list, header dropzone.
113. Dashboard empty state with the "how to find your demos" guide and a
     sample-report link.
114. Loading skeletons matching the final layout for match page and library.
115. Mobile layout pass on match page: stacked scoreboard cards, scrollable
     timeline.
116. **Validation task:** compare the scoreboard for 5 fixtures against
     CSStats/Leetify for the same demos; document and fix every discrepancy.
     *This is a gate — do not proceed to metrics until it passes.*

## Block H — Metrics Engine (Tasks 117–140) 🔴

117. Prisma schema: `MetricDefinition`, `PlayerRoundStats`, `PlayerMatchStats`,
     `TeamRoundStats`; migrate.
118. Seed `MetricDefinition` rows for all MVP metrics with LLM-facing
     descriptions, units, direction and minimum sample size.
119. Metrics module scaffold in Python: load events into DataFrames, per-metric
     registry, output validation.
120. Core combat metrics: kills, deaths, assists, K/D, ADR, HS%.
121. KAST computation per round and per match.
122. HLTV-2.0-style rating implementation, documented, with the formula recorded
     in the metric definition.
123. Opening duel metrics: attempts, wins, losses, win rate, split by side.
124. Opening duel metrics segmented by map zone with sample sizes.
125. Trade metrics: trade kills, deaths traded, trade participation rate,
     untraded-death count.
126. Multi-kill counts (2k–5k) and clutch attempts/wins by situation size.
127. Utility damage and enemies-flashed metrics with blind-duration buckets.
128. Teammate-flash and self-flash metrics including total blind duration
     inflicted on teammates.
129. Unused-utility metrics: count and dollar value of grenades held at death,
     and the percentage of rounds where it exceeded a threshold.
130. Utility timing metrics: average throw time relative to round start and to
     execute start.
131. Positional metrics: deaths by zone, kills by zone, average time to first
     contact, distance traveled per round.
132. Economic metrics: buy type per round, spend efficiency, economic damage,
     save discipline.
133. Team metrics: site hit distribution, execute count and success rate,
     retake success by site, post-plant conversion.
134. Per-round stats writer producing `PlayerRoundStats` rows.
135. Per-match aggregation producing `PlayerMatchStats` rows.
136. Self-benchmarking: compute each metric against the player's trailing 20
     matches; emit delta and percentile.
137. Sample-size propagation: every metric emits `n`; anything below
     `minSampleSize` is flagged low-confidence.
138. Metrics stage wired into the worker pipeline with checkpointing.
139. Metric snapshot regression tool: dump all metrics for the fixture corpus to
     committed JSON; CI diffs on every change.
140. `GET /api/matches/:id/metrics` scoped to the requesting user.

## Block I — Insight Rules (Tasks 141–160) 🔴

141. Prisma schema: `InsightRule`, `Finding`, `FindingCitation`; migrate.
142. Rule engine scaffold: registry, base rule interface, threshold config
     loading from the database, finding emission with citations.
143. Rule — **unused utility at death** (count and value thresholds).
144. Rule — **opening duel leak**, overall, with a minimum attempt count.
145. Rule — **zone-specific opening duel leak** (localized to a callout).
146. Rule — **untraded deaths** (dying away from teammates repeatedly).
147. Rule — **failure to trade teammates** (present but no trade attempt).
148. Rule — **repeated death location** from the DBSCAN clusters.
149. Rule — **teammate flashing** above a duration threshold.
150. Rule — **self-flashing** frequency.
151. Rule — **late utility** (smokes/flashes thrown after the execute began).
152. Rule — **force-buy losses** and their economic cost.
153. Rule — **clutch conversion** below expectation, broken down by situation.
154. Rule — **side asymmetry** (materially worse on CT or T).
155. Rule — **over-peeking / early aggression deaths** in the first 20 seconds.
156. Rule — **low utility usage** overall (throwing far fewer nades than peers or
     than own average).
157. Rule — **strength detection** (at least one positive finding; the report
     requires one).
158. Finding ranking: composite score over severity, confidence, recency,
     actionability and novelty.
159. Citation generation: every finding resolves to concrete round ids and ticks;
     validated at write time.
160. Rules test suite: hand-label expected findings for 5 fixtures; assert the
     engine reproduces them.

## Block J — LLM Reports (Tasks 161–184) 🔴

161. Prisma schema: `Report`, `ReportSection`, `LlmGeneration`, `PromptVersion`;
     migrate.
162. Anthropic client wrapper: retries with backoff, timeout, token accounting,
     cost calculation per model, structured error types.
163. Prompt versioning system: prompts as versioned files with a hash, recorded
     on every generation.
164. Context pack builder — identity and match summary sections.
165. Context pack builder — player metrics section with values, percentiles and
     sample sizes.
166. Context pack builder — findings section with evidence and citations.
167. Context pack builder — round digest (one compact line per round).
168. Context pack builder — metric glossary assembled from `MetricDefinition`,
     scoped to metrics actually present.
169. Token budgeting: measure the pack, drop lowest-ranked findings until it fits
     the ceiling, log what was dropped.
170. Input sanitization: escape and delimit all demo-derived strings (player
     names, clan tags); cap lengths; add the untrusted-data system instruction.
171. Prompt-cache structure: split the request so system prompt, glossary and
     tool schemas are cacheable, and verify cache hits in the usage response.
172. Write the system prompt: coach persona, specificity requirements, no
     arithmetic, mandatory citations, explicit anti-pattern examples.
173. Define the structured output tool schema: verdict, mistakes (with
     `finding_ids`, explanation, drill), strength.
174. Report generation service: build pack → call model → parse structured
     output → persist report and sections.
175. Model routing: Opus 4.8 for the verdict, Sonnet 5 for mistakes and drills;
     configurable per section.
176. Citation validator: verify every cited round and finding id exists; reject
     on failure.
177. Numeric validator: verify every number in the output appears in the context
     pack within a rounding tolerance.
178. Regeneration on validation failure with the validator's complaint appended;
     degrade to findings-only after a second failure.
179. Cost and latency recording per generation into `LlmGeneration`.
180. `POST /api/matches/:id/report` — enqueue generation; `GET /api/reports/:id`.
181. `GET /api/reports/:id/stream` — stream sections to the client as they
     complete.
182. Report generation stage wired into the worker pipeline after rules.
183. Golden-set eval harness: 20 labeled demos, scored on finding overlap,
     citation validity and an LLM-judge specificity rubric.
184. CI job running the eval harness on any prompt file change, posting scores as
     a PR comment.

## Block K — Report UI (Tasks 185–200) 🔴

185. Verdict block component — the headline claim, largest element on the page.
186. Mistake card component: collapsed claim + number, expanded explanation,
     metric with percentile and sample size, drill.
187. Round citation chip component: renders inline, links to the round snapshot.
188. Strength card component.
189. Server-rendered round snapshot PNG: radar background, player positions at a
     tick, death markers, caption. Cached in the `artifacts` bucket.
190. `GET /api/rounds/:id/snapshot` returning the cached image, generating on
     miss.
191. Round snapshot modal opened from citation chips, with the round's event log.
192. Streaming report renderer: sections appear as they generate, with skeletons
     for pending sections.
193. Per-section thumbs up/down with optimistic UI; `POST /api/feedback`.
194. Assemble `/app/matches/:id` report view: verdict, mistakes, strength,
     timeline, scoreboard.
195. Public share links: `/r/:token` with access control, teammate-name
     anonymization toggle, and no-signup viewing.
196. Auto-generated OG image per report showing the verdict.
197. Landing page: hero, comparison block, how-it-works, pricing placeholder,
     FAQ, footer.
198. Public sample report seeded from a real demo, linked from the landing page
     and every empty state.
199. Mobile pass on the report page: single column, collapsible sections,
     readable snapshots.
200. Accessibility pass: keyboard navigation, focus states, contrast audit
     against WCAG AA, screen-reader labels on all interactive elements.

## Block L — MVP Launch Readiness (Tasks 201–212) 🟡

201. Sentry in both runtimes with release tracking and source maps.
202. Structured logging with a `traceId` threaded from request through job to
     LLM call.
203. Admin page listing jobs with status, duration, errors, and a retry action.
204. Admin page listing failed parses with the demo hash and stack trace, plus
     one-click addition to the fixture corpus.
205. PostHog with the full funnel event set defined in the architecture doc.
206. Demo quota enforcement (5 per user) with a clear limit-reached state.
207. Retention job: delete demo objects past `expiresAt`; scheduled via the
     maintenance queue.
208. Production deploy of the web app to Vercel with environment configuration.
209. Production deploy of the worker to Fly.io with autoscaling on queue depth.
210. Production database and Redis provisioning; migration deploy step in CI.
211. Load test: 25 concurrent parses; record queue wait, parse duration and
     failure rate; fix what breaks.
212. Launch checklist: privacy policy, terms, Discord server, feedback channel,
     status page.

---
---

## POST-MVP

## Block M — Round Replay Viewer (Tasks 213–226) ⚪

213. Replay blob format spec: binary layout for per-round tick data
     (Float32Array), documented with a version byte.
214. Blob generation in the worker; upload to the `artifacts` bucket; store the
     reference.
215. `GET /api/rounds/:id/replay` returning the blob URL and metadata; client
     caches in IndexedDB.
216. Canvas renderer: radar background, correct scaling, pan and zoom.
217. Player dot rendering: team color, view cone, name label, HP ring, death
     state.
218. Tick interpolation for smooth playback between 4 Hz samples.
219. Playback engine: play/pause, speed control, seek, frame stepping.
220. Timeline scrubber with event markers and hover preview.
221. Grenade rendering: trajectories, smoke circles with true radius, molotov
     footprints, flash bursts.
222. Bomb rendering: carrier indicator, plant location, defuse timer.
223. Keyboard shortcuts and a discoverable shortcut overlay.
224. Left rail round event log, clickable to seek.
225. Right rail showing findings that cite the current round.
226. Mobile-reduced viewer: pinch-zoom, simplified controls, desktop hint.

## Block N — AI Chat (Tasks 227–240) ⚪

227. Prisma schema: `Conversation`, `Message`, `ToolCall`, `Embedding` with
     pgvector and an HNSW index; migrate.
228. Tool: `get_player_metrics` — user-scoped at construction, typed schema.
229. Tool: `query_rounds` — filter by outcome, side, buy type, economy.
230. Tool: `get_round_timeline` — full event sequence for a round.
231. Tool: `find_deaths` — filter by zone, weapon, phase, opening/traded.
232. Tool: `get_grenades` — filter by type, thrower, phase, effectiveness.
233. Tool: `get_findings` — findings for a match or across matches.
234. Tool: `search_history` — pgvector similarity over the user's own round
     summaries and findings, with a mandatory user filter.
235. Chat agent loop: tool use, turn cap, per-conversation cost ceiling,
     streaming.
236. `POST /api/chat` with streaming response and per-user rate limiting.
237. Chat UI: message list, streaming rendering, input, conversation sidebar with
     auto-generated titles.
238. Tool-call transparency line ("Looked at 24 rounds, 8 opening duels"),
     collapsible.
239. Inline citation chips in chat answers with hover preview and click-to-open.
240. Suggested questions generated from the user's actual findings; scope
     selector (this match / last 10 / all time).

---

## Beyond Task 240

The remaining milestones decompose the same way and are deliberately left
un-enumerated until the MVP results are in — the shape of tasks 241+ should be
informed by what real users do, not decided today.

- **Auto-ingest (M10):** ~20 tasks — Steam share-code chain walking, FACEIT
  OAuth and webhooks, connection management, polling scheduler.
- **Profiles and trends (M11):** ~18 tasks — aggregates, streak tracking, role
  inference, trend charts, progress reports.
- **Billing (M12):** ~16 tasks — Stripe integration, plans, quotas, portal,
  webhooks, dunning.
- **Hardening (M13):** ~22 tasks — OTel tracing, DLQ replay UI, backup and
  restore drill, abuse prevention, status page, GDPR export.
- **Growth (M14):** ~15 tasks — teams, Discord bot, referrals, SEO map guides.
- **Cohort benchmarks:** ~10 tasks — only viable once there's a real corpus of
  matches, which is why they're absent from the MVP.

## Sequencing notes

- **Tasks 51 and 116 are gates.** 51 (fixture corpus) must be genuinely done
  before the parser work, or every later task is debugged against a single demo
  and breaks on the second. 116 (external validation of the scoreboard) must
  pass before any metric work, or you will build sophisticated analysis on wrong
  numbers and not find out for weeks.
- **Blocks G and H can overlap** — the match UI and the metrics engine touch
  different code.
- **Block M (viewer) is fully parallel** to Blocks H–L and can be picked up
  whenever there's appetite for something visual.
- **Do not start Block N (chat) before the MVP feedback is in.** Chat quality is
  bounded by report quality; building it early means rebuilding it.
