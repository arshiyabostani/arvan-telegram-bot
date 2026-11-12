#!/usr/bin/env bash
#
# Installer for arvan-telegram-bot.
#
#   curl -fsSL https://raw.githubusercontent.com/arshiyabostani/arvan-telegram-bot/main/install.sh | sudo bash
#
# It asks for the bot token, the Arvan API key and the admin Telegram IDs, installs the bot
# as a systemd service (or a Docker container) and starts it. Run with --help for options.
#
# Read it before you run it: it is short, and it runs as root.

set -Eeuo pipefail
umask 022

# ---------------------------------------------------------------------------- settings
REPO="${ARVAN_BOT_REPO:-arshiyabostani/arvan-telegram-bot}"
REF="${ARVAN_BOT_REF:-main}"
INSTALL_DIR="${ARVAN_BOT_INSTALL_DIR:-/opt/arvan-telegram-bot}"
CONF_DIR="${ARVAN_BOT_CONF_DIR:-/etc/arvan-telegram-bot}"
UNIT_DIR="${ARVAN_BOT_UNIT_DIR:-/etc/systemd/system}"
SERVICE="arvan-telegram-bot"
SVC_USER="arvanbot"
CONF_FILE="$CONF_DIR/env"
ARVAN_API_BASE="${ARVAN_BASE_URL:-https://napi.arvancloud.ir}"

ACTION=install
MODE=auto
VERIFY=1
ASSUME_YES=0
PURGE=0
RECONFIGURE=0
PYTHON=""
TMP=""

# Optional settings: environment variables or flags. Secrets are never taken from flags
# (arguments are visible to every user via `ps`).
BOT_LANGUAGE="${BOT_LANGUAGE:-fa}"
READ_ONLY="${READ_ONLY:-false}"
ALLOWED_DOMAINS="${ALLOWED_DOMAINS:-}"

# ------------------------------------------------------------------------------ output
if [[ -t 2 ]]; then
  C_RED=$'\033[31m' C_YEL=$'\033[33m' C_GRN=$'\033[32m' C_OFF=$'\033[0m'
else
  C_RED="" C_YEL="" C_GRN="" C_OFF=""
fi
info() { printf '%s==>%s %s\n' "$C_GRN" "$C_OFF" "$*" >&2; }
warn() { printf '%swarning:%s %s\n' "$C_YEL" "$C_OFF" "$*" >&2; }
die() {
  printf '%serror:%s %s\n' "$C_RED" "$C_OFF" "$*" >&2
  exit 1
}
have() { command -v "$1" >/dev/null 2>&1; }

cleanup() {
  if [[ -n $TMP && -d $TMP ]]; then rm -rf "$TMP"; fi
}
trap cleanup EXIT

usage() {
  cat <<EOF
Usage: install.sh [options]

Actions (default is a fresh install):
  --update             download the latest code, keep the existing configuration, restart
  --uninstall          stop and remove the bot (configuration is kept unless --purge)

Options:
  --ref REF            branch, tag or commit to install (default: main; pin a tag in production)
  --mode MODE          auto (default: ask, or pick the best), systemd, docker or manual
  --no-service         same as --mode manual: install files only, do not start anything
  --reconfigure        ask for the settings again even if a configuration exists
  --purge              with --uninstall: also delete the configuration and the service user
  --language fa|en     interface language (default fa)
  --read-only          disable every change (DNS edits, cloud toggle, cache purge)
  --allowed-domains L  comma-separated zones the bot may manage (default: all)
  --no-verify          do not test the token and API key against the live APIs
  -y, --yes            answer yes to every question, including installing Docker or python3-venv if needed
  -h, --help           show this help

Environment (skips the matching prompt, handy for automation):
  TELEGRAM_BOT_TOKEN  ARVAN_API_KEY  ALLOWED_USER_IDS  TELEGRAM_PROXY
  ARVAN_BOT_SHA256    expected SHA-256 of the downloaded archive; the install aborts on mismatch

Paths: $INSTALL_DIR (code), $CONF_FILE (settings, root only).
EOF
}

# ------------------------------------------------------------------------ input helpers
has_tty() { { : </dev/tty; } 2>/dev/null; }

