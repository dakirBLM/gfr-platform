# GFR — Global Forum for Researchers

An international academic social network and research management platform built with Django 4.2.

**Repository:** [dakirBLM/gfr-platform](https://github.com/dakirBLM/gfr-platform) (public — fork, branch, open PRs)

## Features

| Module | What it does |
|---|---|
| **Accounts** | Custom user model, role-based permissions, avatar upload |
| **Academic profile** | Biography, ORCID, research interests, education, publications |
| **Researcher directory** | Searchable member directory with role/country filters |
| **Journals** | Peer-reviewed journals, manuscript submission & review workflow |
| **Research projects** | Create teams, assign tasks, track milestones |
| **Conferences** | Event listings, registration, abstract submission |
| **Messaging** | Private conversations between members with unread badge |
| **Social** | Feed, posts, likes, comments, follows |
| **Dashboard** | Live stats, quick actions, sidebar navigation |

## Quick start

```bash
git clone https://github.com/dakirBLM/gfr-platform.git
cd gfr-platform
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/

This repo includes a committed `db.sqlite3` with demo data. Deployment can keep SQLite temporarily and switch to MySQL later (see [docs/DEPLOY_PYTHONANYWHERE.md](docs/DEPLOY_PYTHONANYWHERE.md)).

Optional reseed:

```bash
python manage.py seed_demo
python manage.py createsuperuser
```

## Contributing

We welcome features and fixes via pull requests.

1. Read [CONTRIBUTING.md](CONTRIBUTING.md)
2. Skim [AGENTS.md](AGENTS.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (also used by AI assistants)
3. Fork → branch → PR against `main`

## Demo accounts

| Username | Password | Role |
|---|---|---|
| `admin` | `admin12345` | Superuser (Django admin) |
| `alice` | `SecurePass!9q` | Researcher |
| `omar_ibrahim` | `Demo!2024gfr` | Professor |
| `lena_vogel` | `Demo!2024gfr` | Researcher |
| `mei_lin` | `Demo!2024gfr` | Editor (journal editor) |
| `fatima_nasser` | `Demo!2024gfr` | Reviewer |
| `yuki_tanaka` | `Demo!2024gfr` | Professor |
| `juan_reyes` | `Demo!2024gfr` | Researcher |
| `kwame_asante` | `Demo!2024gfr` | Researcher |
| `sofia_rossi` | `Demo!2024gfr` | Postgraduate Student |

## URL map

| URL | Description |
|---|---|
| `/` | Public landing page |
| `/about/` | About GFR |
| `/accounts/register/` | Join the platform |
| `/accounts/login/` | Sign in |
| `/app/` | Dashboard home |
| `/app/profile/` | Academic profile editor |
| `/app/researchers/` | Researcher directory |
| `/app/researchers/<username>/` | Public researcher profile |
| `/app/journals/` | Journal listing |
| `/app/journals/<slug>/` | Journal detail + submit |
| `/app/journals/manuscripts/` | My submissions |
| `/app/journals/review/` | Reviewer queue |
| `/app/journals/editor/` | Editor queue |
| `/app/projects/` | Research project directory |
| `/app/projects/new/` | Create a project |
| `/app/projects/<slug>/` | Project detail + tasks + milestones |
| `/app/conferences/` | Conferences & workshops |
| `/app/messages/` | Message inbox |
| `/app/social/` | Social feed |
| `/admin/` | Django admin |

## Role permission matrix

| Feature | Student | Researcher | Professor | Reviewer | Editor | Admin |
|---|---|---|---|---|---|---|
| View journals | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Submit manuscript | ✗ | ✓ | ✓ | ✗ | ✓ | ✓ |
| Peer review | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ |
| Create project | ✗ | ✓ | ✓ | ✗ | ✗ | ✓ |
| Manage users | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |

## Deploy

See [docs/DEPLOY_PYTHONANYWHERE.md](docs/DEPLOY_PYTHONANYWHERE.md).

Settings: `gfr.settings.local` (dev) · `gfr.settings.production` (host).

## Tech stack

- **Backend:** Django 4.2 LTS, SQLite (demo / interim), MySQL-ready via env
- **Frontend:** Tailwind CSS (CDN), Django templates
- **Static on deploy:** WhiteNoise + `collectstatic`
- **Image processing:** Pillow
- **Python:** 3.9+
