/**
 * Run this ONCE after deploying to create the database tables.
 * Usage: DATABASE_URL=your_url node setup-db.js
 */
import pg from "pg";

const { Client } = pg;

const sql = `
CREATE TABLE IF NOT EXISTS workers (
  id          SERIAL PRIMARY KEY,
  discord_id  TEXT NOT NULL UNIQUE,
  discord_username TEXT NOT NULL,
  worker_key  TEXT NOT NULL UNIQUE,
  status      TEXT NOT NULL DEFAULT 'VALID',
  expires_at  TIMESTAMP,
  created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tokens (
  id          SERIAL PRIMARY KEY,
  token       TEXT NOT NULL UNIQUE,
  email       TEXT,
  status      TEXT NOT NULL DEFAULT 'VALID',
  worker_id   INTEGER REFERENCES workers(id),
  worker_key  TEXT,
  created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
  checked_at  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_stats (
  id               SERIAL PRIMARY KEY,
  worker_id        INTEGER NOT NULL REFERENCES workers(id),
  date             TEXT NOT NULL,
  tokens_generated INTEGER NOT NULL DEFAULT 0,
  tokens_valid     INTEGER NOT NULL DEFAULT 0,
  tokens_locked    INTEGER NOT NULL DEFAULT 0,
  tokens_invalid   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tool_config (
  id         SERIAL PRIMARY KEY,
  config     JSON NOT NULL DEFAULT '{}',
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
`;

const client = new Client({ connectionString: process.env.DATABASE_URL });

try {
  await client.connect();
  await client.query(sql);
  console.log("✅ Database tables created successfully.");
} catch (err) {
  console.error("❌ Error creating tables:", err.message);
  process.exit(1);
} finally {
  await client.end();
}
