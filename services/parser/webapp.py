"""
webapp.py — AI CS2 Analyst web app (accounts + saved reports).

Sign up (with your in-game name), log in, upload a demo, and your round-by-round
death review is saved to your profile forever. Compressed FACEIT demos
(.zst/.gz/.bz2) are auto-extracted. Reuses the whole validated pipeline.

Run:
    ./.venv/Scripts/python.exe -m uvicorn webapp:app --port 8000
"""

import html as _html
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

import context_pack
import core
import coach
import report_html
import skills as skillmod
import store

store.init()
app = FastAPI(title="AI CS2 Analyst")
app.add_middleware(SessionMiddleware, secret_key=store.session_secret(),
                   max_age=60 * 60 * 24 * 30)

JOBS: dict[str, dict] = {}
POOL = ThreadPoolExecutor(max_workers=1)
UPLOAD = Path(__file__).parents[2] / "uploads"
UPLOAD.mkdir(exist_ok=True)


def esc(s) -> str:
    return _html.escape(str(s if s is not None else ""))


def user(request: Request) -> dict | None:
    uid = request.session.get("uid")
    return store.user_by_id(uid) if uid else None


STYLE = """
:root{--bg:#0b0e13;--surface:#141821;--surface2:#1b212c;--line:#2a3340;
--ink:#e6ebf2;--muted:#8a97a8;--faint:#5b6675;--ct:#5aa9f0;--t:#e0a53d;
--good:#3fb950;--crit:#e5484d;
--mono:ui-monospace,"Cascadia Code","SF Mono",Menlo,Consolas,monospace;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);margin:0;
min-height:100vh;line-height:1.55;
background-image:linear-gradient(var(--line) 1px,transparent 1px),
linear-gradient(90deg,var(--line) 1px,transparent 1px);
background-size:44px 44px;background-position:center}
a{color:var(--ct);text-decoration:none}
.nav{display:flex;align-items:center;gap:14px;max-width:960px;margin:0 auto;
padding:18px 18px 0}
.brand{font-family:var(--mono);font-size:13px;letter-spacing:.22em;
text-transform:uppercase;color:var(--ct);font-weight:700}
.nav .sp{flex:1}
.nav .who{font-family:var(--mono);font-size:12px;color:var(--muted)}
.wrap{max-width:960px;margin:0 auto;padding:clamp(22px,5vw,46px) 18px}
.narrow{max-width:520px}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.28em;
text-transform:uppercase;color:var(--ct);margin:0 0 12px}
h1{font-size:clamp(26px,5vw,40px);font-weight:760;letter-spacing:-.02em;
line-height:1.1;margin:0 0 12px;text-wrap:balance}
h1 .hl{color:var(--ct)}
.lede{font-size:16px;color:#cdd5e0;margin:0 0 26px;text-wrap:balance}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;
padding:22px}
label{font-family:var(--mono);font-size:11px;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted);display:block;margin:14px 0 6px}
input{width:100%;background:var(--bg);border:1px solid var(--line);
border-radius:8px;color:var(--ink);font-family:var(--sans);font-size:15px;
padding:11px 13px}
input:focus{outline:2px solid var(--ct);border-color:var(--ct)}
button,.btn{display:inline-block;background:var(--ct);color:#04101d;border:0;
border-radius:8px;font-family:var(--sans);font-weight:720;font-size:15px;
padding:12px 16px;cursor:pointer;letter-spacing:.01em;text-align:center}
button.full{width:100%;margin-top:18px}
button:hover,.btn:hover{filter:brightness(1.08)}
button:disabled{opacity:.5}
.ghost{background:var(--surface2);color:var(--ink);border:1px solid var(--line);
font-weight:600}
.small{font-family:var(--mono);font-size:12px;color:var(--faint)}
.drop{border:1.5px dashed var(--line);border-radius:10px;padding:22px 16px;
text-align:center;cursor:pointer;background:var(--surface2);transition:.15s}
.drop:hover,.drop.over{border-color:var(--ct);background:#1d2532}
.drop .big{font-weight:640;margin:0 0 4px}
.drop .sm{font-family:var(--mono);font-size:12px;color:var(--muted);margin:0}
input[type=file]{display:none}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));
gap:14px;margin-top:6px}
.rcard{background:var(--surface);border:1px solid var(--line);border-radius:11px;
padding:16px 17px;display:flex;flex-direction:column;gap:9px}
.rcard:hover{border-color:var(--ct)}
.rtop{display:flex;align-items:baseline;gap:8px}
.rmap{font-weight:700;font-size:16px;text-transform:capitalize}
.rdate{font-family:var(--mono);font-size:11px;color:var(--faint);margin-left:auto}
.rstats{font-family:var(--mono);font-size:12px;color:var(--muted);
display:flex;gap:12px;flex-wrap:wrap}
.rstats b{color:var(--ink);font-variant-numeric:tabular-nums}
.rsum{font-size:13.5px;color:#cdd5e0;
display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.rrow{display:flex;gap:8px;margin-top:2px}
.rrow a,.rrow button{font-size:12.5px;padding:7px 12px}
.del{background:transparent;color:var(--crit);border:1px solid var(--line)}
.empty{text-align:center;color:var(--muted);padding:34px 10px;
font-family:var(--mono);font-size:13px}
.progcard{margin-bottom:26px}
.proggrid{display:flex;gap:24px;flex-wrap:wrap;align-items:center}
.progradar{flex:1 1 300px;min-width:250px}
.progrows{flex:1 1 300px;min-width:250px;display:flex;flex-direction:column;gap:9px}
.progrow{display:flex;align-items:center;gap:12px;font-family:var(--mono);font-size:13px}
.pcat{width:92px;color:var(--muted)}
.pcur{width:26px;text-align:right;font-weight:700;font-variant-numeric:tabular-nums}
.pdelta{width:46px;font-size:11px}
.pdelta.up{color:var(--good)}.pdelta.down{color:var(--crit)}.pdelta.flat{color:var(--faint)}
.reslegend{display:flex;gap:18px;justify-content:center;font-family:var(--mono);
font-size:11px;color:var(--muted);margin:8px 0 0}
.reslegend span{display:flex;align-items:center;gap:6px}
.rl-you::before{content:"";width:15px;height:3px;background:var(--ct)}
.rl-goal::before{content:"";width:15px;border-top:2px dashed var(--faint)}
.steps{display:flex;flex-direction:column;gap:11px;margin:22px 0 0}
.step{display:grid;grid-template-columns:auto 1fr;gap:12px;align-items:center;
font-family:var(--mono);font-size:13px;color:var(--faint)}
.step .dot{width:9px;height:9px;border-radius:50%;background:var(--line)}
.step.on{color:var(--ink)}.step.on .dot{background:var(--ct);box-shadow:0 0 9px var(--ct)}
.step.done{color:var(--muted)}.step.done .dot{background:var(--good)}
.bar{height:4px;background:var(--line);border-radius:3px;overflow:hidden;margin:22px 0 0}
.bar>i{display:block;height:100%;background:var(--ct);width:15%;transition:width .6s}
.pick{display:flex;flex-direction:column;gap:8px;margin-top:6px}
.pick button{background:var(--surface2);color:var(--ink);border:1px solid var(--line);
text-align:left;font-family:var(--mono);font-weight:600;width:100%}
.pick button:hover{border-color:var(--ct)}
.err{color:var(--crit);font-family:var(--mono);font-size:13px}
.foot{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:26px;
text-align:center}
.tabbar{display:flex;gap:10px;font-family:var(--mono);font-size:13px;margin:0 0 20px}
"""


