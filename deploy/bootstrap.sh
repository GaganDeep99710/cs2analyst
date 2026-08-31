#!/usr/bin/env bash
# One-time server prep for Ubuntu (Oracle Cloud). Idempotent + safe to re-run.
# Installs Docker, enables the firewall (SSH kept open FIRST so we never lock
# ourselves out), and prints the host architecture. Run as the 'ubuntu' user:
#   bash bootstrap.sh
set -euo pipefail

echo "== architecture =="
uname -m   # aarch64 => Oracle Ampere ARM; x86_64 => AMD/Intel

echo "== firewall (open SSH BEFORE enabling, then HTTP/HTTPS) =="
sudo apt-get update -y
sudo apt-get install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose

echo "== Docker Engine + Compose plugin =="
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo apt-get install -y docker-compose-plugin || true
sudo usermod -aG docker "$USER" || true
sudo systemctl enable --now docker

echo
echo "Docker: $(docker --version 2>/dev/null || echo 'installed, re-login for group')"
echo "Compose: $(docker compose version 2>/dev/null || echo 'n/a')"
echo
echo "NOTE: Oracle also has a cloud-level firewall (Security List / NSG)."
echo "      You must open ingress 80 and 443 there too, or the site stays"
echo "      unreachable even with ufw open."
echo "DONE. If docker needs sudo, log out and back in once (group refresh)."
