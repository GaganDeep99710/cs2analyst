# Phase 3 — Database Design

Postgres 16 + pgvector. Prisma-managed migrations. All ids are `cuid2` except
event tables, which use `bigserial` (billions of rows; 24-byte string keys there
would be wasteful and would hurt index locality).

Conventions: `snake_case` in the DB with Prisma `@map`, `created_at`/`updated_at`
on every table, soft delete only where recovery matters (`User`, `Demo`), hard
delete everywhere else.

---

## Group A — Identity & Accounts

### `users`
Root of ownership. Every other user-scoped row cascades from here.
`id, email (unique, nullable — Steam users may have none), email_verified,
display_name, avatar_url, role (user|admin), created_at, updated_at,
deleted_at, last_seen_at`
**Indexes:** unique on `email`; `last_seen_at` for activity queries.
**Why:** GDPR deletion needs one root; Steam-only accounts need nullable email.

### `accounts`, `sessions`, `verification_tokens`
Auth.js standard tables. `accounts` holds the OAuth/OpenID linkage
(`provider`, `provider_account_id`), unique on `(provider, provider_account_id)`.
**Why:** database sessions give instant revocation, which JWTs don't.

### `steam_profiles`
`id, user_id (unique FK), steam_id_64 (unique), persona_name, avatar_url,
profile_url, country, last_synced_at`
**Indexes:** unique `steam_id_64`, unique `user_id`.
**Why this is separate from `users`:** `steam_id_64` is the join key between a
human account and the anonymous player rows inside every parsed demo. It's the
hinge of the entire product — a teammate who never signs up still appears in
demos by SteamID, and the day they register, their history is already there.
Keeping it in its own table also lets a user link/unlink without touching the
account root.

---

## Group B — Demos & Jobs

### `demos`
The uploaded artifact, distinct from the match it contains.
`id, uploader_id FK users, sha256 (unique), original_filename, size_bytes,
storage_key, compression (none|bz2|gz), source (manual|valve|faceit|esea),
source_ref, status, uploaded_at, expires_at, deleted_at`
**Indexes:** unique `sha256`; `(uploader_id, uploaded_at desc)` for the library
list; `expires_at` partial where `deleted_at is null` for the retention job.
**Why separate from `matches`:** the same match can be uploaded by five people.
Content-hash dedupe means one parse, five owners. That relationship needs a join
table:

### `demo_owners`
`demo_id, user_id, added_at` — composite PK.
**Why:** many-to-many between demos and the users who claim them. Without this,
dedupe would silently give one uploader's demo to another user or force
duplicate parsing.

### `jobs`
`id, demo_id FK, type (parse|report|ingest|rollup), status, stage,
attempt, max_attempts, priority, error_code, error_message, error_detail jsonb,
queued_at, started_at, finished_at, duration_ms, worker_id, parser_version`
**Indexes:** `(status, priority desc, queued_at)` for the poller;
`(demo_id, type)`; partial index on `status = 'failed'` for the DLQ view.
**Why `stage` and `parser_version`:** stage enables checkpoint resume so a
crash doesn't re-parse; `parser_version` lets you find every match that needs
reprocessing after a parser bug fix — which will happen, repeatedly.

---

## Group C — Match Core

### `matches`
`id, demo_id (unique FK), map_name, tickrate, server_name, match_date,
duration_seconds, mode (premier|competitive|faceit|esea|scrim),
max_rounds (24|30), overtime_rounds, team_a_score, team_b_score,
team_a_name, team_b_name, has_overtime, parsed_at, parser_version`
**Indexes:** unique `demo_id`; `(map_name, match_date desc)`; `match_date desc`.
**Why:** the demo is the file; the match is the game. Separating them keeps
"delete the raw file after 30 days but keep the analysis forever" trivial —
which is the retention policy that makes storage costs survivable.