def shell(request: Request, body: str, nav: bool = True) -> str:
    u = user(request)
    navbar = ""
    if nav:
        right = (
            f"<span class=who>{esc(u['ign'] or u['email'])}</span>"
            "<a class=btn ghost href=/logout>Log out</a>" if u else
            "<a href=/login>Log in</a> <a class=btn href=/signup>Sign up</a>")
        navbar = (f"<div class=nav><a class=brand href=/>AI CS2 Analyst</a>"
                  f"<span class=sp></span>{right}</div>")
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>AI CS2 Analyst</title><style>{STYLE}</style></head><body>"
            f"{navbar}{body}</body></html>")


# ---------------------------------------------------------------- pipeline ---
def _run(job: dict, target: str, p=None):
    job["stage"] = "Analyzing your deaths"
    pack = context_pack.build_pack(job["path"], target, p=p)
    job["stage"] = "Writing your review"
    rep, meta = coach.generate(pack)
    html = report_html.render(pack, rep, meta)
    sb = pack["your_scoreboard"]
    store.save_report(job["id"], job["user_id"], {
        "map": pack["identity"]["map"], "player": target,
        "kd": sb["kd_ratio"], "adr": sb["adr"], "hs": sb["headshot_pct"],
        "rounds": pack["identity"]["rounds_played"], "deaths": sb["deaths"],
        "summary": rep["summary"], "skills": pack.get("skills")}, html)
    job["player"] = target
    job["status"] = "done"
    job["stage"] = "Complete"


