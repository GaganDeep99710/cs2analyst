# Phase 6 — The 30-Day MVP

## The question the MVP must answer

Not "can we build this?" — we can. The MVP exists to answer:

> **Will a player read an AI-written analysis of their own demo and agree that
> it's true and useful?**

Everything that doesn't serve that question is cut. If the answer is no, no
amount of round viewer polish, auto-ingest or billing saves the product. If the
answer is yes, all of that is worth building.

## Scope reduction that makes 30 days real

| Dimension | Full product | MVP |
|---|---|---|
| Demo source | Valve auto, FACEIT, upload | **Manual upload only** |
| Maps | All | **Mirage, Inferno, Dust2, Ancient, Nuke** (5) |
| Modes | Premier, comp, FACEIT, ESEA, scrim | **Premier / MM 5v5 MR12** |
| Analysis subject | All 10 players | **The uploading user only** |
| Report types | Post-mortem, personal, rounds, progress | **Personal + a short match verdict** |
| Round viewer | Full 2D replay | **Static round snapshot images** |
| Chat | Full tool-using agent | **Cut entirely** |
| Trends | Full profile + streaks | **Cut** |
| Billing | Stripe, plans, quotas | **Cut — hard cap of 5 demos/user, waitlist** |
| Auth | Steam + email | **Steam only** |

The cuts that hurt but are correct: **chat** (it's the differentiator, but it's
worthless if reports aren't good, and reports are what we're testing) and the
**round viewer** (a static image with dots and a caption proves the citation
concept at 5% of the cost).

## MVP feature list — the complete set

**Auth**
1. Sign in with Steam. Session. Sign out. That's it.

**Upload**
2. Single-file drag-and-drop, `.dem` and `.dem.bz2`, presigned direct-to-R2.
3. SHA-256 dedupe.
4. Hard cap: 5 demos per user.

**Processing**
5. Redis queue, one Python worker.
6. Staged progress via polling (SSE is a nice-to-have, polling is fine at MVP
   scale).
7. Clear failure states with real explanations.

**Parsing** — the irreducible core
8. Match header, players, rounds, kills, damage, grenades, bomb events.
9. Decimated ticks (needed for positional metrics and snapshots).
10. Zone/callout mapping for the 5 maps.
11. Opening duel, trade, and buy-type enrichment.

**Metrics**
12. ~25 metrics, not 60: ADR, KAST, HS%, rating, opening duel W/L by side and
    zone, trade participation, utility damage, enemies/teammates flashed,
    unused utility at death, multi-kills, clutches, deaths by zone, buy type
    outcomes, time to first contact.
13. Self-comparison only. **No cohort benchmarks** — they need a data corpus we
    won't have. This is fine; "worse than your own average" is still coaching.

**Insights**
14. ~15 rules covering the highest-value, most common mistakes: unused utility,
    opening duel leak by zone, failure to trade, repeated death location,
    teammate flashing, late utility, force-buy losses, over-peeking, clutch
    conversion, weak side asymmetry.
15. Findings with round citations.

**AI**
16. Context pack assembly.
17. One prompt producing: a match verdict (2 sentences), top 3 mistakes with
    explanations and drills, one strength.
18. Claude Sonnet 5 + Opus 4.8 for the verdict. Structured output. Streaming.
19. Citation validator.

**UI**
20. Landing page with a real public sample report.
21. Dashboard / demo list.
22. Upload page with demo-location help.
23. Processing screen with staged progress.
24. Match report page: verdict, 3 mistakes (expandable, cited), 1 strength,
    round timeline, scoreboard.
25. Round snapshot images for citations (server-rendered PNG: radar + death
    positions + caption).
26. Thumbs up/down per section — **the primary success metric**.
27. Mobile-readable report.

**Ops**
28. Sentry, structured logs, a basic admin page listing jobs and failures.
29. PostHog on the core funnel.

**That's the entire MVP. 29 items.**

## Explicitly NOT in the MVP

Chat · round replay viewer · player profiles/trends · cohort benchmarks ·
auto-ingest · billing · teams · sharing beyond a public link · email
notifications · all-player analysis · maps beyond the five · non-MR12 formats ·
Wingman · progress reports · Discord bot · mistake streaks.

Every one of these is in the roadmap. None of them answer the MVP question.

## 30-day schedule

| Days | Focus | Exit criterion |
|---|---|---|
| 1–3 | Foundation, Steam auth | Sign in with Steam, see an empty dashboard |
| 4–7 | Upload, R2, queue, job lifecycle | 250 MB demo uploads and reaches `queued` |
| 8–16 | **Parser** (the long pole) | 5 demos across 5 maps parse correctly end to end |
| 17–20 | Metrics + validation vs. a known source | Scoreboard matches CSStats within rounding |
| 21–23 | Rules engine, ~15 rules | Findings fire correctly on hand-checked demos |
| 24–27 | Context pack, prompt, generation, validator | Reports generate and cite accurately |
| 28–29 | Report UI, snapshots, feedback, landing | The full flow works for a stranger |
| 30 | Deploy, monitoring, 10 friendly testers | Real users producing real thumbs |

**Day 16 is the go/no-go.** If the parser isn't reliably producing correct data
for five demos by then, the schedule is gone and the right move is to extend
rather than compress the AI work — a fast report built on wrong data tests
nothing.

## MVP success criteria

Ship it to 20–30 real players. The product is validated if:

- **>60% of report sections get a thumbs up** (this is the real number that
  matters)
- **>40% of testers upload a second demo unprompted** — the strongest possible
  signal
- **>30% click through to a cited round** — they're checking the work, which
  means they're taking it seriously
- **Parse success rate >90%** on real-world demos
- **Cost per report under $0.30**
- Qualitatively: at least a handful of people say some version of *"that's
  actually right"* unprompted

If sections get thumbs-down at scale, the problem is almost certainly in the
rules and metrics (stage ⑦), not the prompt. Fix the analysis before touching
the prose — that diagnosis order is the most valuable thing to internalize
about running this product.

## Day 31 onward, in priority order

1. Chat (retention)
2. Auto-ingest from Steam (retention)
3. Remaining maps + all-player analysis (breadth)
4. Round replay viewer (delight + marketing)
5. Profiles and trends (monthly-payment justification)
6. Billing (only once retention is proven)
