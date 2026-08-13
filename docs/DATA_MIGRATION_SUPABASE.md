# Supabase Data Migration

How the existing production data (SQLite + filesystem media) was moved to the
new Supabase project (PostgreSQL + Storage) without loss, and how to repeat it
for future environments.

## Result (this migration)

- **297 records / 25 models** imported from the old production SQLite export
  via `dumpdata`/`loaddata` (natural keys; excludes `auth.permission`,
  `contenttypes`, `sessions`, `admin.logentry`).
- **27 tables verified**: row counts match the source exactly (0 mismatches);
  e.g. 23 users, 8 projects, 3 journals, 27 messages, 15 posts.
- **10 media files** uploaded to the `gfr-media` bucket with the same relative
  paths the app expects (`avatars/...`, `task_submissions/...` - no `media/`
  prefix). All DB-referenced files exist in the bucket and return HTTP 200 via
  the public storage URL.
- **29 PostgreSQL sequences** re-pointed with `python manage.py fix_sequences`
  (required after importing explicit primary keys; also run on Render builds).

### Adjustments made (data only)

- `accounts.ResearchInterest` pk=32 was **truncated from 86 to 80 chars** to
  fit the current `CharField(max_length=80)` - the old schema allowed longer
  values. Only record affected.
- 4 junk signup accounts left from earlier live testing (`dd`,
  `ddddadewddwqd`, `ddddddd`, `ddddddd.dd`) and 1 stray test avatar object
  were removed from the target project. Verified zero FK dependencies first.
- 2 files in the media export are not referenced by any DB row (`avatars/-3.jpg`,
  `avatars/alice-photo.jpg`); kept as-is, harmless.

## Procedure (repeatable)

### 1. Isolate the source (never work on the original)

```bash
mkdir -p migration_workspace
cp /path/to/old/db.sqlite3 migration_workspace/db_source_readonly.sqlite3
chmod 444 migration_workspace/db_source_readonly.sqlite3
unzip /path/to/media.zip -d migration_workspace/
# media.zip should expand to migration_workspace/media/avatars/..., etc.
```

Keep `migration_workspace/` out of git (ignored) and delete it after the
migration is confirmed.

### 2. Export

Point Django at the readonly copy (e.g. a small `settings_source.py` in the
workspace that imports `gfr.settings.local` and overrides `DATABASES`), then:

```bash
python manage.py dumpdata \
  --natural-foreign --natural-primary \
  --exclude auth.permission --exclude contenttypes \
  --exclude sessions --exclude admin.logentry \
  --indent 2 --output migration_workspace/data_export.json
```

### 3. Build the target schema

```bash
DJANGO_SETTINGS_MODULE=gfr.settings.production python manage.py migrate
```

### 4. Import + fix sequences

```bash
DJANGO_SETTINGS_MODULE=gfr.settings.production python manage.py loaddata migration_workspace/data_export.json
DJANGO_SETTINGS_MODULE=gfr.settings.production python manage.py fix_sequences
```

If `loaddata` hits an `IntegrityError`, import per-app in dependency order
(accounts -> journals/projects/conferences -> social/messaging/notifications)
instead of the whole fixture at once.

### 5. Upload media (same relative paths, no `media/` prefix)

Use the S3-compatible gateway (boto3) with `SUPABASE_S3_*` env vars; for every
file under `migration_workspace/media/` upload with the path relative to that
root (e.g. `avatars/alice-photo.jpg`, `task_submissions/task_result.pdf`).

### 6. Verify

- Compare row counts per model between source DB and target (ORM count vs
  source query).
- Spot-check relationships (memberships, manuscripts, conversations).
- `HEAD` each DB-referenced media path against `SUPABASE_MEDIA_URL`.
- Do not touch the original source until the owner confirms.

## Environment notes

- Django 4.2.30 must run on Python 3.12 (`.python-version`); Python 3.14
  breaks the admin (`'super' object has no attribute 'dicts'`).
- `.env` (ignored) holds the Supabase connection values for this migration.
- `render.yaml` runs `fix_sequences` automatically during builds.
