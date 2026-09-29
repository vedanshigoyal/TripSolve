#!/usr/bin/env bash
# Ship the committed code to the EC2 server and (re)start the stack.
#
#   bash deploy/deploy.sh <elastic-ip> <path-to-key.pem>
#
# Deploys `git HEAD` (commit first!). Uses deploy/.env.prod for secrets; on first run it
# creates that file with random DB/JWT secrets and the Groq key from backend/.env.
set -euo pipefail

IP="${1:?usage: deploy.sh <elastic-ip> <key.pem>}"
KEY="${2:?usage: deploy.sh <elastic-ip> <key.pem>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/deploy/.env.prod"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "ubuntu@$IP")

if [[ ! -f "$ENV_FILE" ]]; then
  rand() { head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "$1"; }
  groq="$(grep -E '^GROQ_API_KEY=' "$ROOT/backend/.env" 2>/dev/null | cut -d= -f2- || true)"
  sed -e "s|^SITE_HOST=.*|SITE_HOST=${IP//./-}.sslip.io|" \
      -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(rand 32)|" \
      -e "s|^JWT_SECRET=.*|JWT_SECRET=$(rand 48)|" \
      -e "s|^GROQ_API_KEY=.*|GROQ_API_KEY=$groq|" \
      "$ROOT/deploy/.env.prod.example" > "$ENV_FILE"
  echo "Created $ENV_FILE (keep it private; it is git-ignored)."
fi

echo "==> Uploading $(git -C "$ROOT" rev-parse --short HEAD)"
git -C "$ROOT" archive --format=tar HEAD | "${SSH[@]}" "mkdir -p ~/tripsolve && tar -x -C ~/tripsolve"
"${SSH[@]}" "cat > ~/tripsolve/.env" < "$ENV_FILE"

echo "==> Building and starting containers (first build takes ~5-10 min)"
"${SSH[@]}" "cd ~/tripsolve && docker compose -f docker-compose.prod.yml up -d --build --remove-orphans && docker image prune -f >/dev/null"

HOST="$(grep -E '^SITE_HOST=' "$ENV_FILE" | cut -d= -f2)"
echo "==> Done: https://$HOST  (API docs: https://$HOST/api/docs)"