trim() {
  local s=$1
  s=${s#"${s%%[![:space:]]*}"}
  s=${s%"${s##*[![:space:]]}"}
  printf '%s' "$s"
}

# ask VAR "prompt" [secret]  -- reads from the terminal even when the script itself is piped in
ask() {
  local __var=$1 prompt=$2 secret=${3:-0} reply=""
  has_tty || die "$__var is needed: set it as an environment variable, or run the installer in a terminal."
  printf '%s' "$prompt" >/dev/tty
  if [[ $secret == 1 ]]; then
    IFS= read -rs reply </dev/tty || die "input closed"
    printf '\n' >/dev/tty
  else
    IFS= read -r reply </dev/tty || die "input closed"
  fi
  printf -v "$__var" '%s' "$(trim "$reply")"
}

confirm() { # confirm "question" Y|N
  local question=$1 default=${2:-Y} reply="" hint="y/N"
  if ((ASSUME_YES)); then return 0; fi
  if ! has_tty; then [[ $default == Y ]]; return; fi
  if [[ $default == Y ]]; then hint="Y/n"; fi
  printf '%s [%s] ' "$question" "$hint" >/dev/tty
  IFS= read -r reply </dev/tty || reply=""
  reply=${reply,,}
  if [[ -z $reply ]]; then reply=${default,,}; fi
  [[ $reply == y || $reply == yes ]]
}

mask() { # 123456789:AAAA...wxyz -> 123456789:***wxyz
  local s=$1
  if [[ $s == *:* ]]; then printf '%s:***%s' "${s%%:*}" "${s: -4}"; else printf '***%s' "${s: -4}"; fi
}

# ------------------------------------------------------------------------- live checks
# Each check returns 0 (accepted), 1 (definitely rejected) or 2 (could not tell, e.g. no route).
# The secret is passed to curl on stdin as a config file so it never appears in `ps`.
http_status() {
  local code
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 --config - 2>/dev/null || true)
  printf '%s' "${code:-000}"
}

verify_telegram() {
  have curl || return 2
  local extra="" code
  if [[ -n ${TELEGRAM_PROXY:-} ]]; then extra="proxy = \"$TELEGRAM_PROXY\""; fi
  code=$(printf 'url = "https://api.telegram.org/bot%s/getMe"\n%s\n' "$TELEGRAM_BOT_TOKEN" "$extra" | http_status)
  case $code in
    200) return 0 ;;
    401 | 404) return 1 ;;
    *) return 2 ;;
  esac
}

verify_arvan() {
  have curl || return 2
  local code
  code=$(printf 'url = "%s/cdn/4.0/domains?per_page=1"\nheader = "Authorization: Apikey %s"\nheader = "Accept: application/json"\n' \
    "$ARVAN_API_BASE" "$ARVAN_API_KEY" | http_status)
  case $code in
    200) return 0 ;;
    401 | 403) return 1 ;;
    *) return 2 ;;
  esac
}

# --------------------------------------------------------------------- collect settings
get_proxy() {
  if [[ -z ${TELEGRAM_PROXY+x} ]]; then
    if has_tty; then
      ask TELEGRAM_PROXY "Proxy for Telegram, if this server cannot reach it directly (e.g. socks5://127.0.0.1:1080, Enter to skip): "
    else
      TELEGRAM_PROXY=""
    fi
  fi
  TELEGRAM_PROXY=$(trim "$TELEGRAM_PROXY")
  # POSIX bracket expression: "]" first, "-" last. No quotes, spaces, "$" or backslashes.
  local proxy_re='^(http|https|socks5|socks5h)://[]A-Za-z0-9._~:/@%+[-]+$'
  if [[ -n $TELEGRAM_PROXY && ! $TELEGRAM_PROXY =~ $proxy_re ]]; then
    die "TELEGRAM_PROXY must look like socks5://host:port (percent-encode special characters in the password)."
  fi
}

get_token() {
  local attempt=0 rc
  while :; do
    if [[ -z ${TELEGRAM_BOT_TOKEN:-} ]]; then
      ask TELEGRAM_BOT_TOKEN "Telegram bot token from @BotFather (input hidden): " 1
    fi
    if [[ ! $TELEGRAM_BOT_TOKEN =~ ^[0-9]{5,}:[A-Za-z0-9_-]{30,}$ ]]; then
      warn "That does not look like a bot token (expected 123456789:AA...)."
    else
      rc=0
      if ((VERIFY)); then verify_telegram || rc=$?; fi
      case $rc in
        0) return 0 ;;
        2)
          warn "Could not check the token against Telegram (no connection?). Continuing."
          return 0
          ;;
        *) warn "Telegram rejected this token." ;;
      esac
    fi
    TELEGRAM_BOT_TOKEN=""
    attempt=$((attempt + 1))
    ((attempt < 3)) || die "too many invalid attempts"
  done
}

