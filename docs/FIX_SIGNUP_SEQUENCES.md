# Fix signup 500 on Render (no shell)

Free Render has no shell. Use one of these:

## Option A — Supabase SQL Editor (immediate)

1. Open your project in [Supabase](https://supabase.com/dashboard)
2. Go to **SQL Editor** → New query
3. Paste and **Run**:

```sql
-- Re-point every Django auto-id sequence at the highest existing id.
-- Safe to re-run. Fixes: duplicate key on accounts_user_pkey (and similar).

DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT
      n.nspname AS schema_name,
      c.relname AS table_name,
      a.attname AS column_name,
      pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) AS seq
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid
    WHERE c.relkind = 'r'
      AND n.nspname = 'public'
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND pg_get_serial_sequence(quote_ident(n.nspname) || '.' || quote_ident(c.relname), a.attname) IS NOT NULL
  LOOP
    EXECUTE format(
      'SELECT setval(%L, coalesce(max(%I), 1), max(%I) IS NOT NULL) FROM %I.%I',
      r.seq, r.column_name, r.column_name, r.schema_name, r.table_name
    );
  END LOOP;
END $$;
```

4. Try creating a new user again on the live site.

## Option B — Auto-run on every deploy

`render.yaml` now runs `python manage.py fix_sequences` after migrate.
Push/redeploy once so that build step is live; later deploys keep sequences healthy.
