#!/usr/bin/env bash
# Deploy the Copilot API and dashboard to a server you control.
#
#   deploy/deploy.sh <ssh-target> <domain> [options]
#
#   deploy/deploy.sh me@203.0.113.7 copilot.example.com
#   deploy/deploy.sh myserver copilot.example.com --migrate-data
#
# What it does, in order:
#   1. checks the server has Docker, Compose and rsync
#   2. syncs the code (never your data directory or .env files)
#   3. creates the server's .env: domain, random session secret and worker
#      token, the uid to run as. Existing values are kept.
#   4. asks you for a dashboard password if none is set (stored as a hash)
#   5. with --migrate-data, copies your local database and resumes up
#   6. builds and starts the stack, waits for HTTPS, checks the login is on
#   7. writes .worker.env here so `python -m worker` talks to the server
#
# Safe to run again: it updates the code and restarts, nothing else.
#
# Before the first run: point the domain's DNS A record at the server, and
# make sure ports 80 and 443 are open. Caddy gets the certificate by itself.
set -euo pipefail

usage() {
  sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'
  cat <<'USAGE'

Options:
  --migrate-data     copy the local database, resumes and screenshots to the
                     server (refused if the server already has a database)
  --force-migrate    as above, but move the server's database aside first
  --set-password     only set or change the dashboard password, then restart
  --password-hash-stdin
                     do not prompt: read a ready-made hash from stdin (the
                     output of `python -m copilot.auth hash`), for scripts
  --dir PATH         directory on the server (default: copilot, in your home)
  --set KEY=VALUE    put a value in the server's .env (repeatable), for
                     example --set SLACK_WEBHOOK_URL=... or --set TZ=Europe/Paris
  -h, --help

Environment:
  COPILOT_SSH_OPTS   extra ssh options, for example "-p 2222 -i ~/.ssh/key"
USAGE
}

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM="$(dirname "$HERE")"
APPS="$(dirname "$PLATFORM")"

TARGET="" DOMAIN="" REMOTE_DIR="copilot" MIGRATE=0 FORCE_MIGRATE=0 ONLY_PASSWORD=0
HASH_STDIN=0
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --migrate-data) MIGRATE=1 ;;
    --force-migrate) MIGRATE=1; FORCE_MIGRATE=1 ;;
    --set-password) ONLY_PASSWORD=1 ;;
    --password-hash-stdin) HASH_STDIN=1 ;;
    --dir) REMOTE_DIR="${2:?--dir needs a path}"; shift ;;
    --set) [[ "${2:-}" == *=* ]] || { echo "--set needs KEY=VALUE" >&2; exit 2; }
           EXTRA+=("$2"); shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) if [[ -z "$TARGET" ]]; then TARGET="$1"
       elif [[ -z "$DOMAIN" ]]; then DOMAIN="$1"
       else echo "unexpected argument: $1" >&2; exit 2; fi ;;
  esac
  shift
done
[[ -n "$TARGET" ]] || { usage >&2; exit 2; }
[[ -n "$DOMAIN" || $ONLY_PASSWORD -eq 1 ]] || { echo "missing <domain>" >&2; exit 2; }
if [[ -n "$DOMAIN" && ! "$DOMAIN" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]]; then
  echo "that does not look like a hostname: $DOMAIN" >&2; exit 2
fi