### `match_players`
One row per player per match. The bridge between anonymous demo data and users.
`id, match_id FK, steam_id_64, user_id (nullable FK), name, clan_tag,
team (a|b), starting_side (ct|t), rank, is_bot, connected_rounds,
disconnected_at_round`
**Indexes:** `(match_id, steam_id_64)` unique; `(steam_id_64, match_id)` for
"all matches for this player"; `(user_id)` partial where not null.
**Why nullable `user_id`:** most players in any demo have no account. We still
compute their stats. Backfilling `user_id` on signup turns "I just registered"
into "here are your last 40 matches" — a powerful onboarding moment.
**Why `connected_rounds`:** every per-round rate metric must divide by rounds
actually played, or a player who joined at round 12 shows a fake 50% opening
duel rate.

### `rounds`
`id, match_id FK, round_number, start_tick, freeze_end_tick, end_tick,
official_end_tick, winner_team, end_reason (t_win|ct_win|bomb_defused|
bomb_exploded|time_expired|elimination), bomb_planted, bomb_site (a|b|null),
plant_tick, defuse_tick, ct_score_before, t_score_before,
ct_equip_value, t_equip_value, ct_buy_type, t_buy_type, duration_seconds`
**Indexes:** `(match_id, round_number)` unique.
**Why:** the round is the atomic unit of CS analysis and the unit of citation.
Every AI claim points at a round. Denormalizing scores and economy onto it
avoids recomputation on every read.

---

## Group D — Events (high volume)

These are the tables that grow. All partitioned by `HASH(match_id)` into 16
partitions.

### `kills`
`id bigserial, match_id, round_id, tick, game_time,
attacker_steam_id, victim_steam_id, assister_steam_id,
flash_assister_steam_id, weapon, weapon_class, headshot, penetrated,
thru_smoke, no_scope, attacker_blind, victim_blind_duration,
attacker_x/y/z, victim_x/y/z, attacker_yaw, victim_yaw, distance,
attacker_zone, victim_zone, is_opening_kill, is_trade_kill,
traded_kill_id (self FK), is_first_kill_of_round, attacker_hp_remaining`
**Indexes:** `(round_id, tick)`; `(match_id, attacker_steam_id)`;
`(match_id, victim_steam_id)`; partial on `is_opening_kill`.
**Why the denormalized flags:** `is_opening_kill`, `is_trade_kill` and the
zone labels are computed once at parse time. Recomputing them per query would
make the metrics layer unusably slow, and they're immutable once written.
**Why `traded_kill_id`:** trade analysis needs the link, not just a boolean —
"you failed to trade *this specific death*" is a citable insight.

### `damages`
`id bigserial, match_id, round_id, tick, attacker_steam_id, victim_steam_id,
weapon, hp_damage, armor_damage, hitgroup, is_team_damage,
attacker_x/y/z, victim_x/y/z, distance`
**Indexes:** `(round_id)`; `(match_id, attacker_steam_id)`.
**Why separate from kills:** ADR, utility damage, and "you did 87 damage across
three players and got nothing" all need non-fatal hits. Highest-volume table
after ticks — ~4k rows/match.

### `grenades`
`id bigserial, match_id, round_id, thrower_steam_id, grenade_type
(smoke|flash|he|molotov|incendiary|decoy), throw_tick, detonate_tick,
throw_x/y/z, throw_yaw, throw_pitch, detonate_x/y/z, throw_zone,
detonate_zone, is_jump_throw, is_run_throw, total_damage,
enemies_flashed, teammates_flashed, self_flashed,
max_enemy_flash_duration, max_teammate_flash_duration,
round_phase (freeze|early|mid|late|post_plant), lineup_match_id`
**Indexes:** `(round_id)`; `(match_id, thrower_steam_id, grenade_type)`.
**Why so wide:** utility is the single richest source of actionable coaching and
the least understood by players. Teammate-flash and self-flash counts are among
the most diagnostic numbers in the product. `round_phase` enables "you throw
your smokes 8 seconds too late", which is a real, common, fixable mistake.

### `flash_events`
`id, grenade_id FK, victim_steam_id, duration, is_teammate, victim_x/y/z,
was_looking_at_flash`
**Why a separate table:** one flash blinds N players for different durations.
Modeling it as columns on `grenades` loses the per-victim detail that makes
flash coaching specific.