get_api_key() {
  local attempt=0 rc
  while :; do
    if [[ -z ${ARVAN_API_KEY:-} ]]; then
      ask ARVAN_API_KEY "ArvanCloud API key (input hidden): " 1
    fi
    ARVAN_API_KEY=$(trim "$ARVAN_API_KEY")
    ARVAN_API_KEY=$(printf '%s' "$ARVAN_API_KEY" | sed -E 's/^[Aa][Pp][Ii][Kk][Ee][Yy][[:space:]]+//')
    if [[ ! $ARVAN_API_KEY =~ ^[A-Za-z0-9._~+/=-]{16,200}$ ]]; then
      warn "That does not look like an Arvan API key."
    else
      rc=0
      if ((VERIFY)); then verify_arvan || rc=$?; fi
      case $rc in
        0) return 0 ;;
        2)
          warn "Could not check the API key against ArvanCloud (no connection?). Continuing."
          return 0
          ;;
        *) warn "ArvanCloud rejected this API key." ;;
      esac
    fi
    ARVAN_API_KEY=""
    attempt=$((attempt + 1))
    ((attempt < 3)) || die "too many invalid attempts"
  done
}

get_admin_ids() {
  local attempt=0 raw part ok
  local -a parts ids
  while :; do
    if [[ -z ${ALLOWED_USER_IDS:-} ]]; then
      ask ALLOWED_USER_IDS "Admin Telegram user IDs, comma separated (get yours from @userinfobot): "
    fi
    raw=${ALLOWED_USER_IDS//[,;]/ }
    read -r -a parts <<<"$raw" || true
    ids=() ok=1
    for part in "${parts[@]}"; do
      if [[ $part =~ ^[1-9][0-9]{0,15}$ ]]; then ids+=("$part"); else ok=0; fi
    done
    if ((ok && ${#ids[@]} > 0)); then
      ALLOWED_USER_IDS=$(
        IFS=,
        printf '%s' "${ids[*]}"
      )
      return 0
    fi
    warn "User IDs are plain numbers, for example 123456789 or 111,222."
    ALLOWED_USER_IDS=""
    attempt=$((attempt + 1))
    ((attempt < 3)) || die "too many invalid attempts"
  done
}

validate_options() {
  [[ $BOT_LANGUAGE == fa || $BOT_LANGUAGE == en ]] || die "--language must be fa or en"
  [[ $READ_ONLY == true || $READ_ONLY == false ]] || die "READ_ONLY must be true or false"
  ALLOWED_DOMAINS=$(trim "${ALLOWED_DOMAINS,,}")
  if [[ -n $ALLOWED_DOMAINS && ! $ALLOWED_DOMAINS =~ ^[a-z0-9.-]+(,[a-z0-9.-]+)*$ ]]; then
    die "--allowed-domains must be a comma-separated list of domain names"
  fi
}

write_conf() {
  local tmp
  tmp=$(mktemp)
  {
    printf 'TELEGRAM_BOT_TOKEN=%s\n' "$TELEGRAM_BOT_TOKEN"
    printf 'ARVAN_API_KEY=%s\n' "$ARVAN_API_KEY"
    printf 'ALLOWED_USER_IDS=%s\n' "$ALLOWED_USER_IDS"
    printf 'READ_ONLY=%s\n' "$READ_ONLY"
    printf 'BOT_LANGUAGE=%s\n' "$BOT_LANGUAGE"
    if [[ -n $ALLOWED_DOMAINS ]]; then printf 'ALLOWED_DOMAINS=%s\n' "$ALLOWED_DOMAINS"; fi
    if [[ -n $TELEGRAM_PROXY ]]; then printf 'TELEGRAM_PROXY=%s\n' "$TELEGRAM_PROXY"; fi
  } >"$tmp"
  install -d -m 700 "$CONF_DIR"
  install -m 600 "$tmp" "$CONF_FILE"
  rm -f "$tmp"
}

configure() {
  if [[ -f $CONF_FILE ]] && ((!RECONFIGURE)); then
    if [[ $ACTION == update ]] || confirm "Found an existing configuration in $CONF_FILE. Keep it?" Y; then
      info "Keeping existing configuration"
      return 0
    fi
  fi
  [[ $ACTION != update ]] || die "no configuration found in $CONF_FILE; run a normal install first"
  validate_options
  echo >&2
  info "Settings (secrets are not echoed and are stored in $CONF_FILE, readable by root only)"
  get_proxy
  get_token
  get_api_key
  get_admin_ids
  printf '    bot token : %s\n    api key   : %s\n    admins    : %s\n' \
    "$(mask "$TELEGRAM_BOT_TOKEN")" "$(mask "$ARVAN_API_KEY")" "$ALLOWED_USER_IDS" >&2
  write_conf
}

# --------------------------------------------------------------------------- preflight
PY_CANDIDATES=(python3.13 python3.12 python3.11 python3)

py_ok() { # py_ok CMD [venv]: the interpreter is 3.11+ (and can create a venv when asked)
  have "$1" || return 1
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null || return 1
  [[ ${2:-} != venv ]] || "$1" -c 'import venv, ensurepip' 2>/dev/null
}

py_version() { "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "?"; }

find_python() { # sets PYTHON to an interpreter that is ready to build a virtualenv
  local c
  for c in "${PY_CANDIDATES[@]}"; do
    if py_ok "$c" venv; then
      PYTHON=$(command -v "$c")
      return 0
    fi
  done
  return 1
}

have_py311() { # some interpreter is new enough, with or without the venv module
  local c
  for c in "${PY_CANDIDATES[@]}"; do
    if py_ok "$c"; then return 0; fi
  done
  return 1
}

have_systemd() { have systemctl && [[ -d /run/systemd/system || -n ${ARVAN_BOT_FORCE_SYSTEMD:-} ]]; }
have_docker() { have docker && docker compose version >/dev/null 2>&1; }

# Software is only installed with consent: a yes at the prompt, or -y. Never silently.
confirm_install() {
  if ((ASSUME_YES)); then return 0; fi
  has_tty || return 1
  confirm "$1" Y
}

ensure_python() {
  local c pkg
  find_python && return 0
  for c in "${PY_CANDIDATES[@]}"; do
    if py_ok "$c"; then
      pkg=python3-venv
      if [[ $c != python3 ]]; then pkg="$c-venv"; fi
      if have apt-get && confirm_install "Python's venv module is missing. Install $pkg with apt?"; then
        ((EUID == 0)) || die "installing packages needs root: re-run with sudo"
        info "Installing $pkg"
        if ! { apt-get update -qq && apt-get install -y -qq "$pkg" >/dev/null; }; then
          die "apt could not install $pkg"
        fi
        find_python && return 0
      fi
      die "the Python venv module is missing (Debian/Ubuntu: apt install $pkg)"
    fi
  done
  die "Python 3.11 or newer is required (found: $(have python3 && py_version python3 || echo none)).
       Run the installer again and choose Docker, which does not need a newer Python on the host."
}

ensure_docker_daemon() {
  if docker info >/dev/null 2>&1; then return 0; fi
  if have systemctl; then systemctl enable --now docker >/dev/null 2>&1 || true; fi
  docker info >/dev/null 2>&1 || die "the Docker daemon is not running"
}

ensure_docker() {
  if have_docker; then
    ensure_docker_daemon
    return 0
  fi
  info "Docker with the compose plugin was not found"
  confirm_install "Install Docker now with Docker's official script (get.docker.com)?" ||
    die "Docker is required. Install it yourself, or run this installer with -y to let it do that."
  ((EUID == 0)) || die "installing Docker needs root: re-run with sudo"
  local url=${ARVAN_BOT_DOCKER_SCRIPT_URL:-https://get.docker.com}
  info "Downloading $url"
  fetch "$url" "$TMP/get-docker.sh" || die "could not download the Docker install script"
  info "Installing Docker (this takes a few minutes)"
  sh "$TMP/get-docker.sh" || die "the Docker install script failed"
  have_docker || die "Docker was installed but 'docker compose' is not available"
  ensure_docker_daemon
}

pick_mode() { # interactive menu; sets MODE
  local sys_note dk_note rec=2 choice sysv
  if ! have_systemd; then
    sys_note="not available here: systemd is not running"
  elif find_python; then
    sys_note="ready (Python $(py_version "$PYTHON"))"
    rec=1
  elif have_py311; then
    sys_note="needs the python3-venv package (I can install it)"
    rec=1
  else
    sysv=$(have python3 && py_version python3 || echo none)
    sys_note="not available: needs Python 3.11+ (found $sysv)"
  fi
  if have_docker; then dk_note="installed"; else dk_note="not installed (I can install it)"; fi
  {
    printf '\nHow should the bot run?\n'
    printf '  1) systemd  Python virtualenv + hardened system service. Light, no extra daemon.\n'
    printf '              %s\n' "$sys_note"
    printf '  2) Docker   isolated container, independent of the host Python.\n'
    printf '              %s. Needs access to Docker Hub to pull the Python base image.\n' "$dk_note"
    printf 'Recommended here: %s\n' "$rec"
  } >/dev/tty
  while :; do
    ask choice "Choose 1 or 2 [$rec]: "
    if [[ -z $choice ]]; then choice=$rec; fi
    case $choice in
      1 | systemd)
        if have_systemd && have_py311; then
          MODE=systemd
          return 0
        fi
        warn "systemd mode is not possible on this machine (see above). Pick 2." ;;
      2 | docker)
        MODE=docker
        return 0 ;;
      *) warn "Please type 1 or 2." ;;
    esac
  done
}

choose_mode() {
  case $MODE in auto | systemd | docker | manual) ;; *) die "unknown mode: $MODE (use auto, systemd, docker or manual)" ;; esac
  if [[ $ACTION == update && $MODE == auto && -f $INSTALL_DIR/.mode ]]; then
    MODE=$(<"$INSTALL_DIR/.mode")
  fi
  if [[ $MODE == auto ]]; then
    if has_tty && ((!ASSUME_YES)); then
      pick_mode
    elif have_systemd && have_py311; then
      MODE=systemd
    else
      MODE=docker
    fi
  fi
  if [[ $MODE != manual ]] && ((EUID != 0)); then
    die "this needs root: re-run with sudo"
  fi
  case $MODE in
    systemd)
      have_systemd || die "systemd is not running on this machine (use --mode docker)"
      ensure_python
      ;;
    manual) ensure_python ;;
    docker) ensure_docker ;;
  esac
}