def process(job_id: str):
    job = JOBS[job_id]
    try:
        job["status"] = "running"
        job["stage"] = "Reading the demo"
        p = core.load(job["path"])
        job["stage"] = "Verifying the scoreboard"
        players = core.scoreboard(p)["player"].tolist()
        job["players"] = players
        name = (job.get("name") or "").strip().lower()
        match = [pl for pl in players if pl.lower() == name]
        if not match:
            job["_parser"] = p
            job["status"] = "pick"
            job["stage"] = "Pick your player"
            return
        _run(job, match[0], p=p)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        job["status"] = "error"
        job["error"] = str(e)


def _guarded(job, player, p):
    try:
        _run(job, player, p=p)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        job["status"] = "error"
        job["error"] = str(e)


# --------------------------------------------------------------------- auth ---
@app.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request, err: str = ""):
    if user(request):
        return RedirectResponse("/", 303)
    e = f"<p class=err>{esc(err)}</p>" if err else ""
    return shell(request,
        "<div class='wrap narrow'><p class=eyebrow>Create account</p>"
        "<h1>Start your <span class=hl>demo log</span></h1>"
        "<div class=card><form method=post action=/signup>" + e +
        "<label>Email</label><input name=email type=email required>"
        "<label>Password</label><input name=password type=password required minlength=6>"
        "<label>Your CS2 in-game name</label>"
        "<input name=ign placeholder='the name you play under' required>"
        "<p class=small>So we auto-find you in every demo you upload.</p>"
        "<button class=full type=submit>Create account</button></form></div>"
        "<p class=foot>Already have one? <a href=/login>Log in</a></p></div>")


@app.post("/signup")
def signup(request: Request, email: str = Form(...), password: str = Form(...),
           ign: str = Form(...)):
    if not store.user_by_email(email):
        uid = store.create_user(email, password, ign)
        if uid:
            request.session["uid"] = uid
            return RedirectResponse("/", 303)
    return RedirectResponse("/signup?err=That+email+is+already+registered", 303)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, err: str = ""):
    if user(request):
        return RedirectResponse("/", 303)
    e = f"<p class=err>{esc(err)}</p>" if err else ""
    return shell(request,
        "<div class='wrap narrow'><p class=eyebrow>Welcome back</p>"
        "<h1>Log in</h1><div class=card><form method=post action=/login>" + e +
        "<label>Email</label><input name=email type=email required>"
        "<label>Password</label><input name=password type=password required>"
        "<button class=full type=submit>Log in</button></form></div>"
        "<p class=foot>New here? <a href=/signup>Create an account</a></p></div>")


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    u = store.user_by_email(email)
    if u and store.verify_pw(password, u["pw"]):
        request.session["uid"] = u["id"]
        return RedirectResponse("/", 303)
    return RedirectResponse("/login?err=Wrong+email+or+password", 303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", 303)


# ---------------------------------------------------------------- dashboard ---
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    u = user(request)
    if not u:
        return shell(request,
            "<div class=wrap><p class=eyebrow>AI CS2 Analyst</p>"
            "<h1>Stop reading stats.<br>See <span class=hl>why you died</span>, "
            "round by round.</h1>"
            "<p class=lede>Upload a CS2 demo. Get a coach's read of every death — "
            "the mistake, the map callout, and how to fix it. Saved to your "
            "profile so you can track it over time.</p>"
            "<a class=btn href=/signup>Get started — free</a> &nbsp; "
            "<a href=/login>Log in</a></div>")

    reports = store.list_reports(u["id"])
    if reports:
        cards = "".join(_report_card(r) for r in reports)
        history = f"<div class=grid>{cards}</div>"
    else:
        history = ("<div class=empty>No matches yet — upload your first demo "
                   "above to start your log.</div>")
    return shell(request,
        "<div class=wrap>"
        f"<p class=eyebrow>Welcome, {esc(u['ign'] or u['email'])}</p>"
        "<h1>Your matches</h1>"
        "<div class=card style='margin-bottom:26px'>"
        "<form id=f method=post action=/analyze enctype=multipart/form-data>"
        "<div class=drop id=drop><p class=big id=fname>Drop a demo to analyze</p>"
        "<p class=sm>.dem, .zst, .gz or .bz2 &middot; compressed is fine, we extract it</p>"
        "</div>"
        "<input type=file id=file name=file accept='.dem,.zst,.gz,.bz2' required>"
        "<button class=full id=go type=submit>Analyze new match</button>"
        "</form></div>" + _progression(reports) + history + "</div>"
        + _UPLOAD_JS)


def _report_card(r: dict) -> str:
    when = time.strftime("%b %d", time.localtime(r["created_at"]))
    mp = (r["map"] or "").replace("de_", "").replace("_", " ")
    return (
        f"<div class=rcard><div class=rtop>"
        f"<span class=rmap>{esc(mp)}</span>"
        f"<span class=rdate>{esc(when)}</span></div>"
        f"<div class=rstats><span>K/D <b>{esc(r['kd'])}</b></span>"
        f"<span>ADR <b>{esc(r['adr'])}</b></span>"
        f"<span>HS <b>{esc(r['hs'])}%</b></span>"
        f"<span><b>{esc(r['rounds'])}</b> rds</span></div>"
        f"<div class=rsum>{esc(r['summary'])}</div>"
        f"<div class=rrow><a class='btn' href=/report/{esc(r['id'])}>View review</a>"
        f"<form method=post action=/delete/{esc(r['id'])} "
        f"onsubmit=\"return confirm('Delete this report?')\">"
        f"<button class=del type=submit>Delete</button></form></div></div>")


def _spark(vals: list[int], w: int = 90, h: int = 22) -> str:
    n = len(vals)
    if n == 1:
        vals = vals * 2
        n = 2
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1

    def X(i):
        return 2 + i / (n - 1) * (w - 4)

    def Y(v):
        return 2 + (1 - (v - lo) / rng) * (h - 4)

    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'style="flex:0 0 auto"><polyline points="{pts}" fill="none" '
            f'stroke="var(--ct)" stroke-width="1.5" stroke-linejoin="round"/>'
            f'<circle cx="{X(n - 1):.1f}" cy="{Y(vals[-1]):.1f}" r="2.2" '
            f'fill="var(--ct)"/></svg>')


