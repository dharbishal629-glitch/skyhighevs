import { Router, type IRouter, type Request, type Response } from "express";
import { pool } from "@workspace/db";
import { requireWorkerKey } from "../middlewares/auth";

const router: IRouter = Router();

/**
 * Keys that must NEVER be sent to workers — these are admin/server-side secrets.
 * Any key matching (case-insensitive) one of these prefixes or exact names is stripped.
 */
const SENSITIVE_KEYS = new Set([
  "admin_access_code",
  "CTRL_TOTP_SECRET",
  "CTRL_API_KEY",
  "WORKER_API_KEY",
  "TOTP_SECRET",
]);

function isSensitive(key: string): boolean {
  const k = key.toUpperCase();
  if (SENSITIVE_KEYS.has(key)) return true;
  if (SENSITIVE_KEYS.has(k)) return true;
  if (k.includes("TOTP") || k.includes("ADMIN") || k === "WORKER_API_KEY") return true;
  return false;
}

async function ensureEnvSettingsTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS env_settings (
      key         TEXT PRIMARY KEY,
      value       TEXT NOT NULL DEFAULT '',
      description TEXT NOT NULL DEFAULT '',
      updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
    )
  `);
}

/**
 * GET /api/tool/worker-env
 *
 * Returns all env_settings entries that are safe for workers, filtered to
 * exclude admin-only secrets. Workers authenticate with their worker key.
 *
 * The launcher calls this endpoint right after key validation, then sets
 * every returned key in os.environ so main.py can read them without any
 * credentials being hardcoded in the launcher script itself.
 */
router.get("/tool/worker-env", requireWorkerKey, async (_req: Request, res: Response) => {
  try {
    await ensureEnvSettingsTable();

    const result = await pool.query(
      `SELECT key, value FROM env_settings ORDER BY key`
    );

    const env: Record<string, string> = {};
    for (const row of result.rows) {
      if (!isSensitive(row.key as string)) {
        env[row.key as string] = row.value as string;
      }
    }

    res.json({ env });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to fetch env settings", detail: err?.message });
  }
});

export default router;