# ------------------------------------------------------------------------ fetch + deploy
fetch() { # fetch URL OUTFILE
  local url=$1 out=$2 proto='=https'
  if [[ -n ${ARVAN_BOT_ARCHIVE_URL:-} ]]; then proto='=https,http,file'; fi
  if have curl; then
    curl -fsSL --proto "$proto" --proto-redir "$proto" --tlsv1.2 --retry 3 --connect-timeout 15 -o "$out" "$url"
  elif have wget; then
    wget -q -O "$out" "$url"
  else
    die "curl or wget is required"
  fi
}

fetch_source() {
  local url=${ARVAN_BOT_ARCHIVE_URL:-https://github.com/$REPO/archive/$REF.tar.gz} sum
  info "Downloading $REPO @ $REF"
  fetch "$url" "$TMP/src.tgz" || die "download failed: $url"
  sum=$(sha256sum "$TMP/src.tgz")
  sum=${sum%% *}
  printf '    sha256 %s\n' "$sum" >&2
  if [[ -n ${ARVAN_BOT_SHA256:-} && ${ARVAN_BOT_SHA256,,} != "$sum" ]]; then
    die "checksum mismatch: expected $ARVAN_BOT_SHA256"
  fi
  mkdir "$TMP/src"
  tar -xzf "$TMP/src.tgz" -C "$TMP/src" --strip-components=1 --no-same-owner ||
    die "could not unpack the archive"
  [[ -f $TMP/src/pyproject.toml && -d $TMP/src/src/arvan_bot ]] ||
    die "the archive does not look like arvan-telegram-bot"
}

deploy_source() {
  install -d -m 755 "$INSTALL_DIR"
  rm -rf "$INSTALL_DIR/app.new" "$INSTALL_DIR/app.old"
  cp -R "$TMP/src" "$INSTALL_DIR/app.new"
  chmod -R u+rwX,go+rX,go-w "$INSTALL_DIR/app.new"
  if [[ -d $INSTALL_DIR/app ]]; then mv "$INSTALL_DIR/app" "$INSTALL_DIR/app.old"; fi
  mv "$INSTALL_DIR/app.new" "$INSTALL_DIR/app"
  rm -rf "$INSTALL_DIR/app.old"
  printf '%s\n' "$MODE" >"$INSTALL_DIR/.mode"
}

build_venv() {
  info "Installing the bot and its dependencies (this can take a minute)"
  local venv=$INSTALL_DIR/venv
  if [[ ! -x $venv/bin/python ]]; then
    "$PYTHON" -m venv "$venv" || die "could not create a virtualenv (Debian/Ubuntu: apt install python3-venv)"
  fi
  if ! {
    "$venv/bin/pip" install --disable-pip-version-check --no-cache-dir --upgrade "$INSTALL_DIR/app" &&
      "$venv/bin/pip" install --disable-pip-version-check --no-cache-dir --force-reinstall --no-deps "$INSTALL_DIR/app"
  } >"$TMP/pip.log" 2>&1; then
    tail -n 25 "$TMP/pip.log" >&2
    die "pip install failed (see the output above)"
  fi
}

check_config() {
  local out
  local -a kv
  mapfile -t kv <"$CONF_FILE"
  if ! out=$(env -i PATH=/usr/local/bin:/usr/bin:/bin "${kv[@]}" "$INSTALL_DIR/venv/bin/arvan-bot" --check-config 2>&1); then
    printf '%s\n' "$out" >&2
    die "the bot rejected the configuration (re-run with --reconfigure)"
  fi
}

# ------------------------------------------------------------------------------ modes
install_systemd() {
  if ! id -u "$SVC_USER" >/dev/null 2>&1; then
    info "Creating system user $SVC_USER"
    useradd --system --user-group --no-create-home --home-dir /nonexistent \
      --shell "$(command -v nologin || echo /usr/sbin/nologin)" "$SVC_USER"
  fi
  deploy_source
  build_venv
  check_config
  info "Writing $UNIT_DIR/$SERVICE.service"
  cat >"$UNIT_DIR/$SERVICE.service" <<EOF
[Unit]
Description=Telegram bot for ArvanCloud CDN
Documentation=https://github.com/$REPO
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SVC_USER
EnvironmentFile=$CONF_FILE
Environment=PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ExecStart=$INSTALL_DIR/venv/bin/arvan-bot
WorkingDirectory=$INSTALL_DIR
Restart=on-failure
RestartSec=5

# The bot needs outbound HTTPS and nothing else.
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictNamespaces=yes
RestrictSUIDSGID=yes
LockPersonality=yes
CapabilityBoundingSet=
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
  chmod 644 "$UNIT_DIR/$SERVICE.service"
  systemctl daemon-reload
  systemctl enable "$SERVICE" >/dev/null 2>&1
  systemctl restart "$SERVICE"
  sleep 4
  if ! systemctl is-active --quiet "$SERVICE"; then
    journalctl -u "$SERVICE" -n 25 --no-pager >&2 || true
    die "the service did not stay up. If Telegram is blocked here, re-run with --reconfigure and set a proxy."
  fi
}

install_docker() {
  deploy_source
  install -m 600 "$CONF_FILE" "$INSTALL_DIR/app/.env"
  info "Building and starting the container"
  docker compose -p "$SERVICE" -f "$INSTALL_DIR/app/docker-compose.yml" up -d --build
  sleep 4
  if [[ -z $(docker compose -p "$SERVICE" -f "$INSTALL_DIR/app/docker-compose.yml" ps --status running --quiet) ]]; then
    docker compose -p "$SERVICE" -f "$INSTALL_DIR/app/docker-compose.yml" logs --tail 25 >&2 || true
    die "the container did not stay up. If Telegram is blocked here, re-run with --reconfigure and set a proxy."
  fi
}

install_manual() {
  deploy_source
  build_venv
  check_config
}

# --------------------------------------------------------------------------- uninstall
safe_rm_dir() {
  [[ -n $1 && $1 != / && $1 == *arvan* ]] || die "refusing to delete '$1'"
  rm -rf "$1"
}

do_uninstall() {
  local mode=manual
  if [[ -f $INSTALL_DIR/.mode ]]; then mode=$(<"$INSTALL_DIR/.mode"); fi
  if [[ ! -d $INSTALL_DIR && ! -f $UNIT_DIR/$SERVICE.service ]]; then
    info "Nothing to uninstall"
    return 0
  fi
  confirm "Remove the bot from $INSTALL_DIR?" N || die "aborted (use -y to skip this question)"
  if [[ $mode != manual ]] && ((EUID != 0)); then die "this needs root: re-run with sudo"; fi
  case $mode in
    systemd)
      systemctl disable --now "$SERVICE" >/dev/null 2>&1 || true
      rm -f "$UNIT_DIR/$SERVICE.service"
      systemctl daemon-reload || true
      ;;
    docker)
      docker compose -p "$SERVICE" -f "$INSTALL_DIR/app/docker-compose.yml" down --rmi local >/dev/null 2>&1 || true
      ;;
  esac
  safe_rm_dir "$INSTALL_DIR"
  if ((PURGE)); then
    safe_rm_dir "$CONF_DIR"
    if id -u "$SVC_USER" >/dev/null 2>&1; then
      userdel "$SVC_USER" 2>/dev/null || true
      info "Removed the bot, its configuration and the $SVC_USER user"
    else
      info "Removed the bot and its configuration"
    fi
  else
    info "Removed the bot. Settings are kept in $CONF_FILE (use --purge to delete them)"
  fi
}