def _progression(reports: list[dict]) -> str:
    with_sk = [r for r in reports if r.get("skills")]
    if not with_sk:
        return ""
    latest = with_sk[0]["skills"]
    radar = (report_html.radar_svg(latest)
             if all(c in latest for c in skillmod.CATEGORIES) else "")
    rows = ""
    for cat in skillmod.CATEGORIES:
        series = [r["skills"].get(cat) for r in reversed(with_sk)
                  if r["skills"].get(cat) is not None]
        if not series:
            continue
        cur, delta = series[-1], series[-1] - series[0]
        cls, ar = (("up", "▲") if delta > 2 else
                   ("down", "▼") if delta < -2 else ("flat", "→"))
        rows += (f'<div class=progrow><span class=pcat>{esc(cat)}</span>'
                 f'{_spark(series)}<span class=pcur>{cur}</span>'
                 f'<span class="pdelta {cls}">{ar} {abs(delta)}</span></div>')
    left = f'<div class=progradar>{radar}</div>' if radar else ""
    return (
        '<div class="card progcard"><p class=h style="margin-bottom:14px">'
        f'Your progression <span class=small>· {len(with_sk)} '
        f'{"match" if len(with_sk) == 1 else "matches"}</span></p>'
        f'<div class=proggrid>{left}<div class=progrows>{rows}</div></div>'
        '<p class=reslegend><span class=rl-you>Latest</span>'
        '<span class=rl-goal>Goal</span></p></div>')


_UPLOAD_JS = """<script>
const drop=document.getElementById('drop'),file=document.getElementById('file'),
fn=document.getElementById('fname'),f=document.getElementById('f'),
go=document.getElementById('go');
if(drop){drop.onclick=()=>file.click();
file.onchange=()=>{if(file.files[0])fn.textContent=file.files[0].name};
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',ev=>{if(ev.dataTransfer.files[0]){file.files=ev.dataTransfer.files;fn.textContent=file.files[0].name}});
f.addEventListener('submit',()=>{go.disabled=true;go.textContent='Uploading…'});}
</script>"""


@app.post("/analyze")
async def analyze(request: Request, file: UploadFile, name: str = Form("")):
    u = user(request)
    if not u:
        return RedirectResponse("/login", 303)
    job_id = uuid.uuid4().hex[:12]
    dest = UPLOAD / f"{job_id}.dem"
    with open(dest, "wb") as out:
        while chunk := await file.read(1 << 20):
            out.write(chunk)
    JOBS[job_id] = {"id": job_id, "status": "queued", "stage": "Queued",
                    "name": name or u["ign"], "path": str(dest),
                    "user_id": u["id"]}
    POOL.submit(process, job_id)
    return RedirectResponse(f"/j/{job_id}", 303)