### `bomb_events`
`id, match_id, round_id, tick, event_type (planted|defused|exploded|
began_plant|began_defuse|aborted_plant|aborted_defuse), player_steam_id,
site, x/y/z, has_kit`
**Why the `began_*`/`aborted_*` events:** fake plants and aborted defuses are
tactically meaningful and invisible if you only record completions.

### `player_ticks`
The volume monster. Decimated to 4 Hz (every 16th tick at 64-tick).
`match_id, round_id, tick, steam_id_64, x, y, z, yaw, pitch, hp, armor,
has_helmet, has_defuser, active_weapon, is_ducking, is_scoped, is_walking,
is_airborne, equipment_value, zone`
**Primary key:** `(match_id, tick, steam_id_64)`.
**Indexes:** `(round_id, tick)`. Deliberately few — this table is written in
bulk via COPY and read in sequential ranges, so extra indexes cost more on
write than they save on read.
**Why 4 Hz:** at 64 tick × 10 players × 35 rounds × 115s you'd have ~2.5M rows
per match. At 4 Hz it's ~160k, which is enough for movement analysis, heatmaps
and a smooth interpolated replay. **This decision alone is a 16× cost
difference across storage, write throughput and query time.**
**Retention:** dropped after 90 days; the replay blob survives.

---

## Group E — Metrics

### `metric_definitions`
A registry, not a data table. `id, key, display_name, unit, category,
direction (higher_better|lower_better|neutral), description, formula_doc,
min_sample_size, version`
**Why it exists:** three consumers need one source of truth — the UI (labels,
formatting), the LLM (`description` is injected into the prompt so the model
knows what `kast` means without being told in prose), and the rules engine
(`min_sample_size` prevents claims from tiny samples). Without this table, the
definition of every metric gets duplicated in three places and drifts.

### `player_match_stats`
One row per player per match, ~60 computed columns (adr, kast, hs_pct,
opening_attempts/wins, trade_kills, trades_received, utility_damage,
enemies_flashed, teammates_flashed, self_flashes, unused_utility_value,
clutch_attempts/wins by size, multi_kills 2k–5k, rating, impact,
avg_time_to_death, deaths_traded_pct, …).
**Indexes:** `(match_id, steam_id_64)` unique; `(steam_id_64, match_id)`.
**Why a wide table instead of tall key-value:** the read pattern is "give me all
stats for this player in this match", always. Wide is one row; tall is 60 rows
and a pivot. Adding a column is a migration, which is fine and desirable —
metrics should be schema, not soup.

### `player_round_stats`
Per player per round: `kills, deaths, assists, damage, was_opening_kill,
was_opening_death, was_traded, traded_someone, survived, was_clutch,
clutch_size, clutch_won, utility_thrown, utility_unused_value,
equipment_value, spent, kast_contribution, time_alive, distance_traveled`
**Indexes:** `(round_id, steam_id_64)` unique; `(match_id, steam_id_64)`.
**Why:** this is the table the rules engine actually scans. "Died with utility
in 40% of rounds" is a one-line aggregate here and an expensive join otherwise.

### `team_round_stats`
Team-level per round: equipment, buy type, utility thrown, site hit, execute
detected, map control estimate, players alive over time.

### `metric_values`
Tall table for *derived* metrics that are computed over windows rather than per
match: `subject_type (player|team), subject_id, metric_key, window
(match|last_5|last_20|season), value, sample_size, percentile_self,
percentile_cohort, cohort_id, computed_at`
**Indexes:** `(subject_type, subject_id, metric_key, window)` unique.
**Why tall here but wide above:** these are sparse, arrive over time, and are
queried one metric at a time for trend charts. Different access pattern,
different shape.