# ----------------------------------------------------------------------------- summary
summary() {
  local self="curl -fsSL https://raw.githubusercontent.com/$REPO/$REF/install.sh | sudo bash -s --"
  echo >&2
  info "Done. Open your bot in Telegram and send /start."
  case $MODE in
    systemd)
      printf '    logs      journalctl -u %s -f\n    status    systemctl status %s\n    restart   systemctl restart %s\n' "$SERVICE" "$SERVICE" "$SERVICE" >&2
      ;;
    docker)
      printf '    logs      docker compose -p %s -f %s/app/docker-compose.yml logs -f\n' "$SERVICE" "$INSTALL_DIR" >&2
      ;;
    manual)
      printf '    run       (set -a; . %s; set +a; exec %s/venv/bin/arvan-bot)\n' "$CONF_FILE" "$INSTALL_DIR" >&2
      ;;
  esac
  printf '    update    %s --update --ref %s\n    uninstall %s --uninstall\n    settings  %s (then re-run with --reconfigure or restart the service)\n' \
    "$self" "$REF" "$self" "$CONF_FILE" >&2
}

# ------------------------------------------------------------------------------- main
parse_args() {
  while (($#)); do
    case $1 in
      --update) ACTION=update ;;
      --uninstall) ACTION=uninstall ;;
      --purge) PURGE=1 ;;
      --reconfigure) RECONFIGURE=1 ;;
      --no-service) MODE=manual ;;
      --no-verify) VERIFY=0 ;;
      --read-only) READ_ONLY=true ;;
      -y | --yes) ASSUME_YES=1 ;;
      -h | --help)
        usage
        exit 0
        ;;
      --mode | --ref | --language | --allowed-domains)
        (($# >= 2)) || die "$1 needs a value"
        case $1 in
          --mode) MODE=$2 ;;
          --ref) REF=$2 ;;
          --language) BOT_LANGUAGE=$2 ;;
          --allowed-domains) ALLOWED_DOMAINS=$2 ;;
        esac
        shift
        ;;
      *) die "unknown option: $1 (try --help)" ;;
    esac
    shift
  done
}

main() {
  parse_args "$@"
  [[ $REPO != *arshiyabostani* ]] || die "edit REPO at the top of install.sh (or set ARVAN_BOT_REPO=owner/name) first"
  [[ $REF =~ ^[A-Za-z0-9._/-]+$ ]] || die "--ref may only contain letters, digits and . _ / -"
  [[ $(uname -s) == Linux ]] || die "Linux only"
  TMP=$(mktemp -d)

  if [[ $ACTION == uninstall ]]; then
    do_uninstall
    return 0
  fi

  info "arvan-telegram-bot installer ($REPO @ $REF)"
  choose_mode
  info "Mode: $MODE"
  configure
  fetch_source
  case $MODE in
    systemd) install_systemd ;;
    docker) install_docker ;;
    manual) install_manual ;;
  esac
  summary
}

main "$@"
