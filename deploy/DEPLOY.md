# Production deploy — Oracle VPS + custom domain

Self-hosted stack: the FastAPI app in Docker behind **Caddy** (automatic HTTPS).
Secrets stay in a `root:600` env file on the server — never in the image, never
in git. This is the runbook Claude follows once it has SSH access.

## 0. Inputs needed
- SSH private key for `ubuntu@150.136.144.202` (used locally; never pasted).
- The domain (bought at Spaceship), e.g. `demodojo.gg`.
- The three API keys (Anthropic, Gemini, FACEIT).

## 1. Server prep (once)
```bash
scp -i <key> deploy/bootstrap.sh ubuntu@150.136.144.202:~
ssh -i <key> ubuntu@150.136.144.202 'bash bootstrap.sh'
```
Note the printed architecture (`aarch64` = ARM Ampere; `x86_64` = AMD).

## 2. Ship the code
From the repo root, sync everything except junk to the server:
```bash
rsync -az --delete \
  --exclude '.git' --exclude '**/.venv' --exclude 'data' \
  --exclude 'uploads' --exclude 'demos' --exclude 'tools' \
  -e "ssh -i <key>" ./ ubuntu@150.136.144.202:~/app/
```
(If `rsync` isn't available locally, `tar czf - ... | ssh ... tar xzf -` works too.)

## 3. Configure secrets on the server
```bash
cd ~/app/deploy
cp secrets.env.example secrets.env && chmod 600 secrets.env   # fill real keys
cp .env.example .env                                           # set DOMAIN + email
```

## 4. Open Oracle's cloud firewall (web console — cannot be done over SSH)
VCN → Security List (or the instance's NSG) → **Add Ingress Rules**:
- Source `0.0.0.0/0`, TCP, dest port **80**
- Source `0.0.0.0/0`, TCP, dest port **443**

## 5. DNS (Spaceship)
Point the domain at the server, then Caddy will auto-issue the cert:
- `A` record: host `@`  → `150.136.144.202`
- `A` record: host `www` → `150.136.144.202`

## 6. Launch
```bash
cd ~/app/deploy
docker compose up -d --build
docker compose logs -f caddy   # watch the cert get issued
```
Visit `https://<domain>` — done.

## Updating later
```bash
# re-sync code (step 2), then:
cd ~/app/deploy && docker compose up -d --build
```

## Persistence
Accounts, reports, and the session secret live in the `appdata` Docker volume
(`/app/data` in the container). Certs live in `caddy_data`. Neither is touched
by `docker compose up --build`, so data survives redeploys.