### `benchmark_cohorts` / `cohort_metrics`
`cohort_id, name, rank_min, rank_max, map_name, mode` and per-cohort
percentile distributions (p10/p25/p50/p75/p90) per metric, recomputed nightly.
**Why:** "your ADR is 68" means nothing. "Your ADR is 68, which is p31 for
Premier 15–18k on Mirage" is coaching. Precomputing distributions makes
percentile lookup O(1) instead of a scan over every match ever played.

---

## Group F — Insights & Reports

### `insight_rules`
`id, key, name, category, description, severity_default, version,
enabled, threshold_config jsonb`
**Why in the DB rather than only in code:** thresholds need tuning without a
deploy, and every `finding` must reference the exact rule version that produced
it so you can explain historical findings after a threshold change.

### `findings`
The bridge between deterministic analysis and the LLM.
`id, match_id, subject_type (player|team), subject_steam_id, rule_id FK,
rule_version, severity (info|minor|moderate|major|critical),
confidence (0–1), title, evidence jsonb, metric_snapshot jsonb,
sample_size, created_at`
**Indexes:** `(match_id, subject_steam_id, severity desc)`;
`(rule_id, created_at)` for rule-level analytics.
**Why `evidence` and `metric_snapshot` are frozen JSON:** a finding must remain
explainable even after the underlying metric tables are pruned at 90 days. The
finding is the durable artifact.

### `finding_citations`
`id, finding_id FK, round_id, tick, kill_id (nullable), grenade_id (nullable),
label`
**Why:** this is the "watch this" link. Every AI claim traces through a finding
to a citation to a timestamp in the round viewer. It's what makes the product
verifiable rather than plausible.

### `reports`
`id, match_id FK, subject_type, subject_steam_id (nullable for team reports),
report_type (match_postmortem|player_personal|round_narrative|progress),
status (pending|generating|complete|failed), model, prompt_version,
generated_at, input_tokens, output_tokens, cached_tokens, cost_usd,
latency_ms, feedback_score`
**Indexes:** `(match_id, subject_steam_id, report_type)` unique;
`(prompt_version, feedback_score)` for quality analysis.
**Why cost lives on the report:** unit economics must be queryable. "What did
the median report cost last week?" should be one SQL query, not a spreadsheet.

### `report_sections`
`id, report_id FK, section_key, order_index, heading, body_markdown,
finding_ids uuid[], feedback (up|down|null), feedback_at`
**Why sectioned rather than one blob:** per-section thumbs up/down is the
highest-signal quality data you can collect, and it's impossible if the report
is a single field. It also lets the UI stream and expand sections
independently.

### `llm_generations`
Append-only audit of every model call: `id, report_id/conversation_id,
model, prompt_version, system_hash, input_tokens, output_tokens,
cache_read_tokens, cache_write_tokens, cost_usd, latency_ms, stop_reason,
error, created_at`
**Why:** cost attribution, latency debugging, and the ability to answer "did
quality drop because we changed the prompt or because we changed the model?"

---

## Group G — Chat

### `conversations`
`id, user_id FK, match_id (nullable FK — chat can be global or match-scoped),
title, created_at, last_message_at, message_count, total_cost_usd`
**Indexes:** `(user_id, last_message_at desc)`.

### `messages`
`id, conversation_id FK, role (user|assistant|tool), content,
tool_calls jsonb, tool_call_id, token_count, created_at, order_index`
**Indexes:** `(conversation_id, order_index)`.

### `tool_calls`
`id, message_id FK, tool_name, arguments jsonb, result jsonb,
duration_ms, error`
**Why logged separately:** when the model answers wrongly, the question is
almost always "what did the tool return?" Without this table that's
unanswerable.

