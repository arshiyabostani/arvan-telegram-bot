# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems.

Use GitHub's private reporting instead: **Security** tab, then **Report a vulnerability**.
Include what you found, how to reproduce it, and which version you tested. This is a small
project maintained in spare time, so expect a first reply within about a week.

Only the latest release gets fixes.

## What matters most here

The bot holds an ArvanCloud API key that can change DNS and purge cache. Anyone who can
drive the bot can redirect your traffic. Reports about any of these are especially welcome:

- a way for a user who is not on `ALLOWED_USER_IDS` to get a response or trigger an action
- a way to run a change in `READ_ONLY` mode, or on a domain outside `ALLOWED_DOMAINS`
- a way to replay or skip a confirmation step
- secrets (bot token, API key, proxy credentials) showing up in logs or messages
- unvalidated input reaching an API path or payload
- anything in `install.sh` that mishandles secrets or can be abused, since it runs as root

## If you leaked a secret

1. Revoke the bot token: talk to @BotFather, `/revoke`.
2. Delete the Arvan API key in the panel and create a new one.
3. Removing the secret from git history is not enough. Assume it was copied.
