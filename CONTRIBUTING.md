# Contributing to GFR Platform

Thanks for helping improve the Global Forum for Researchers.

## Workflow

1. Fork [dakirBLM/gfr-platform](https://github.com/dakirBLM/gfr-platform) (after it exists).
2. Clone your fork and create a branch: `git checkout -b feature/short-description` or `fix/...`.
3. Make focused changes (one concern per PR).
4. Run the app locally and smoke-test the paths you touched.
5. Open a Pull Request against `main` using the PR template.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # optional overrides
python manage.py migrate
python manage.py runserver
```

This repo ships with `db.sqlite3` (demo data). Prefer keeping it unless your change requires a migration + reseed.

If you need a clean demo set:

```bash
python manage.py seed_demo
```

## Project conventions

- Django apps live at the repo root (`accounts`, `journals`, `projects`, …).
- Templates live in `templates/<app>/` (project-level templates, not per-app `templates/` folders).
- App URLs under `/app/` are included from `dashboard/urls.py`.
- Custom user model: `accounts.User` (`AUTH_USER_MODEL`).
- Settings: `gfr.settings.local` (dev) / `gfr.settings.production` (deploy).
- Read [AGENTS.md](AGENTS.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before large changes.

## Pull requests

- Describe **why** the change exists.
- List how you tested it.
- Include migrations when models change.
- Do not commit `.env`, virtualenvs, or unrelated reformatting.

## Issues

Use the GitHub issue templates for bugs and feature requests.
