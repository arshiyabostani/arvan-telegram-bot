#!/usr/bin/env bash
# Smoke test for install.sh: install, update, uninstall in throwaway directories.
# Needs network access to PyPI. Does not touch systemd, Docker or real system paths.
set -Eeuo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d -t arvan-installer-XXXXXX)
trap 'rm -rf "$work"' EXIT

# Pack the working tree the way GitHub does: one top-level directory.
tar -czf "$work/src.tgz" -C "$root" \
  --exclude=.git --exclude=__pycache__ --exclude='*.egg-info' --exclude=.venv \
  --exclude=.pytest_cache --exclude=.ruff_cache --exclude=.env \
  --transform 's,^\.,arvan-telegram-bot-main,' .

export ARVAN_BOT_REPO=test/arvan-telegram-bot
export ARVAN_BOT_ARCHIVE_URL="file://$work/src.tgz"
export ARVAN_BOT_INSTALL_DIR="$work/arvan-opt"
export ARVAN_BOT_CONF_DIR="$work/arvan-etc"
export TELEGRAM_BOT_TOKEN="123456789:AAFakeTokenFakeTokenFakeTokenFake1"
export ARVAN_API_KEY="11111111-2222-3333-4444-555555555555"
export ALLOWED_USER_IDS="42, 43"

fail() { echo "FAIL: $*" >&2; exit 1; }
inst() { bash "$root/install.sh" "$@"; }

echo "--- proxy validation"
# shellcheck disable=SC2016 # the $(...) is deliberately a literal string
for bad in 'socks5://h:1 --x' 'ftp://h:1' 'socks5://h:1/$(id)' 'socks5://h"1'; do
  if TELEGRAM_PROXY=$bad inst --mode manual --no-verify >/dev/null 2>&1; then fail "accepted bad proxy: $bad"; fi
done

echo "--- ref validation"
if inst --ref 'main; id' --mode manual --no-verify >/dev/null 2>&1; then fail "accepted a malicious --ref"; fi

echo "--- install"
export TELEGRAM_PROXY="socks5://user:p%40ss@127.0.0.1:1080"
inst --mode manual --no-verify --language en --allowed-domains Example.com
env_file="$ARVAN_BOT_CONF_DIR/env"
[[ $(stat -c %a "$env_file") == 600 ]] || fail "env file must be mode 600"
grep -qx 'ALLOWED_USER_IDS=42,43' "$env_file" || fail "ids not normalised"
grep -qx 'ALLOWED_DOMAINS=example.com' "$env_file" || fail "domains not normalised"
grep -qx 'BOT_LANGUAGE=en' "$env_file" || fail "language missing"
grep -qx 'TELEGRAM_PROXY=socks5://user:p%40ss@127.0.0.1:1080' "$env_file" || fail "proxy missing"
[[ -x $ARVAN_BOT_INSTALL_DIR/venv/bin/arvan-bot ]] || fail "venv missing"
"$ARVAN_BOT_INSTALL_DIR/venv/bin/arvan-bot" --version
[[ $(stat -c %a "$ARVAN_BOT_INSTALL_DIR/app/pyproject.toml") == 6?4 ]] || fail "source must be world-readable for the service user"

echo "--- update keeps config"
before=$(sha256sum "$env_file")
inst --update --mode manual
[[ $before == "$(sha256sum "$env_file")" ]] || fail "update changed the config"

echo "--- bad checksum is refused"
if ARVAN_BOT_SHA256=deadbeef inst --update --mode manual 2>/dev/null; then fail "checksum mismatch accepted"; fi

echo "--- uninstall keeps config, purge removes it"
inst --uninstall -y
[[ ! -d $ARVAN_BOT_INSTALL_DIR ]] || fail "install dir still there"
[[ -f $env_file ]] || fail "config should survive a plain uninstall"
inst --mode manual --no-verify >/dev/null 2>&1 # reuses the kept config
inst --uninstall --purge -y
[[ ! -e $ARVAN_BOT_CONF_DIR ]] || fail "purge left the config behind"

echo "installer smoke test passed"
