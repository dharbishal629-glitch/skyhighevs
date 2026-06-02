import { Router, type IRouter, type Request, type Response } from "express";
import { db, pool } from "@workspace/db";
import { toolConfigTable, workersTable } from "@workspace/db/schema";
import { eq } from "drizzle-orm";
import { requireApiKey } from "../middlewares/auth";
import { requireAdmin } from "../middlewares/admin";

const router: IRouter = Router();

// ── Self-healing table creation ───────────────────────────────────────────────

async function ensurePayoutTables() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS payout_methods (
      id           SERIAL PRIMARY KEY,
      discord_id   TEXT NOT NULL UNIQUE,
      method       TEXT NOT NULL,
      updated_at   TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS payout_requests (
      id                SERIAL PRIMARY KEY,
      discord_id        TEXT NOT NULL,
      discord_username  TEXT NOT NULL,
      valid_count       INTEGER NOT NULL DEFAULT 0,
      price_per_token   NUMERIC(10,4) NOT NULL DEFAULT 0,
      amount_usd        NUMERIC(10,4) NOT NULL DEFAULT 0,
      payout_method     TEXT NOT NULL DEFAULT '',
      status            TEXT NOT NULL DEFAULT 'PENDING',
      created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
      paid_at           TIMESTAMP
    );
  `);
}

// ── Token Price (stored in tool_config JSON) ──────────────────────────────────

async function getTokenPrice(): Promise<number> {
  const rows = await db.select().from(toolConfigTable).limit(1);
  if (rows.length === 0) return 0;
  const cfg = rows[0].config as Record<string, unknown>;
  return typeof cfg.tokenPrice === "number" ? cfg.tokenPrice : 0;
}

router.get("/payout/price", requireApiKey, async (_req: Request, res: Response) => {
  try {
    const price = await getTokenPrice();
    res.json({ tokenPrice: price });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to get price", detail: err?.message });
  }
});

router.put("/payout/price", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  try {
    const { price } = req.body as { price: number };
    if (typeof price !== "number" || price < 0) {
      res.status(400).json({ error: "price must be a non-negative number" });
      return;
    }

    const rows = await db.select().from(toolConfigTable).limit(1);
    if (rows.length === 0) {
      await db.insert(toolConfigTable).values({ config: { tokenPrice: price } });
    } else {
      const current = rows[0].config as Record<string, unknown>;
      await db.update(toolConfigTable)
        .set({ config: { ...current, tokenPrice: price }, updatedAt: new Date() })
        .where(eq(toolConfigTable.id, rows[0].id));
    }

    res.json({ success: true, tokenPrice: price });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to set price", detail: err?.message });
  }
});

// ── Payout Method ─────────────────────────────────────────────────────────────

router.get("/payout/method/:discordId", requireApiKey, async (req: Request, res: Response) => {
  try {
    await ensurePayoutTables();
    const discordId = req.params.discordId as string;
    const result = await pool.query(
      "SELECT method FROM payout_methods WHERE discord_id = $1 LIMIT 1",
      [discordId]
    );
    if (result.rows.length === 0) {
      res.json({ method: null });
    } else {
      res.json({ method: result.rows[0].method });
    }
  } catch (err: any) {
    res.status(500).json({ error: "Failed to get payout method", detail: err?.message });
  }
});

router.put("/payout/method", requireApiKey, async (req: Request, res: Response) => {
  try {
    await ensurePayoutTables();
    const { discordId, method } = req.body as { discordId: string; method: string };
    if (!discordId || !method) {
      res.status(400).json({ error: "discordId and method are required" });
      return;
    }

    await pool.query(
      `INSERT INTO payout_methods (discord_id, method, updated_at)
       VALUES ($1, $2, NOW())
       ON CONFLICT (discord_id) DO UPDATE SET method = $2, updated_at = NOW()`,
      [discordId, method.trim()]
    );

    res.json({ success: true, method: method.trim() });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to set payout method", detail: err?.message });
  }
});

// ── Payout Requests ───────────────────────────────────────────────────────────

router.get("/payout/requests", requireApiKey, requireAdmin, async (_req: Request, res: Response) => {
  try {
    await ensurePayoutTables();
    const result = await pool.query(
      `SELECT * FROM payout_requests ORDER BY created_at DESC`
    );
    res.json({ requests: result.rows });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to get payout requests", detail: err?.message });
  }
});

router.post("/payout/request", requireApiKey, async (req: Request, res: Response) => {
  try {
    await ensurePayoutTables();
    const { discordId, discordUsername, validCount, pricePerToken, amountUsd, payoutMethod } =
      req.body as {
        discordId: string;
        discordUsername: string;
        validCount: number;
        pricePerToken: number;
        amountUsd: number;
        payoutMethod: string;
      };

    if (!discordId || !discordUsername || typeof validCount !== "number") {
      res.status(400).json({ error: "discordId, discordUsername, and validCount are required" });
      return;
    }

    // Check for existing PENDING request
    const existing = await pool.query(
      "SELECT id FROM payout_requests WHERE discord_id = $1 AND status = 'PENDING' LIMIT 1",
      [discordId]
    );
    if (existing.rows.length > 0) {
      res.status(409).json({ error: "You already have a pending payout request." });
      return;
    }

    const result = await pool.query(
      `INSERT INTO payout_requests
         (discord_id, discord_username, valid_count, price_per_token, amount_usd, payout_method, status, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, 'PENDING', NOW())
       RETURNING id`,
      [discordId, discordUsername, validCount, pricePerToken, amountUsd, payoutMethod || ""]
    );

    res.json({ success: true, requestId: result.rows[0].id });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to create payout request", detail: err?.message });
  }
});

router.post("/payout/mark-paid/:id", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  try {
    await ensurePayoutTables();
    const id = req.params.id as string;
    const result = await pool.query(
      `UPDATE payout_requests SET status = 'PAID', paid_at = NOW() WHERE id = $1 RETURNING *`,
      [id]
    );
    if (result.rows.length === 0) {
      res.status(404).json({ error: "Payout request not found" });
      return;
    }
    res.json({ success: true, request: result.rows[0] });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to mark paid", detail: err?.message });
  }
});

router.post("/payout/cancel/:discordId", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  try {
    await ensurePayoutTables();
    const discordId = req.params.discordId as string;
    await pool.query(
      `UPDATE payout_requests SET status = 'CANCELLED' WHERE discord_id = $1 AND status = 'PENDING'`,
      [discordId]
    );
    res.json({ success: true });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to cancel request", detail: err?.message });
  }
});

export default router;
