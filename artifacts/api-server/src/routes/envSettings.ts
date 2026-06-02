import { Router, type IRouter, type Request, type Response } from "express";
import { pool } from "@workspace/db";
import { requireApiKey } from "../middlewares/auth";
import { requireAdmin } from "../middlewares/admin";

const router: IRouter = Router();

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

// GET /api/admin/env — list all env settings
router.get("/admin/env", requireApiKey, requireAdmin, async (_req: Request, res: Response) => {
  try {
    await ensureEnvSettingsTable();
    const result = await pool.query(
      `SELECT key, value, description, updated_at FROM env_settings ORDER BY key`
    );
    res.json({ settings: result.rows });
  } catch (err: any) {
    res.status(500).json({ error: err?.message || "Failed to fetch env settings" });
  }
});

// POST /api/admin/env — upsert a key-value pair
router.post("/admin/env", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  const { key, value, description } = req.body ?? {};
  if (!key || typeof key !== "string") {
    res.status(400).json({ error: "key is required" });
    return;
  }
  if (typeof value !== "string") {
    res.status(400).json({ error: "value must be a string" });
    return;
  }
  try {
    await ensureEnvSettingsTable();
    await pool.query(
      `INSERT INTO env_settings (key, value, description, updated_at)
       VALUES ($1, $2, $3, NOW())
       ON CONFLICT (key) DO UPDATE
         SET value = EXCLUDED.value,
             description = EXCLUDED.description,
             updated_at = NOW()`,
      [key.trim(), value, description ?? ""]
    );
    res.json({ ok: true, key: key.trim() });
  } catch (err: any) {
    res.status(500).json({ error: err?.message || "Failed to save env setting" });
  }
});

// DELETE /api/admin/env/:key — delete a key
router.delete("/admin/env/:key", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  const key = req.params.key as string;
  if (!key) {
    res.status(400).json({ error: "key is required" });
    return;
  }
  try {
    await ensureEnvSettingsTable();
    await pool.query(`DELETE FROM env_settings WHERE key = $1`, [key]);
    res.json({ ok: true, key });
  } catch (err: any) {
    res.status(500).json({ error: err?.message || "Failed to delete env setting" });
  }
});

/** Exported helper: read a key from DB env_settings (returns null if not found) */
export async function getEnvSetting(key: string): Promise<string | null> {
  try {
    await ensureEnvSettingsTable();
    const result = await pool.query(
      `SELECT value FROM env_settings WHERE key = $1`,
      [key]
    );
    return result.rows[0]?.value ?? null;
  } catch {
    return null;
  }
}

export default router;
