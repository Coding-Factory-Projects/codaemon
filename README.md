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
  - /onboard (confirm page)    - /createcategory  (admin)
  - /healthz                   - /deletecategory  (admin)
                               - /renamecategory  (admin)
                               - /rollover        (admin)
                               - /onboard         (students)
        \__ both call bot/discord_api/ (Discord REST) __/
```

- The **gateway** worker handles slash commands (it makes an *outbound* WebSocket
  to Discord — Discord never needs codaemon's URL).
- The **web** process handles the onboarding page and calls Discord and learnd
  over REST. No async needed there.

## Fixture-backed onboarding

Onboarding configuration has two independent settings:

- `STUDENT_BACKEND=fixture|learnd` selects the student source. The fixture backend
  also finds or creates Discord roles from promotion names in the fixture.
- `ONBOARD_DELIVERY=email|link` either sends the confirmation email or returns the
  link ephemerally in Discord. Link delivery bypasses proof of email ownership and
  must never be used in production.

Local development defaults to `fixture` and `link`. Dev and int also allow
`gmail.com` addresses for test mailboxes; production keeps only school domains.

### 1. Prepare Discord

1. Create a Discord application and bot, then enable **Server Members Intent**.
2. Install it on a disposable guild with `bot` and `applications.commands` scopes.
   Administrator permission is simplest for this test-only guild.

### 2. Run locally

Install dependencies and create the local runtime fixture:

```bash
make install
make dev
cp fixtures/students.example.json fixtures/students.json
```

`make dev` renders `.env` with Ansible. The only development secret, the Discord
bot token, is read from `op://Private/Discord/codaemon-dev/bot token`; sign in to
the 1Password CLI first. Non-secret development configuration lives in
`ansible/vars/dev.yml`; rerun `make dev` after changing it.

With the fixture backend, role IDs can remain empty. Start the two processes:

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
`students.json` inside it. Configure the Discord values above, then set:

```dotenv
STUDENT_BACKEND=fixture
ONBOARD_DELIVERY=email
LEARND_FIXTURE_PATH=fixtures/students.json
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

With `STUDENT_BACKEND=fixture`, `runbot` finds or creates Admin, Base, Guest,
Product Owners, and every promotion role declared in the fixture. Existing roles
are reused; duplicate or reserved names are rejected. Restart `runbot` after
adding or renaming a promotion.

1. Assign Guest to the test member.
2. Run `/onboard ada.lovelace.test@edu.esiee-it.fr`.
3. Open the confirmation link received by email or returned privately in Discord.
4. Verify the nickname, Base role, B1 Cergy role, and removal of Guest.

An allowed email missing from the fixture tests “student not found.” Assign Admin
to test `/createcategory`, `/renamecategory`, `/deletecategory`, and `/resetmember`.
`/resetmember` is available in `dev` and `int`, but is not registered in `prod`;
with the LearnD backend, it reads active promotion role IDs from LearnD.

## Development checks

Run `make format`, `make lint`, and `make check` before committing.

## Deployment

- Push to `main` → GitHub Actions checks the project, builds and pushes
  `ghcr.io/coding-factory-projects/codaemon`, then deploys **int** automatically.
- Images are tagged with the commit SHA, `latest`, and the application version.
  The release part is incremented manually in `pyproject.toml`; CI appends the
  six-character commit SHA, for example `2026.01-ab3832`.
- Environment deployment is implemented once in the reusable
  `deploy-environment.yml` workflow. The manual `Deploy production` workflow
  promotes an existing integration-tested image through the same workflow.
- `/healthz` returns the deployed version and CI verifies it after deployment.

### One-time int server setup

The int deployment runs on the `gryt-int` SSH target in `/srv/codaemon-int`, with
Nginx proxying `codaemon-int.codingfactory.tech` to `127.0.0.1:8200`. Install
Docker, Nginx, and the Certbot-managed certificate manually. Once the certificate
exists, install the tracked application directory and Nginx vhost with:

```bash
make configure-int
```

The inventory uses the `gryt-int` SSH target. Normal application deployments do
not modify the shared Nginx configuration. The playbook manages only Codaemon's
vhost and assumes Certbot handles certificate renewal.

### One-time prod server setup

Production runs on the `gryt-coding` SSH target in `/srv/codaemon-prod`, with
Nginx proxying `codaemon.codingfactory.tech` to `127.0.0.1:8200`. Once the
manually provisioned certificate exists, install the application directory and
Nginx vhost with:

```bash
make configure-prod
```

Normal deployments only copy the Compose and environment files, then restart
the containers. Certificate issuance and renewal remain managed outside this
playbook.

### GitHub configuration
Create the `int` **Environment** with these secrets:

| Secret | Meaning |
|---|---|
| `SSH_HOST` / `SSH_USER` / `SSH_KEY` | deploy SSH target (dedicated key) |
| `SSH_FINGERPRINT` | SHA256 host-key fingerprint for `gryt-int` |
| `DOTENV` | secret `.env` values for int (Discord, `LEARND_API_TOKEN`, and SMTP credentials) |

Static int configuration, including non-secret SMTP settings, lives in
`.github/environments/int.env` and uses learnd with email delivery. Each int
deployment still copies `fixtures/students.example.json` to the server so the
fixture backend remains available.

Create the `prod` **Environment** with the same four secrets, pointed at
`gryt-coding` and the production credentials. Production's `DOTENV` must include
the Discord credentials, `DJANGO_SECRET_KEY`, `LEARND_API_TOKEN`, and SMTP
credentials. Static production configuration lives in
`.github/environments/prod.env` and uses LearnD with email delivery.

The workflow combines static configuration with the secret `DOTENV`, version,
and immutable image tag. Make the GHCR package public so the server can pull
without credentials. To deploy production, run the `Deploy production` workflow
on the Git ref to promote. It derives the immutable image tag and version, and
refuses deployment unless that exact commit has a successful int workflow run.

## learnd contract

Codaemon authenticates to `LEARND_BASE_URL/api/v1/` with:

```http
Authorization: Bearer <LEARND_API_TOKEN>
```

Onboarding looks up the active student and school-class membership through
`school-students/`, `school-class-students/`, and `school-classes/`, then patches
the student's `discord_user_id`.

The admin-only `/rollover` command reads `academic-years/` and `school-classes/`.
It keeps and renames the newest archived year using the suffix `· arch. 25-26`,
deletes categories, child channels, and roles for every older archived year,
then idempotently creates or completes the active year's Discord resources and
patches their Discord IDs back to `school-classes/{id}/`. Run it first with
`dry_run:true`; `dry_run:false` applies the plan and reports progress.