### `embeddings`
`id, subject_type (round_summary|finding|report_section), subject_id,
user_id, match_id, content_text, embedding vector(1024), model, created_at`
**Indexes:** HNSW on `embedding` (`vector_cosine_ops`); btree on `(user_id,
subject_type)` — **the user filter must be in the query, not just the app
layer**, since an unfiltered vector search across all users is a data leak.
**Why narrow scope:** vector search only serves fuzzy recall ("have I done this
before?"). Precise questions go through structured tools. Embedding everything
would be expensive and would degrade answer quality by giving the model prose
where it should get numbers.

---

## Group H — Aggregates & Progress

### `player_aggregates`
Rollup by `(steam_id_64, map_name, side, mode, window_start, window_end)` with
matches counted and the same ~60 metrics averaged. Refreshed nightly and on
new-match ingest.
**Why:** the profile page must load in under 300 ms. Aggregating 200 matches ×
30 rounds live is not that.

### `mistake_streaks`
`id, steam_id_64, rule_id, first_seen_at, last_seen_at, occurrence_count,
matches_seen, matches_absent_streak, status (active|improving|resolved)`
**Why:** this is the retention feature. "This is the 7th match in a row you've
done this" and "you've fixed this — 12 matches clean" are the two most
motivating sentences the product can produce, and both require tracking findings
*across* matches rather than within one.

### `progress_reports`
Periodic LLM-generated longitudinal summaries. Same cost/prompt-version columns
as `reports`.

---

## Group I — Billing, Ops, Ingest

### `plans` / `subscriptions` / `usage_records` / `quota_counters`
Standard billing shapes. `quota_counters` keyed `(user_id, period_start,
counter_key)` with an atomic increment — quota must be enforced with a DB-level
guarantee, not an application-level read-then-write race.

### `ingest_connections` / `ingest_cursors`
`user_id, provider (steam|faceit), credentials_encrypted, status,
last_polled_at, last_error` and per-connection cursor state (the last
share code / last match id seen).
**Why cursors are separate:** polling state changes on every poll; credentials
change almost never. Splitting them keeps the hot write path narrow.

### `audit_logs`
`id, user_id, actor_id, action, subject_type, subject_id, metadata jsonb,
ip, user_agent, created_at`. Append-only. Covers deletions, plan changes,
admin actions, data exports.

### `system_events`
Operational timeline: deploys, parser version rollouts, incidents. Correlating
"quality dropped on the 14th" with "parser 2.3 shipped on the 14th" needs this.

---

## Indexing philosophy

1. **Index the access path, not the column.** Every index here exists because a
   named query needs it.
2. **Composite order = equality columns first, then range/sort.** e.g.
   `(uploader_id, uploaded_at desc)` serves "my demos, newest first" as an
   index-only scan.
3. **Partial indexes for skewed predicates** — `status = 'failed'`,
   `deleted_at is null`, `user_id is not null`. Far smaller and faster than full
   indexes on columns where 99% of rows share a value.
4. **Under-index the write-heavy event tables.** `player_ticks` takes bulk COPY
   writes and sequential range reads. Every extra index is a direct tax on parse
   throughput, which is the system's primary bottleneck.
5. **Partition the two biggest tables by `HASH(match_id)`** from the first
   migration. Retrofitting partitioning onto a live 500M-row table is a
   multi-day outage-shaped project.
6. **Vector index must be paired with a user filter** in every query — HNSW plus
   a btree pre-filter, enforced by putting the query behind a single repository
   function that cannot be called without a user id.

## Relationship summary

```
users ─1:1─ steam_profiles
users ─1:N─ demos ─N:M─ users (via demo_owners)
demos ─1:1─ matches ─1:N─ rounds ─1:N─ kills/damages/grenades/bomb_events
matches ─1:N─ match_players ─N:1(optional)─ users
grenades ─1:N─ flash_events
rounds ─1:N─ player_round_stats ─rollup→ player_match_stats ─rollup→ player_aggregates
matches ─1:N─ findings ─1:N─ finding_citations → rounds/kills/grenades
findings ─N:M─ report_sections (via finding_ids[])
matches ─1:N─ reports ─1:N─ report_sections
users ─1:N─ conversations ─1:N─ messages ─1:N─ tool_calls
findings/rounds/report_sections ─1:1─ embeddings
steam_profiles ─1:N─ mistake_streaks ─N:1─ insight_rules
```

The spine: **user → demo → match → round → event → metric → finding → report.**
Every feature in this product is a traversal of that chain in one direction or
the other.
