import { Router, type IRouter, type Request, type Response } from "express";
import { db } from "@workspace/db";
import { workersTable, tokensTable, dailyStatsTable } from "@workspace/db/schema";
import { eq, desc, sql } from "drizzle-orm";
import { requireWorkerKey } from "../middlewares/auth";

const router: IRouter = Router();

/** GET /api/worker/me — worker profile + lifetime stats */
router.get("/worker/me", requireWorkerKey, async (req: Request, res: Response) => {
  try {
    const worker = (req as any).worker;

    const stats = await db
      .select({
        tokensGenerated: sql<number>`COALESCE(SUM(${dailyStatsTable.tokensGenerated}), 0)`,
        tokensValid: sql<number>`COALESCE(SUM(${dailyStatsTable.tokensValid}), 0)`,
        tokensLocked: sql<number>`COALESCE(SUM(${dailyStatsTable.tokensLocked}), 0)`,
        tokensInvalid: sql<number>`COALESCE(SUM(${dailyStatsTable.tokensInvalid}), 0)`,
      })
      .from(dailyStatsTable)
      .where(eq(dailyStatsTable.workerId, worker.id));

    const gen = Number(stats[0]?.tokensGenerated ?? 0);
    const valid = Number(stats[0]?.tokensValid ?? 0);

    res.json({
      discordId: worker.discordId,
      discordUsername: worker.discordUsername,
      status: worker.status,
      expiresAt: worker.expiresAt,
      createdAt: worker.createdAt,
      stats: {
        tokensGenerated: gen,
        tokensValid: valid,
        tokensLocked: Number(stats[0]?.tokensLocked ?? 0),
        tokensInvalid: Number(stats[0]?.tokensInvalid ?? 0),
        unlockRate: gen > 0 ? Math.round((valid / gen) * 100) : 0,
      },
    });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to fetch profile", detail: err?.message });
  }
});

/** GET /api/worker/my-tokens — recent tokens for this worker */
router.get("/worker/my-tokens", requireWorkerKey, async (req: Request, res: Response) => {
  try {
    const worker = (req as any).worker;
    const limit = Math.min(Number(req.query.limit) || 100, 500);

    const tokens = await db
      .select({
        id: tokensTable.id,
        token: tokensTable.token,
        email: tokensTable.email,
        status: tokensTable.status,
        createdAt: tokensTable.createdAt,
        checkedAt: tokensTable.checkedAt,
      })
      .from(tokensTable)
      .where(eq(tokensTable.workerId, worker.id))
      .orderBy(desc(tokensTable.createdAt))
      .limit(limit);

    res.json({ tokens });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to fetch tokens", detail: err?.message });
  }
});

/** GET /api/worker/my-stats — daily breakdown for charts */
router.get("/worker/my-stats", requireWorkerKey, async (req: Request, res: Response) => {
  try {
    const worker = (req as any).worker;

    const days = await db
      .select()
      .from(dailyStatsTable)
      .where(eq(dailyStatsTable.workerId, worker.id))
      .orderBy(desc(dailyStatsTable.date))
      .limit(30);

    res.json({ days });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to fetch stats", detail: err?.message });
  }
});

export default router;
