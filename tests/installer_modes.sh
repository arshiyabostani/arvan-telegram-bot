#!/usr/bin/env bash
# Tests the Docker path of install.sh with a fake docker and a fake get.docker.com.
# Needs no network and no real Docker.
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d -t arvan-modes-XXXXXX)
trap 'rm -rf "$work"' EXIT
mkdir "$work/bin"

tar -czf "$work/src.tgz" -C "$root" \
  --exclude=.git --exclude=__pycache__ --exclude='*.egg-info' --exclude=.venv \
  --exclude=.pytest_cache --exclude=.ruff_cache --exclude=.env \
  --transform 's,^\.,arvan-telegram-bot-main,' .

# "get.docker.com": creates a fake docker on PATH.
cat >"$work/get-docker.sh" <<SCRIPT
#!/bin/sh
echo "get-docker ran" >> "$work/calls.log"
cat > "$work/bin/docker" <<'DOCKER'
#!/bin/sh
echo "docker \$*" >> "$work/calls.log"
case "\$*" in *"ps --status running --quiet"*) echo abc123 ;; esac
DOCKER
chmod +x "$work/bin/docker"
SCRIPT

export PATH="$work/bin:$PATH"
export ARVAN_BOT_REPO=test/arvan-telegram-bot
export ARVAN_BOT_ARCHIVE_URL="file://$work/src.tgz"
export ARVAN_BOT_DOCKER_SCRIPT_URL="file://$work/get-docker.sh"
export ARVAN_BOT_INSTALL_DIR="$work/arvan-opt"
export ARVAN_BOT_CONF_DIR="$work/arvan-etc"
export TELEGRAM_BOT_TOKEN="123456789:AAFakeTokenFakeTokenFakeTokenFake1"
export ARVAN_API_KEY="11111111-2222-3333-4444-555555555555"
export ALLOWED_USER_IDS="42"
: >"$work/calls.log"

fail() { echo "FAIL: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || { echo "skipped: needs root (docker mode refuses to run as a normal user)"; exit 0; }
if command -v docker >/dev/null 2>&1; then echo "skipped: a real docker is on PATH"; exit 0; fi

echo "--- no terminal and no -y: Docker is not installed behind your back"
if setsid bash "$root/install.sh" --mode docker --no-verify </dev/null >"$work/out.txt" 2>&1; then fail "installed Docker without consent"; fi
grep -q "run this installer with -y" "$work/out.txt" || fail "unhelpful message"
[[ ! -e $work/bin/docker ]] || fail "docker appeared"

echo "--- with -y: installs Docker, builds and starts the container"
bash "$root/install.sh" --mode docker --no-verify -y >/dev/null 2>&1
grep -q "get-docker ran" "$work/calls.log" || fail "official script was not used"
grep -q "compose -p arvan-telegram-bot -f $work/arvan-opt/app/docker-compose.yml up -d --build" "$work/calls.log" || fail "compose up missing"
[[ $(stat -c %a "$work/arvan-opt/app/.env") == 600 ]] || fail ".env must be mode 600"
[[ $(<"$work/arvan-opt/.mode") == docker ]] || fail "mode not recorded"

echo "--- update reuses the recorded mode and the saved settings"
: >"$work/calls.log"
bash "$root/install.sh" --update --no-verify >/dev/null 2>&1
grep -q "up -d --build" "$work/calls.log" || fail "update did not rebuild"
grep -q "get-docker ran" "$work/calls.log" && fail "update reinstalled Docker"

echo "--- uninstall"
bash "$root/install.sh" --uninstall --purge -y >/dev/null 2>&1
grep -q "down --rmi local" "$work/calls.log" || fail "compose down missing"
[[ ! -e $ARVAN_BOT_INSTALL_DIR && ! -e $ARVAN_BOT_CONF_DIR ]] || fail "leftovers after purge"

echo "installer docker-mode test passed"
