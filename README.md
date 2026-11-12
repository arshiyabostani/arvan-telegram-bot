# arvan-telegram-bot

[![CI](https://github.com/arshiyabostani/arvan-telegram-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/arshiyabostani/arvan-telegram-bot/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)

A Telegram bot for the small, frequent jobs you do on an ArvanCloud CDN account: check a DNS
record, add or remove one, switch the cloud (proxy) toggle, purge the cache. It talks to the
CDN API v4.0 and nothing else.

Unofficial. Not affiliated with or endorsed by ArvanCloud.

## What it does

- Lists the domains on the account
- Shows DNS records (paginated) and lets you delete them
- Creates `A`, `AAAA`, `CNAME`, `ANAME`, `TXT`, `MX` and `NS` records, with a confirmation step
- Turns the cloud toggle on or off for `A`, `AAAA`, `CNAME` and `ANAME` records
- Purges the whole cache of a domain, or specific URLs
- Persian and English interface (`BOT_LANGUAGE`)

What it does not do: edit a record in place (delete and recreate instead), `SRV`, `CAA`, `TLSA`
and `PTR` records, SSL, firewall, WAF, reports. Pull requests are welcome.

## Quick install

On a Linux server, as a user with `sudo`:

```sh
curl -fsSL https://raw.githubusercontent.com/arshiyabostani/arvan-telegram-bot/v1.0.0/install.sh \
  | sudo bash -s -- --ref v1.0.0
```

It asks four things: a Telegram proxy (only if the server cannot reach Telegram directly), the
bot token, the Arvan API key and the admin Telegram user IDs. Secrets are typed hidden. Then it
installs the bot as a `systemd` service, starts it, and prints the commands for logs, update and
removal. Open the bot in Telegram and send `/start`.

Piping a script into a root shell means trusting it, so you may prefer to read it first:

```sh
curl -fsSL https://raw.githubusercontent.com/arshiyabostani/arvan-telegram-bot/v1.0.0/install.sh -o install.sh
less install.sh
sudo bash install.sh --ref v1.0.0
```

What it does, in order:

1. Asks how to run the bot (see [Docker or systemd](#docker-or-systemd)). The menu shows what
   this machine supports and recommends one. If you choose Docker and it is not installed, the
   installer offers to install it with Docker's official script (`get.docker.com`). If you
   choose systemd and only the `python3-venv` package is missing, it offers to install that with
   `apt`. Nothing is installed without a yes, or `-y`.
2. Asks for the settings and checks the token and API key against Telegram and ArvanCloud. If a
   service is unreachable it only warns, since many servers need a proxy for Telegram.
3. Downloads the release archive from GitHub, prints its SHA-256, and unpacks it.
4. Installs into `/opt/arvan-telegram-bot` and writes the settings to
   `/etc/arvan-telegram-bot/env` (mode 600, root only). Then it starts either a hardened
   `systemd` unit that runs as the unprivileged `arvanbot` user, or the Docker container.

Without a terminal (cron, CI) there are no questions: it picks systemd when it can, otherwise
Docker, and refuses to install anything unless you pass `-y`.

```sh
# update, keeping the settings
curl -fsSL https://raw.githubusercontent.com/arshiyabostani/arvan-telegram-bot/main/install.sh | sudo bash -s -- --update

# change the settings
sudo bash install.sh --reconfigure

# remove (add --purge to delete the settings and the service user too)
sudo bash install.sh --uninstall
```

Options: `--ref` (branch, tag or commit), `--mode auto|systemd|docker|manual` (skips the question), `--language fa|en`,
`--read-only`, `--allowed-domains a.com,b.ir`, `--no-verify`, `-y`. See `--help`.
For automation, `TELEGRAM_BOT_TOKEN`, `ARVAN_API_KEY`, `ALLOWED_USER_IDS` and `TELEGRAM_PROXY` can
be set in the environment to skip the prompts. There are deliberately no flags for secrets,
because command-line arguments are visible to every user on the machine.
To check a download against a known hash, set `ARVAN_BOT_SHA256`.

## Docker or systemd

Both are supported and both are hardened. Short version:

- **systemd** (Python 3.11+ and `python3-venv` on the host) is lighter. There is no extra daemon,
  logs go to `journalctl`, and the only moving parts are a virtualenv and a unit file. It is the
  default recommendation whenever the host can do it.
- **Docker** does not care about the host's Python version, so it is the answer on Ubuntu 22.04
  (Python 3.10) and similar. The cost is the Docker daemon, which runs as root, and pulling the
  Python base image from Docker Hub, which some networks block.

If the server already runs Docker for other things, use Docker. Otherwise prefer systemd.

## Manual setup

You need a bot token, an Arvan API key, and your numeric Telegram user ID.

1. **Bot token.** Message [@BotFather](https://t.me/BotFather), send `/newbot`, copy the token.
2. **API key.** Create one in the ArvanCloud panel. Give it access to the CDN service only, and
   restrict it to your server's IP if the panel offers that.
3. **Your user ID.** Message [@userinfobot](https://t.me/userinfobot). It replies with a number.

Then pick one of the two ways to run it.

### Docker

```sh
cp .env.example .env      # fill in the three values above
docker compose up -d --build
docker compose logs -f
```

### Python

Python 3.11 or newer.

```sh
python -m venv .venv && . .venv/bin/activate
pip install .
cp .env.example .env      # fill it in
arvan-bot --check-config  # validates the settings and exits
arvan-bot
```

If Telegram is blocked where the bot runs, set `TELEGRAM_PROXY` (for example
`socks5://127.0.0.1:1080`). The proxy is used for Telegram only, not for the Arvan API.

## Configuration

Everything comes from environment variables. A `.env` file in the working directory is read
if it exists. Any secret can instead be given as `NAME_FILE=/path/to/file`.

| Variable             | Required | Default                      | Meaning                                                              |
|----------------------|----------|------------------------------|----------------------------------------------------------------------|
| `TELEGRAM_BOT_TOKEN` | yes      |                              | Token from BotFather                                                 |
| `ARVAN_API_KEY`      | yes      |                              | Arvan API key (a leading `Apikey ` is accepted and stripped)         |
| `ALLOWED_USER_IDS`   | yes      |                              | Comma-separated Telegram user IDs. An empty list makes the bot refuse to start |
| `ALLOWED_DOMAINS`    | no       | all domains on the account   | Comma-separated zones the bot may touch                              |
| `READ_ONLY`          | no       | `false`                      | `true` disables every change                                         |
| `BOT_LANGUAGE`       | no       | `fa`                         | `fa` or `en`                                                         |
| `LOG_LEVEL`          | no       | `INFO`                       | `DEBUG`, `INFO`, `WARNING`, `ERROR`                                  |
| `TELEGRAM_PROXY`     | no       |                              | `http`, `https`, `socks5` or `socks5h` URL                           |
| `ARVAN_BASE_URL`     | no       | `https://napi.arvancloud.ir` | Must be `https`                                                      |

Bad configuration is reported all at once and the process exits with status 2.

## Using it

Send `/start`, pick a domain, and use the buttons. When the bot needs text (a record name, a
list of URLs) it asks for it, and `/cancel` or the Cancel button drops whatever is in progress.

Deleting a record and purging the whole cache both ask for confirmation. That confirmation is
kept on the server for 60 seconds. An old "Yes, delete" button left in the chat does nothing.

Purging by URL takes absolute URLs, one per line, up to 30. Every URL has to belong to the
selected domain or one of its subdomains.

## Security

The bot holds a key that can change DNS and clear cache for every domain on the account.
Whoever controls the bot can send your traffic somewhere else, so the defaults are strict.

What the code does:

- **Allowlist.** Only the user IDs in `ALLOWED_USER_IDS` are served. Everyone else is ignored
  without a reply, so the bot does not confirm that it exists.
- **Private chats only.** Added to a group, it stays silent.
- **Rate limit.** 20 actions per 10 seconds per user.
- **Policy in one place.** `READ_ONLY` and `ALLOWED_DOMAINS` are enforced inside the API client,
  below the Telegram handlers, so a handler bug cannot skip them.
- **Input validation.** Domains, record IDs, record names, values and URLs are checked before use,
  and every path segment is percent-encoded. Callback data must match strict patterns.
- **Confirmations are state, not buttons.** Destructive actions run only if the server still has
  a matching, unexpired confirmation for that user.
- **No secret leakage.** Secrets are never logged. The HTTP libraries are silenced below
  WARNING and every log line, tracebacks included, is scrubbed for the token and API key. API error
  bodies are not forwarded to the chat; only a short, sanitised summary is.
- **Retries only for reads.** A `POST` or `DELETE` that times out is not repeated.
- **Audit log.** Each change writes one line (`user=… action=… outcome=… details={…}`) to stderr.
  Details are JSON-encoded so user text cannot forge extra lines.
- **Stale updates dropped.** Messages queued while the bot was offline are discarded on start.
- **Installer.** Secrets are read with hidden input, never passed as arguments (checks against the
  live APIs hand them to `curl` on stdin), and stored in a root-only file the service user cannot
  read. The service runs unprivileged with `NoNewPrivileges`, `ProtectSystem=strict`, a private
  `/tmp`, no capabilities and no socket types beyond IP and Unix.
- **Container.** The image runs as a non-root user; the compose file adds a read-only filesystem,
  no capabilities and `no-new-privileges`.

What it cannot do for you:

- If someone takes over your Telegram account, they take over the bot. Turn on two-step
  verification in Telegram.
- Bot chats are not end-to-end encrypted. Telegram can see what is sent, including domain names
  and record values.
- There is no database. Flow state lives in memory and is lost on restart. Audit lines go to
  stderr, so ship them somewhere if you need to keep them.

Practical advice: use a dedicated API key, set `ALLOWED_DOMAINS` if the account has more zones
than the bot needs, and run with `READ_ONLY=true` when you only want to look.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## API compatibility

Request shapes follow the examples in the public ArvanCloud CDN documentation
(`docs.arvancloud.ir`). The test suite runs against a fake API, not the real service, so try the
bot on a throwaway domain before you point it at something that matters. If Arvan changes the
API, `arvan/client.py` and `arvan/records.py` are the only files that should need to change.

## Layout

```
src/arvan_bot/
  __main__.py        entry point and CLI flags
  config.py          environment parsing and validation
  logging_setup.py   log format and secret redaction
  validation.py      every check on user input
  arvan/
    client.py        HTTP client: policy, retries, error mapping
    records.py       DNS payload builders and display helpers
    errors.py
  bot/
    app.py           handler registration
    auth.py          allowlist, private-chat check, rate limit
    flow.py          short-lived state for multi-step actions
    audit.py
    messages.py      English and Persian strings
    callbacks.py     callback data and the patterns that accept it
    handlers/        domains, dns, cache, text
install.sh           one-command installer (systemd or Docker)
tests/               unit and conversation tests, plus installer_smoke.sh
```

## Development

```sh
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest
shellcheck -x install.sh tests/*.sh
bash tests/installer_smoke.sh        # install/update/uninstall into a temp dir; needs PyPI access
sudo bash tests/installer_modes.sh   # Docker path with a fake docker; no network needed
```

The handler tests drive the real routing table against an in-memory fake of the Arvan API, so
they cover whole conversations (add a record, delete with a stale confirmation, read-only mode,
an unauthorised user) rather than single functions.

## License

MIT. See [LICENSE](LICENSE).
