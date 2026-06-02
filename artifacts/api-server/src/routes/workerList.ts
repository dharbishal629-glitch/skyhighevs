import { Router, type IRouter, type Request, type Response } from "express";
import { db } from "@workspace/db";
import { workersTable, dailyStatsTable } from "@workspace/db/schema";
import { eq, sql } from "drizzle-orm";
import { requireApiKey } from "../middlewares/auth";
import { requireAdmin } from "../middlewares/admin";
import { logBus } from "../lib/logBus";

const router: IRouter = Router();

router.get("/workers/list", requireApiKey, requireAdmin, async (_req: Request, res: Response) => {
  const workers = await db
    .select({
      id: workersTable.id,
      discordId: workersTable.discordId,
      discordUsername: workersTable.discordUsername,
      workerKey: workersTable.workerKey,
      status: workersTable.status,
      expiresAt: workersTable.expiresAt,
      createdAt: workersTable.createdAt,
      tokensGenerated: sql<number>`COALESCE(SUM(${dailyStatsTable.tokensGenerated}), 0)`,
      tokensValid: sql<number>`COALESCE(SUM(${dailyStatsTable.tokensValid}), 0)`,
    })
    .from(workersTable)
    .leftJoin(dailyStatsTable, eq(workersTable.id, dailyStatsTable.workerId))
    .groupBy(
      workersTable.id,
      workersTable.discordId,
      workersTable.discordUsername,
      workersTable.workerKey,
      workersTable.status,
      workersTable.expiresAt,
      workersTable.createdAt,
    );

  const result = workers.map((w) => {
    const gen = Number(w.tokensGenerated);
    const valid = Number(w.tokensValid);
    return {
      ...w,
      tokensGenerated: gen,
      tokensValid: valid,
      expiresAt: w.expiresAt ? w.expiresAt.toISOString() : null,
      createdAt: w.createdAt.toISOString(),
      unlockRate: gen > 0 ? Math.round((valid / gen) * 100) : 0,
    };
  });

  logBus.info(`Workers list fetched — ${result.length} workers`);

  res.json({ workers: result });
});

export default router;
