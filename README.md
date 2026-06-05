# codaemon

The Discord bot that manages the Coding Factory school server: it provisions a
private category + channels + role per class, and onboards students (validates
their school email, sets their nickname, assigns their promotion role).

It holds **no roster** — [learnd](https://learnd) (formerly TeachPilot) is the
system of record for students/classes. codaemon only stores a small onboarding
audit log.

## Architecture

Two processes from one image (Design A):

```
  web (gunicorn / WSGI)        runbot (discord.py gateway)
  - /on-promotion-created      - /createcategory  (admin)
  - /onboard (confirm page)    - /deletecategory  (admin)
  - /healthz                   - /onboard         (students)
        \__ both call bot/discord_actions.py (Discord REST) __/
```

- The **gateway** worker handles slash commands (it makes an *outbound* WebSocket
  to Discord — Discord never needs codaemon's URL).
- The **web** process handles the learnd webhook + the onboarding page, and calls
  Discord over REST. No async needed there.

## Local development

```bash
uv sync
cp .env.example .env   # fill in the values
cd src
uv run python manage.py migrate
uv run python manage.py runserver   # web
uv run python manage.py runbot      # gateway (separate terminal)
```

Lint/format: `uv run ruff check src` / `uv run ruff format src`.

## Deployment

- Push to `main` → GitHub Actions builds & pushes `ghcr.io/coding-factory-projects/codaemon`,
  then deploys to **staging** automatically and to **production** after manual approval.
- The server only needs `docker-compose.yml` + `.env` (both pushed by CI); it pulls the image.

### One-time server setup (by hand)
- DNS A records: `codaemon.codingfactory.tech` and `codaemon-staging.codingfactory.tech` → server IP.
- nginx vhost per host → `proxy_pass http://127.0.0.1:<GUNICORN_PORT>` (8200 prod, 8201 staging) + certbot.
- A directory per environment (e.g. `/srv/codaemon`, `/srv/codaemon-staging`).
- A **separate Discord application + test guild** for staging.

### GitHub configuration
Create two **Environments** (`staging`, `production`); add *Required reviewers* to
`production`. Per-environment **secrets**:

| Secret | Meaning |
|---|---|
| `SSH_HOST` / `SSH_USER` / `SSH_KEY` | deploy SSH target (dedicated key) |
| `DEPLOY_PATH` | e.g. `/srv/codaemon` or `/srv/codaemon-staging` |
| `DOTENV` | the full `.env` contents for that environment |

Make the GHCR package public so the server pulls without credentials.

## learnd contract

- learnd → codaemon: `POST /on-promotion-created {name, campus}` (+ `X-Shared-Secret`) → `{roleId}`
- codaemon → learnd: `PATCH /promotions/students {email, discord_id}` (+ `X-Shared-Secret`)
  → `{firstName, lastName, promotion: {discord_role_id}}`

The shared secret is required in **both** directions from day one.
