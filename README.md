# codaemon

The Discord bot that manages the Coding Factory school server: it provisions a
private category + channels + role per class, and onboards students (validates
their school email, sets their nickname, assigns their promotion role).

In production it holds **no roster**: learnd is the system of record, and
codaemon only stores a small onboarding audit log.

## Architecture

Two processes from one image (Design A):

```
  web (gunicorn / WSGI)        runbot (discord.py gateway)
  - /on-promotion-created      - /createcategory  (admin)
  - /onboard (confirm page)    - /deletecategory  (admin)
  - /healthz                   - /rollover        (admin)
                               - /onboard         (students)
        \__ both call bot/discord_actions.py (Discord REST) __/
```

- The **gateway** worker handles slash commands (it makes an *outbound* WebSocket
  to Discord — Discord never needs codaemon's URL).
- The **web** process handles the learnd webhook + the onboarding page, and calls
  Discord over REST. No async needed there.

## Test mode

Test mode reads a private student fixture instead of learnd and returns the
confirmation link directly in Discord instead of sending email.

### 1. Prepare Discord

1. Create a Discord application and bot, then enable **Server Members Intent**.
2. Install it on a disposable guild with `bot` and `applications.commands` scopes.
   Administrator permission is simplest for this test-only guild.

### 2. Run locally

Install dependencies and create the private fixture:

```bash
make install
cp .env.example .env
cp fixtures/students.example.json fixtures/students.json
```

Configure `.env`:

```dotenv
CODAEMON_TEST_MODE=true
LEARND_FIXTURE_PATH=fixtures/students.json
DISCORD_TOKEN=...
DISCORD_GUILD_ID=...
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_PATH=data/db.sqlite3
WEBSITE_BASE_URL=http://localhost:8000
```

Role IDs can remain empty. Start the two processes:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver       # terminal 1
.venv/bin/python manage.py runbot          # terminal 2
```

No tunnel is needed when the browser is on this computer. For another device or
tester, expose port 8000 and set the tunnel host in `WEBSITE_BASE_URL` and
`DJANGO_ALLOWED_HOSTS`.

### 3. Run a deployed instance

Create `fixtures/` beside `docker-compose.yml` and place the private
`students.json` inside it. Configure test mode plus the Discord values above,
then set:

```dotenv
DJANGO_ALLOWED_HOSTS=codaemon-test.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://codaemon-test.example.com
WEBSITE_BASE_URL=https://codaemon-test.example.com
```

Start or update the instance:

```bash
docker compose pull
docker compose up -d
```

Compose mounts the private fixture into both services; it is never included in
the image.

### 4. Test onboarding

On `runbot` startup, the bot finds or creates Admin, Base, Guest, Product Owners,
and every promotion role declared in the fixture. Existing roles are reused;
duplicate or reserved names are rejected. Restart `runbot` after adding or
renaming a promotion.

1. Assign Guest to the test member.
2. Run `/onboard ada.lovelace.test@edu.esiee-it.fr`.
3. Open the private confirmation link.
4. Verify the nickname, Base role, B1 Cergy role, and removal of Guest.

An allowed email missing from the fixture tests “student not found.” Assign Admin
to test `/createcategory` and `/deletecategory`. Test mode bypasses proof of email
ownership and must never be enabled in production.

## Development checks

Run `make format`, `make lint`, and `make check` before committing.

## Deployment

- Push to `main` → GitHub Actions builds & pushes `ghcr.io/coding-factory-projects/codaemon`,
  then deploys to **staging** automatically and to **production** after manual approval.
- A production server only needs `docker-compose.yml` + `.env`; a test instance
  also needs its private fixture.

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

- learnd → codaemon: `POST /on-promotion-created {name, campus}` (+ `X-Shared-Secret`)
  → `{roleId, categoryId}`
- codaemon → learnd: `PATCH /promotions/students {email, discord_id}` (+ `X-Shared-Secret`)
  → `{firstName, lastName, promotion: {discord_role_id}}`

The shared secret is required in **both** directions from day one.

### Academic-year rollover support required in LearnD

`SchoolClass` must store the Discord category alongside its existing role:

```python
discord_category_id = models.CharField(
    _("discord category id"),
    max_length=255,
    blank=True,
)
```

When LearnD handles `/on-promotion-created`, it must persist both `roleId` and
`categoryId` on the class.

LearnD must expose these shared-secret-protected endpoints to codaemon:

```http
GET /discord/rollover
```

```json
{
  "active_year": {
    "start_year": 2026,
    "school_classes": [
      {
        "id": "class-1",
        "name": "B1",
        "campus": "Paris",
        "discord_role_id": "123",
        "discord_category_id": "456"
      }
    ]
  },
  "archived_years": [
    {
      "start_year": 2025,
      "school_classes": []
    }
  ]
}
```

`archived_years` must contain every archived year, newest or oldest first; the
bot sorts them by `start_year`. Empty Discord IDs are valid for resources that
have not been provisioned yet. Campus is its display name, not its ID.

```http
PATCH /discord/school-classes/{id}
```

```json
{
  "discord_role_id": "123",
  "discord_category_id": "456"
}
```

The admin-only `/rollover` command queries these endpoints. It keeps and renames
the newest archived year using the suffix `· arch. 25-26`, deletes categories,
child channels, and roles for every older archived year, then idempotently
creates or completes the active year's Discord resources. Run it first with
`dry_run:true`; `dry_run:false` applies the plan and updates its ephemeral
response with progress for each class.
