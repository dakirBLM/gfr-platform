# AGENTS.md — GFR Platform

Context for humans and AI assistants working in this repository.

## What this is

**GFR (Global Forum for Researchers)** is a Django 4.2 academic social + research management platform: profiles, journals (peer review), projects/tasks, conferences, messaging, social feed, notifications.

Python 3.9+. Frontend: Tailwind CDN + templates (no SPA). Demo data lives in committed `db.sqlite3`.

## Quick commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver          # http://127.0.0.1:8000/
python manage.py seed_demo          # reseed demo users/content if needed
python manage.py createsuperuser
```

Settings modules:

- Local / `manage.py`: `gfr.settings.local` (SQLite `db.sqlite3`, `DEBUG=True`)
- Production WSGI: `gfr.settings.production` (env-driven; SQLite until DB switch)
- Importing `gfr.settings` re-exports local for convenience

## App map

| App | Responsibility |
|---|---|
| `core` | Public landing + about |
| `accounts` | Custom `User`, roles, register/login |
| `dashboard` | Logged-in shell; mounts most `/app/` includes |
| `journals` | Journals, manuscripts, review/editor queues |
| `projects` | Projects, members, sections, tasks, milestones |
| `conferences` | Events, registration, abstracts |
| `messaging` | Conversations + unread badge (context processor) |
| `social` | Feed, posts, likes, comments, follows |
| `notifications` | In-app notifications |
| `gfr` | Project package: settings, urls, wsgi, context processors |

Templates are **project-level** under `templates/`, not inside each app. Static assets: `static/`. Uploads: `media/` (tracked for demo).

## URL layout

- `/` — `core` (public)
- `/accounts/` — auth (`accounts` namespace)
- `/app/` — authenticated area (`dashboard` + includes)
- `/admin/` — Django admin

Feature routes are included from `dashboard/urls.py` (journals, projects, messages, conferences, social, notifications). Researcher directory lives under `/app/researchers/`.

## Auth & roles

- `AUTH_USER_MODEL = accounts.User`
- Roles: `accounts.Role` (student, researcher, professor, reviewer, editor, …)
- Permission matrix is documented in `README.md`; enforce in views/forms, not only UI

## Where to change what

| Goal | Start here |
|---|---|
| New public page | `core/views.py`, `core/urls.py`, `templates/core/` |
| Profile / directory | `dashboard/views.py`, `accounts/models.py`, `templates/dashboard/`, `templates/researchers/` |
| Journal workflow | `journals/` models, views, `templates/journals/` |
| Project/tasks | `projects/` models, views, `templates/projects/` |
| Nav / layout | `templates/base.html`, `templates/components/navbar.html`, `templates/dashboard/_sidebar.html` |
| Settings / deploy | `gfr/settings/`, `docs/DEPLOY_PYTHONANYWHERE.md` |
| Demo data | `accounts/management/commands/seed_demo.py` |

## Conventions for contributors & agents

- Prefer small PRs: one feature or fix.
- Keep the committed SQLite demo DB unless migrations require a careful update; do not wipe casually.
- Add migrations when models change; do not edit old migrations that others may have applied.
- Match existing view/form/template style in the target app.
- Do not commit `.env`, `.venv/`, or secrets.
- Production secrets and hostnames come from environment variables (see `.env.example`).

## Deploy note

PythonAnywhere pulls `main`, uses `gfr.settings.production`, and can keep SQLite first. Switching to MySQL later is env-only (`DATABASE_*`). Details: `docs/DEPLOY_PYTHONANYWHERE.md`. Architecture overview: `docs/ARCHITECTURE.md`. Contribution flow: `CONTRIBUTING.md`.
