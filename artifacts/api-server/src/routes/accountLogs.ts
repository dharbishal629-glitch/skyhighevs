import { Router, type IRouter, type Request, type Response } from "express";
import { pool } from "@workspace/db";
import { requireApiKey } from "../middlewares/auth";

const router: IRouter = Router();

async function ensureTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS account_logs (
      id           SERIAL PRIMARY KEY,
      email        TEXT NOT NULL,
      account_pass TEXT,
      token        TEXT NOT NULL,
      email_pass   TEXT,
      is_hotmail   BOOLEAN NOT NULL DEFAULT false,
      verified     BOOLEAN NOT NULL DEFAULT false,
      worker_id    TEXT,
      sent         BOOLEAN NOT NULL DEFAULT false,
      created_at   TIMESTAMP NOT NULL DEFAULT NOW()
    )
  `);
}

router.post("/logs/account-created", requireApiKey, async (req: Request, res: Response) => {
  try {
    await ensureTable();
    const { email, accountPass, token, emailPass, isHotmail, verified, workerId } = req.body;
    if (!email || !token) {
      res.status(400).json({ error: "email and token are required" });
      return;
    }
    const result = await pool.query(
      `INSERT INTO account_logs (email, account_pass, token, email_pass, is_hotmail, verified, worker_id)
       VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id`,
      [email, accountPass || null, token, emailPass || null, isHotmail || false, verified || false, workerId || null]
    );
    res.json({ id: result.rows[0].id });
  } catch (err: any) {
    res.status(500).json({ error: err?.message || "Failed to save log" });
  }
});

router.get("/logs/account-created/pending", requireApiKey, async (_req: Request, res: Response) => {
  try {
    await ensureTable();
    const result = await pool.query(
      `SELECT id, email, account_pass, token, email_pass, is_hotmail, verified, worker_id, created_at
       FROM account_logs WHERE sent = false ORDER BY created_at ASC LIMIT 20`
    );
    res.json({ logs: result.rows });
  } catch (err: any) {
    res.status(500).json({ error: err?.message || "Failed to fetch pending logs" });
  }
});

router.patch("/logs/account-created/:id/sent", requireApiKey, async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id, 10);
    if (isNaN(id)) {
      res.status(400).json({ error: "Invalid id" });
      return;
    }
    await pool.query(`UPDATE account_logs SET sent = true WHERE id = $1`, [id]);
    res.json({ ok: true });
  } catch (err: any) {
    res.status(500).json({ error: err?.message || "Failed to mark log as sent" });
  }
});

export default router;
