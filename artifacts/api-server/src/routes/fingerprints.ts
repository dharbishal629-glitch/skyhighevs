import { Router, type IRouter, type Request, type Response } from "express";
import { db } from "@workspace/db";
import { fingerprintsTable } from "@workspace/db/schema";
import { eq } from "drizzle-orm";
import { requireApiKey } from "../middlewares/auth";
import { requireAdmin } from "../middlewares/admin";

const router: IRouter = Router();

// ── GET /fingerprints — workers fetch a random enabled fingerprint ──────────
router.get("/fingerprints", requireApiKey, async (_req: Request, res: Response) => {
  try {
    const all = await db
      .select()
      .from(fingerprintsTable)
      .where(eq(fingerprintsTable.enabled, true));

    if (all.length === 0) {
      res.json({ fingerprint: null, total: 0 });
      return;
    }

    const pick = all[Math.floor(Math.random() * all.length)];
    res.json({ fingerprint: pick, total: all.length });
  } catch (err: any) {
    res.status(500).json({ error: err?.message ?? "DB error", fingerprint: null, total: 0 });
  }
});

// ── GET /fingerprints/all — admin list all fingerprints ────────────────────
router.get("/fingerprints/all", requireApiKey, requireAdmin, async (_req: Request, res: Response) => {
  try {
    const all = await db.select().from(fingerprintsTable).orderBy(fingerprintsTable.createdAt);
    res.json({ fingerprints: all, count: all.length });
  } catch (err: any) {
    res.status(500).json({ error: err?.message ?? "DB error", fingerprints: [], count: 0 });
  }
});

// ── POST /fingerprints — add single or bulk fingerprints (admin) ───────────
router.post("/fingerprints", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  try {
    const { data, bulk, enabled = true } = req.body as {
      data?: string;
      bulk?: string[];
      enabled?: boolean;
    };

    const items: string[] = [];
    if (bulk && Array.isArray(bulk)) {
      items.push(...bulk.filter(s => typeof s === "string" && s.trim()));
    } else if (data && typeof data === "string" && data.trim()) {
      items.push(data.trim());
    }

    if (items.length === 0) {
      res.status(400).json({ error: "Provide data (single) or bulk (array) fingerprint strings" });
      return;
    }

    const inserted = await db
      .insert(fingerprintsTable)
      .values(items.map(d => ({ data: d.trim(), enabled: Boolean(enabled) })))
      .returning({ id: fingerprintsTable.id });

    res.json({ success: true, inserted: inserted.length });
  } catch (err: any) {
    res.status(500).json({ error: err?.message ?? "DB error" });
  }
});

// ── PATCH /fingerprints/:id — toggle enabled or update data ────────────────
router.patch("/fingerprints/:id", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id, 10);
    const { enabled, data } = req.body as { enabled?: boolean; data?: string };

    const update: Record<string, unknown> = {};
    if (typeof enabled === "boolean") update.enabled = enabled;
    if (data && typeof data === "string") update.data = data.trim();

    if (Object.keys(update).length === 0) {
      res.status(400).json({ error: "Provide enabled or data to update" });
      return;
    }

    await db.update(fingerprintsTable).set(update).where(eq(fingerprintsTable.id, id));
    res.json({ success: true });
  } catch (err: any) {
    res.status(500).json({ error: err?.message ?? "DB error" });
  }
});

// ── DELETE /fingerprints/:id — remove a single fingerprint ────────────────
router.delete("/fingerprints/:id", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  try {
    const id = parseInt(req.params.id, 10);
    await db.delete(fingerprintsTable).where(eq(fingerprintsTable.id, id));
    res.json({ success: true });
  } catch (err: any) {
    res.status(500).json({ error: err?.message ?? "DB error" });
  }
});

// ── DELETE /fingerprints — clear all fingerprints ─────────────────────────
router.delete("/fingerprints", requireApiKey, requireAdmin, async (_req: Request, res: Response) => {
  try {
    const deleted = await db.delete(fingerprintsTable).returning({ id: fingerprintsTable.id });
    res.json({ success: true, deleted: deleted.length });
  } catch (err: any) {
    res.status(500).json({ error: err?.message ?? "DB error", deleted: 0 });
  }
});

export default router;