say()  { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\nerror: %s\n' "$*" >&2; exit 1; }

# A target of local:/some/dir deploys into a directory on this machine
# instead of over ssh. It exists to rehearse a deploy end to end.
LOCAL_ROOT=""
if [[ "$TARGET" == local:* ]]; then
  LOCAL_ROOT="${TARGET#local:}"
  mkdir -p "$LOCAL_ROOT"
  LOCAL_ROOT="$(cd "$LOCAL_ROOT" && pwd)"
fi
read -r -a SSH_OPTS <<< "${COPILOT_SSH_OPTS:-}"
SSH=(ssh -o ConnectTimeout=15 ${SSH_OPTS[@]+"${SSH_OPTS[@]}"})

# remote SCRIPT [ARGS...]: run a shell snippet in the deploy directory on the
# server. stdin is passed through, so secrets can be piped instead of put on
# a command line.
remote() {
  local script="$1"; shift
  if [[ -n "$LOCAL_ROOT" ]]; then
    (cd "$LOCAL_ROOT" && bash -c "$script" copilot "$@")
  else
    local quoted="" arg
    for arg in "$@"; do quoted+=" $(printf '%q' "$arg")"; done
    "${SSH[@]}" "$TARGET" "mkdir -p $(printf '%q' "$REMOTE_DIR") && cd $(printf '%q' "$REMOTE_DIR") && bash -c $(printf '%q' "$script") copilot$quoted"
  fi
}
dest() {
  if [[ -n "$LOCAL_ROOT" ]]; then printf '%s/%s' "$LOCAL_ROOT" "$1"
  else printf '%s:%s/%s' "$TARGET" "$REMOTE_DIR" "$1"; fi
}
sync() { rsync -az -e "${SSH[*]}" "$@"; }

COMPOSE="docker compose -f docker-compose.prod.yml"
PY="$PLATFORM/backend/.venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3 || true)"

# Replace or add KEY=VALUE in the server's .env. The value arrives on stdin.
SETKV='set -e; umask 077; cd platform; touch .env; IFS= read -r value
tmp="$(mktemp)"; grep -v "^$1=" .env > "$tmp" || true
printf "%s=%s\n" "$1" "$value" >> "$tmp"; cat "$tmp" > .env; rm -f "$tmp"'

set_password() {
  local hash=""
  if [[ $HASH_STDIN -eq 1 ]]; then
    IFS= read -r hash || true
    [[ "$hash" == scrypt:* ]] || die "--password-hash-stdin expects the output of: python -m copilot.auth hash"
  else
    [[ -t 0 ]] || return 1
    [[ -n "$PY" ]] || die "python3 is needed locally to hash the password"
    hash="$("$PY" "$PLATFORM/backend/copilot/auth.py" hash)" || return 1
  fi
  printf '%s\n' "$hash" | remote "$SETKV" COPILOT_PASSWORD_HASH
}

# ------------------------------------------------------------------ preflight
say "Checking $TARGET"
command -v rsync >/dev/null || die "rsync is not installed on this machine"
check="$(remote 'ok=1
command -v docker >/dev/null 2>&1 || { echo "docker is not installed"; ok=0; }
[ $ok = 1 ] && { docker compose version >/dev/null 2>&1 || { echo "the docker compose plugin is not installed"; ok=0; }; }
[ $ok = 1 ] && { docker ps >/dev/null 2>&1 || { echo "this user cannot run docker (add it to the docker group, then log in again)"; ok=0; }; }
command -v rsync >/dev/null 2>&1 || { echo "rsync is not installed"; ok=0; }
[ $ok = 1 ] && echo READY' </dev/null)" || die "could not reach $TARGET over ssh"
[[ "$check" == *READY* ]] || die "the server is not ready:
$check
Install Docker with the official script (https://get.docker.com), then run this again."
note "Docker, Compose and rsync are present"

if [[ $ONLY_PASSWORD -eq 1 ]]; then
  say "Setting the dashboard password"
  set_password || die "run this from your own terminal: it has to prompt you for the password"
  remote "cd platform && $COMPOSE up -d api >/dev/null 2>&1" </dev/null
  note "Password updated and the API restarted. Existing sessions stay valid."
  exit 0
fi

# ---------------------------------------------------------------------- sync
say "Syncing code to $(dest platform)"
remote 'mkdir -p platform/data job-ops' </dev/null
sync --delete --exclude-from="$HERE/rsync-exclude" "$PLATFORM/" "$(dest platform/)"
sync "$APPS/job-ops/fetchers.py" "$APPS/job-ops/models.py" "$APPS/job-ops/notify.py" \
     "$APPS/job-ops/sources.yaml" "$(dest job-ops/)"
note "code synced; data/ and .env files were not touched"

# ----------------------------------------------------------------------- env
say "Configuring the server's .env"
TZ_LOCAL="$(readlink /etc/localtime 2>/dev/null | sed 's#^.*/zoneinfo/##')"
state="$(remote 'set -e; umask 077; cd platform; touch .env; chmod 600 .env
have() { grep -q "^$1=." .env; }
put() { tmp="$(mktemp)"; grep -v "^$1=" .env > "$tmp" || true; printf "%s=%s\n" "$1" "$2" >> "$tmp"; cat "$tmp" > .env; rm -f "$tmp"; }
rand() { if command -v openssl >/dev/null 2>&1; then openssl rand -hex 32; else head -c 32 /dev/urandom | od -An -tx1 | tr -d " \n"; fi; }
put COPILOT_DOMAIN "$1"; put COPILOT_UID "$(id -u)"; put COPILOT_GID "$(id -g)"
have COPILOT_SESSION_SECRET || put COPILOT_SESSION_SECRET "$(rand)"
have COPILOT_WORKER_TOKEN || put COPILOT_WORKER_TOKEN "$(rand)"
have TZ || put TZ "$2"
shift 2; for kv in "$@"; do put "${kv%%=*}" "${kv#*=}"; done
have COPILOT_PASSWORD_HASH && echo password=set || echo password=missing
have ANTHROPIC_API_KEY && echo apikey=set || echo apikey=missing
have COPILOT_URL_PORT && grep "^COPILOT_URL_PORT=" .env || true' \
  "$DOMAIN" "${TZ_LOCAL:-America/Los_Angeles}" ${EXTRA[@]+"${EXTRA[@]}"} </dev/null)"
note "domain, run-as uid, session secret and worker token are in place"
URL_PORT="$(printf '%s\n' "$state" | sed -n 's/^COPILOT_URL_PORT=//p')"
URL="https://$DOMAIN$URL_PORT"

PASSWORD_SET=1
if [[ "$state" == *password=missing* || $HASH_STDIN -eq 1 ]]; then
  say "Choose the dashboard password (it is hashed here; only the hash is sent)"
  if set_password; then note "password set"; else
    PASSWORD_SET=0
    note "no terminal to prompt on, so no password was set."
    note "The dashboard stays locked until you run:  deploy/set-password.sh $TARGET"
  fi
fi

if [[ "$state" == *apikey=missing* ]]; then
  if [[ -t 0 ]] && grep -q '^ANTHROPIC_API_KEY=.' "$PLATFORM/.env" 2>/dev/null; then
    read -r -p "    Copy ANTHROPIC_API_KEY from your local .env to the server? [y/N] " yn
    if [[ "$yn" =~ ^[Yy] ]]; then
      sed -n 's/^ANTHROPIC_API_KEY=//p' "$PLATFORM/.env" | head -1 | remote "$SETKV" ANTHROPIC_API_KEY
      note "API key copied"
    fi
  else
    note "no Claude API key on the server: matches will stay unscored until you add"
    note "ANTHROPIC_API_KEY to $REMOTE_DIR/platform/.env there and run this again"
  fi
fi

# ----------------------------------------------------------------- migration
if [[ $MIGRATE -eq 1 ]]; then
  say "Migrating local data"
  [[ -f "$PLATFORM/data/copilot.db" ]] || die "no local database at $PLATFORM/data/copilot.db"
  if remote 'test -e platform/data/copilot.db' </dev/null; then
    [[ $FORCE_MIGRATE -eq 1 ]] || die "the server already has a database. Use --force-migrate to replace it (the old one is kept as a backup)."
    remote "cd platform && $COMPOSE stop api >/dev/null 2>&1 || true
            stamp=\$(date +%Y%m%d-%H%M%S); mv data/copilot.db data/copilot.db.replaced-\$stamp
            rm -f data/copilot.db-wal data/copilot.db-shm; echo \"    old database kept as data/copilot.db.replaced-\$stamp\"" </dev/null
  fi
  mkdir -p "$PLATFORM/data/.export"
  # A consistent snapshot through SQLite's backup API, safe while the local
  # app is running. Taken inside the container when there is one, so the
  # database still has a single writer process.
  SNAP='import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()'
  if (cd "$PLATFORM" && docker compose ps --status running --services 2>/dev/null | grep -qx api); then
    (cd "$PLATFORM" && docker compose exec -T api python -c "$SNAP" /data/copilot.db /data/.export/copilot.db)
  else
    "$PY" -c "$SNAP" "$PLATFORM/data/copilot.db" "$PLATFORM/data/.export/copilot.db"
  fi
  sync "$PLATFORM/data/.export/copilot.db" "$(dest platform/data/copilot.db)"
  for d in resumes screenshots; do
    [[ -d "$PLATFORM/data/$d" ]] && sync "$PLATFORM/data/$d" "$(dest platform/data/)"
  done
  rm -rf "$PLATFORM/data/.export"
  note "database, resumes and screenshots copied (the browser profile stays here)"
fi

# --------------------------------------------------------------------- start
say "Building and starting the stack on the server (the first build takes a few minutes)"
remote "cd platform && $COMPOSE up -d --build --remove-orphans 2>&1 | tail -n 12" </dev/null

say "Waiting for $URL"
CURL=(curl -sS --max-time 8)
[[ "$DOMAIN" == localhost || "$DOMAIN" == *.localhost ]] && CURL+=(-k)   # Caddy's own CA
ok=0
for _ in $(seq 1 40); do
  if "${CURL[@]}" -f -o /dev/null "$URL/api/health" 2>/dev/null; then ok=1; break; fi
  sleep 3
done
if [[ $ok -ne 1 ]]; then
  remote "cd platform && $COMPOSE ps && $COMPOSE logs --tail 15 caddy api" </dev/null || true
  die "$URL did not answer. Usual causes: the domain's DNS does not point at the server yet, or ports 80 and 443 are closed. The stack is running; fix that and Caddy will pick it up."
fi
note "HTTPS is up"

# The one check that matters: an anonymous request must be refused.
code="$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$URL/api/status" || true)"
case "$code" in
  401) note "login is enforced (anonymous request refused with 401)" ;;
  503) note "locked: no password is set yet (anonymous request refused with 503)" ;;
  *) remote "cd platform && $COMPOSE stop" </dev/null || true
     die "an anonymous request returned HTTP $code instead of being refused. The stack was stopped." ;;
