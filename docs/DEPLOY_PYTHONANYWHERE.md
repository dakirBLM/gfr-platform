# Deploy on PythonAnywhere

This guide assumes a **new** clone of `gfr-platform` on a PythonAnywhere account. Keep SQLite at first; switch MySQL later via env.

## 1. Clone

In a Bash console:

```bash
cd ~
git clone https://github.com/dakirBLM/gfr-platform.git
cd gfr-platform
```

## 2. Virtualenv + dependencies

```bash
python3.10 -m venv ~/.virtualenvs/gfr-platform
source ~/.virtualenvs/gfr-platform/bin/activate
pip install -r requirements.txt
# If using MySQL later:
# pip install mysqlclient
```

## 3. Environment

```bash
cp .env.example .env
nano .env
```

Minimum production values:

```bash
DJANGO_SETTINGS_MODULE=gfr.settings.production
DJANGO_SECRET_KEY=generate-a-long-random-string
DJANGO_ALLOWED_HOSTS=YOURUSERNAME.pythonanywhere.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://YOURUSERNAME.pythonanywhere.com
```

SQLite (interim — keeps the committed demo DB):

```bash
DATABASE_ENGINE=django.db.backends.sqlite3
DATABASE_NAME=/home/YOURUSERNAME/gfr-platform/db.sqlite3
```

## 4. Migrate & static files

```bash
source ~/.virtualenvs/gfr-platform/bin/activate
cd ~/gfr-platform
export DJANGO_SETTINGS_MODULE=gfr.settings.production
# Export the same secrets as in .env, or rely on dotenv loading from project .env
python manage.py migrate
python manage.py collectstatic --noinput
```

## 5. Web app WSGI

In the PythonAnywhere **Web** tab:

- Source code: `/home/YOURUSERNAME/gfr-platform`
- Working directory: `/home/YOURUSERNAME/gfr-platform`
- Virtualenv: `/home/YOURUSERNAME/.virtualenvs/gfr-platform`

Edit the WSGI file to something like:

```python
import os
import sys

project_home = '/home/YOURUSERNAME/gfr-platform'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ['DJANGO_SETTINGS_MODULE'] = 'gfr.settings.production'

from dotenv import load_dotenv
load_dotenv(os.path.join(project_home, '.env'))

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Static files mapping (Web tab):

| URL | Directory |
|---|---|
| `/static/` | `/home/YOURUSERNAME/gfr-platform/staticfiles` |
| `/media/` | `/home/YOURUSERNAME/gfr-platform/media` |

WhiteNoise also serves collected static from the app if mappings are incomplete.

Reload the web app.

## 6. Updating from GitHub (after PRs merge)

```bash
cd ~/gfr-platform
git pull origin main
source ~/.virtualenvs/gfr-platform/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Then **Reload** on the Web tab.

## 7. Switching to MySQL later

1. Create a MySQL DB in the PythonAnywhere Databases tab.
2. `pip install mysqlclient`
3. Update `.env`:

```bash
DATABASE_ENGINE=django.db.backends.mysql
DATABASE_NAME=YOURUSERNAME$gfr
DATABASE_USER=YOURUSERNAME
DATABASE_PASSWORD=...
DATABASE_HOST=YOURUSERNAME.mysql.pythonanywhere-services.com
DATABASE_PORT=3306
```

4. Run `python manage.py migrate` (and load/seed data as needed — do not assume SQLite data auto-copies).
5. Reload the web app.

## Collaboration loop

Contributors open PRs on GitHub → you merge to `main` → `git pull` on PythonAnywhere → migrate / collectstatic → reload.
