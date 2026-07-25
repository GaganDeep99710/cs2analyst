# Deploying AI CS2 Analyst (a permanent public URL)

**Not Vercel.** This app parses 200–400 MB demos (60–90 s, needs ~2 GB RAM,
holds jobs + a SQLite DB). Vercel's serverless model can't do any of that. Use
a container host. The repo already contains a working `Dockerfile`.

Recommended: **Railway** (closest to the "just push it" experience). Fly.io and
Render work too. All need your own account. One honest cost note: the RAM this
needs is past every free tier — budget ~**$5–10/mo** for a small instance.

---

## Option A — Railway (recommended)

1. Put this repo on GitHub (see "Push to GitHub" below).
2. Go to https://railway.app → **New Project → Deploy from GitHub repo** →
   pick this repo. Railway auto-detects the `Dockerfile` and builds it.
3. **Variables** tab → add:
   - `GEMINI_API_KEY` = your Google AI Studio key (the one in
     `services/parser/.env` locally). Never commit the `.env`.
4. **Settings → Resources** → raise memory to **2 GB** (parsing a big demo OOMs
   at 512 MB).
5. **Settings → Networking → Generate Domain** → that's your permanent URL.
6. (Optional, keeps report history across redeploys) **Add a Volume** mounted
   at `/app/data` — that's where the SQLite DB lives. Without it, accounts/
   reports reset on each redeploy.

## Option B — Fly.io

```bash
# one-time: install flyctl, then
fly auth login
fly launch --no-deploy          # detects the Dockerfile; pick a name/region
fly secrets set GEMINI_API_KEY=your_key_here
fly scale memory 2048           # 2 GB
fly volumes create data --size 1        # persistent DB
# add to fly.toml:  [mounts]\n  source="data"\n  destination="/app/data"
fly deploy
```

## Option C — Render

New **Web Service** → **Docker** runtime → point at the repo → add the
`GEMINI_API_KEY` env var → pick an instance with ≥2 GB RAM.

---

## Push to GitHub (first time)

```bash
cd D:/cs2-analyst
git init
git add .
git commit -m "AI CS2 Analyst web app"
# create an empty repo on github.com, then:
git remote add origin https://github.com/<you>/cs2-analyst.git
git push -u origin main
```

The `.dockerignore` and `.gitignore` already exclude the venv, uploads, demos,
the extraction tooling, and the `.env` secret — only the app + `callouts.json`
ship.

---

## What ships vs what doesn't
- **Ships:** the FastAPI app, the pipeline, and `callouts/callouts.json`
  (already extracted — no CS2 install needed on the server).
- **Does NOT ship / not needed at runtime:** the `.venv`, the VRF CLI in
  `tools/`, raw `demos/`, the nav/extract intermediates, and your `.env`.

## After it's live
Same product as local: users sign up, upload a demo (`.dem`/`.zst`/`.gz`/
`.bz2`), get their round-by-round death review, saved to their profile — but
now on a URL that never sleeps and doesn't depend on your PC.