esac

# -------------------------------------------------------------------- worker
say "Pointing the apply worker at the server"
ENV_OUT="$PLATFORM/.worker.env"
[[ -n "$LOCAL_ROOT" ]] && ENV_OUT="$LOCAL_ROOT/.worker.env"
token="$(remote 'sed -n "s/^COPILOT_WORKER_TOKEN=//p" platform/.env | head -1' </dev/null)"
[[ -n "$token" ]] || die "could not read the worker token from the server"
(umask 077; printf '# Written by deploy/deploy.sh. Delete this file to use a local API again.\nCOPILOT_API=%s\nCOPILOT_WORKER_TOKEN=%s\n' "$URL" "$token" > "$ENV_OUT")
unset token
note "wrote $ENV_OUT (not committed; holds the worker token)"

say "Deployed: $URL"
[[ $PASSWORD_SET -eq 1 ]] || note "Set the password first:  deploy/set-password.sh $TARGET"
note "Worker (on this machine):  cd backend && .venv/bin/python -m worker"
note "Update later:              deploy/deploy.sh $TARGET $DOMAIN"
if (cd "$PLATFORM" && docker compose ps --status running --services 2>/dev/null | grep -qx api); then
  note "Your local copy is still running and will keep fetching on its own schedule."
  note "Stop it once you are happy with the server:  docker compose down"
fi
