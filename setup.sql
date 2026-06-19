-- ============================================================
-- CTRL.PNL — Full Database Setup Script
-- Safe to run on both FRESH and EXISTING databases.
-- Every statement uses IF NOT EXISTS / IF NOT EXISTS guards
-- so re-running it never breaks anything.
-- ============================================================

-- ── workers ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workers (
  id               SERIAL PRIMARY KEY,
  discord_id       TEXT NOT NULL UNIQUE,
  discord_username TEXT NOT NULL,
  worker_key       TEXT NOT NULL UNIQUE,
  status           TEXT NOT NULL DEFAULT 'VALID',
  expires_at       TIMESTAMP,
  created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Worker Edits columns (safe to add on top of existing table)
ALTER TABLE workers ADD COLUMN IF NOT EXISTS worker_edits_enabled    BOOLEAN  NOT NULL DEFAULT FALSE;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS worker_proxy             TEXT;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS worker_proxy_enabled     BOOLEAN  NOT NULL DEFAULT FALSE;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS worker_adb_enabled       BOOLEAN  NOT NULL DEFAULT FALSE;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS worker_nopecha_key       TEXT;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS worker_nopecha_enabled   BOOLEAN  NOT NULL DEFAULT FALSE;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS worker_cooldown          INTEGER  NOT NULL DEFAULT 0;
-- Legacy column (unused but may exist in old DBs — keep to avoid errors)
ALTER TABLE workers ADD COLUMN IF NOT EXISTS worker_fingerprint_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- ── tokens ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tokens (
  id           SERIAL PRIMARY KEY,
  token        TEXT NOT NULL UNIQUE,
  email        TEXT,
  account_pass TEXT,
  status       TEXT NOT NULL DEFAULT 'VALID',
  worker_id    INTEGER REFERENCES workers(id),
  worker_key   TEXT,
  created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
  checked_at   TIMESTAMP
);

ALTER TABLE tokens ADD COLUMN IF NOT EXISTS account_pass TEXT;
ALTER TABLE tokens ADD COLUMN IF NOT EXISTS worker_key   TEXT;

-- ── daily_stats ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_stats (
  id               SERIAL PRIMARY KEY,
  worker_id        INTEGER NOT NULL REFERENCES workers(id),
  date             TEXT NOT NULL,
  tokens_generated INTEGER NOT NULL DEFAULT 0,
  tokens_valid     INTEGER NOT NULL DEFAULT 0,
  tokens_locked    INTEGER NOT NULL DEFAULT 0,
  tokens_invalid   INTEGER NOT NULL DEFAULT 0
);

-- ── tool_config ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tool_config (
  id         SERIAL PRIMARY KEY,
  config     JSON NOT NULL DEFAULT '{}',
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ── fingerprints ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fingerprints (
  id         SERIAL PRIMARY KEY,
  data       TEXT NOT NULL,
  enabled    BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ── Verify ────────────────────────────────────────────────────
-- Run this to confirm all tables exist after setup:
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