@app.post("/pick/{job_id}")
def pick(request: Request, job_id: str, player: str = Form(...)):
    u = user(request)
    job = JOBS.get(job_id)
    if not (u and job and job.get("user_id") == u["id"]):
        return RedirectResponse("/", 303)
    job["status"] = "running"
    job["stage"] = "Analyzing your deaths"
    p = job.pop("_parser", None)
    POOL.submit(lambda: _guarded(job, player, p))
    return RedirectResponse(f"/j/{job_id}", 303)


@app.get("/api/status/{job_id}")
def status(job_id: str):
    job = JOBS.get(job_id, {"status": "error"})
    return JSONResponse({"status": job["status"], "stage": job.get("stage")})


@app.get("/j/{job_id}", response_class=HTMLResponse)
def job_view(request: Request, job_id: str):
    u = user(request)
    if not u:
        return RedirectResponse("/login", 303)
    job = JOBS.get(job_id)
    if not job or job.get("user_id") != u["id"]:
        # maybe it finished and was saved — go to the report
        if store.get_report(job_id, u["id"]):
            return RedirectResponse(f"/report/{job_id}", 303)
        return shell(request, "<div class='wrap narrow'><p class=err>Job not "
                     "found.</p><p><a href=/>Back to your matches</a></p></div>")

    if job["status"] == "done":
        return RedirectResponse(f"/report/{job_id}", 303)

    if job["status"] == "pick":
        opts = "".join(
            f"<form method=post action=/pick/{job_id}>"
            f"<button name=player value=\"{esc(pl)}\">{esc(pl)}</button></form>"
            for pl in job.get("players", []))
        return shell(request, "<div class='wrap narrow'><p class=eyebrow>Almost "
                     "there</p><h1>Which one is you?</h1>"
                     f"<div class=card><div class=pick>{opts}</div></div></div>")

    if job["status"] == "error":
        return shell(request, "<div class='wrap narrow'><h1>That didn't work</h1>"
                     f"<div class=card><p class=err>{esc(job.get('error'))}</p>"
                     "<p class=small>Make sure it's a GOTV demo (not a POV "
                     "recording), 5v5.</p></div>"
                     "<p class=foot><a href=/>← Back</a></p></div>")

    steps = ["Reading the demo", "Verifying the scoreboard",
             "Analyzing your deaths", "Writing your review"]
    steps_js = "[" + ",".join(f'"{s}"' for s in steps) + "]"
    body = (
        "<div class='wrap narrow'><p class=eyebrow>AI CS2 Analyst</p>"
        "<h1>Reviewing your match…</h1>"
        "<p class=lede id=stage>Working through your demo. ~30–60 seconds.</p>"
        "<div class=card><div class=steps>" +
        "".join(f"<div class=step><span class=dot></span>{s}</div>"
                for s in steps) +
        "</div><div class=bar><i id=bar></i></div></div></div>"
        f"""<script>
const STEPS={steps_js};
async function poll(){{
  try{{
    const j=await (await fetch('/api/status/{job_id}')).json();
    if(['done','pick','error'].includes(j.status)){{location.reload();return;}}
    const i=STEPS.indexOf(j.stage);
    document.querySelectorAll('.step').forEach((el,k)=>{{
      el.classList.toggle('on',k===i);el.classList.toggle('done',k<i);}});
    const bar=document.getElementById('bar');
    if(bar)bar.style.width=(((i<0?0:i)+1)/STEPS.length*100)+'%';
    const st=document.getElementById('stage');
    if(st&&j.stage)st.textContent=j.stage+'…';
  }}catch(e){{}}
  setTimeout(poll,1400);
}}poll();
</script>""")
    return shell(request, body)


@app.get("/report/{rid}", response_class=HTMLResponse)
def report_view(request: Request, rid: str):
    u = user(request)
    if not u:
        return RedirectResponse("/login", 303)
    r = store.get_report(rid, u["id"])
    if not r:
        return shell(request, "<div class='wrap narrow'><p class=err>Report not "
                     "found.</p><p><a href=/>Back to your matches</a></p></div>")
    topbar = ("<div class=nav><a class=brand href=/>AI CS2 Analyst</a>"
              "<span class=sp></span><a class='btn ghost' href=/>← My matches</a>"
              f"<form method=post action=/delete/{esc(rid)} "
              "onsubmit=\"return confirm('Delete this report?')\">"
              "<button class=del type=submit>Delete</button></form></div>")
    return HTMLResponse(
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<style>{STYLE}</style></head><body>{topbar}{r['html']}</body></html>")


@app.post("/delete/{rid}")
def delete(request: Request, rid: str):
    u = user(request)
    if u:
        store.delete_report(rid, u["id"])
    return RedirectResponse("/", 303)
