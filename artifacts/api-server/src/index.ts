import app from "./app";
import { logger } from "./lib/logger";
import { pool } from "@workspace/db";

process.on("uncaughtException", (err) => {
  logger.error({ err }, "Uncaught exception — server continues");
});

process.on("unhandledRejection", (reason) => {
  logger.error({ reason }, "Unhandled rejection — server continues");
});

const rawPort = process.env["PORT"];

if (!rawPort) {
  throw new Error(
    "PORT environment variable is required but was not provided.",
  );
}

const port = Number(rawPort);

if (Number.isNaN(port) || port <= 0) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

async function initDb() {
  try {
    await pool.query(`
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
    `);
    logger.info("Database tables verified/created");
  } catch (err) {
    logger.error({ err }, "DB init failed — server will still start");
  }
}

const KEEPALIVE_URL = process.env.CTRL_API_URL || "";
const PING_INTERVAL_MS = 14 * 60 * 1000;

function startKeepAlive() {
  if (!KEEPALIVE_URL) return;
  setInterval(async () => {
    try {
      const res = await fetch(`${KEEPALIVE_URL}/api/health`, { signal: AbortSignal.timeout(10000) });
      logger.info({ status: res.status }, "Keep-alive ping sent");
    } catch (err: any) {
      logger.warn({ err: err?.message }, "Keep-alive ping failed");
    }
  }, PING_INTERVAL_MS);
  logger.info({ url: KEEPALIVE_URL }, "Keep-alive pinger started");
}

initDb().then(() => {
  app.listen(port, (err) => {
    if (err) {
      logger.error({ err }, "Error listening on port");
      process.exit(1);
    }
    logger.info({ port }, "Server listening");
    startKeepAlive();
  });
});
