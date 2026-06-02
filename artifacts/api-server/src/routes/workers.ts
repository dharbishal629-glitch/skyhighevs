import { Router, type IRouter, type Request, type Response } from "express";
import { db } from "@workspace/db";
import { workersTable, dailyStatsTable } from "@workspace/db/schema";
import { eq, and, desc, sql } from "drizzle-orm";
import { requireApiKey } from "../middlewares/auth";
import { requireAdmin } from "../middlewares/admin";
import { logBus } from "../lib/logBus";
import crypto from "crypto";

const router: IRouter = Router();

function generateWorkerKey(): string {
  return "WK-" + crypto.randomBytes(16).toString("hex").toUpperCase();
}

function getTodayDate(): string {
  return new Date().toISOString().split("T")[0];
}

router.post("/workers/create-key", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  const { discordId, discordUsername, durationDays } = req.body;

  if (!discordId || !discordUsername) {
    res.status(400).json({ error: "discordId and discordUsername are required" });
    return;
  }

  const existing = await db.select().from(workersTable).where(eq(workersTable.discordId, discordId)).limit(1);

  const workerKey = generateWorkerKey();
  const expiresAt = durationDays
    ? new Date(Date.now() + Number(durationDays) * 24 * 60 * 60 * 1000)
    : null;

  if (existing.length > 0) {
    const [updated] = await db
      .update(workersTable)
      .set({ workerKey, status: "VALID", expiresAt, updatedAt: new Date() })
      .where(eq(workersTable.discordId, discordId))
      .returning();
    logBus.success(`Worker key renewed for ${discordUsername} (${discordId})`);
    res.json({ success: true, worker: updated });
    return;
  }

  const [worker] = await db
    .insert(workersTable)
    .values({ discordId, discordUsername, workerKey, status: "VALID", expiresAt })
    .returning();

  logBus.success(`New worker key created for ${discordUsername} (${discordId}) — expires: ${expiresAt?.toISOString() ?? "never"}`);
  res.json({ success: true, worker });
});

router.delete("/workers/delete-key", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  const { discordId } = req.body;

  if (!discordId) {
    res.status(400).json({ error: "discordId is required" });
    return;
  }

  const result = await db
    .update(workersTable)
    .set({ status: "LOCKED", updatedAt: new Date() })
    .where(eq(workersTable.discordId, discordId))
    .returning();

  if (result.length === 0) {
    res.status(404).json({ error: "Worker not found" });
    return;
  }

  res.json({ success: true, message: "Worker key locked" });
});

router.post("/workers/validate-key", requireApiKey, async (req: Request, res: Response) => {
  const { workerKey } = req.body;

  if (!workerKey) {
    res.status(400).json({ error: "workerKey is required" });
    return;
  }

  const [worker] = await db
    .select()
    .from(workersTable)
    .where(eq(workersTable.workerKey, workerKey))
    .limit(1);

  if (!worker) {
    logBus.warn(`Failed key validation attempt — key not found`);
    res.json({ valid: false, status: "INVALID", message: "Worker key not found" });
    return;
  }

  if (worker.status === "LOCKED") {
    logBus.warn(`Blocked login attempt — key LOCKED for ${worker.discordUsername}`);
    res.json({ valid: false, status: "LOCKED", message: "Worker key is locked" });
    return;
  }

  if (worker.expiresAt && new Date(worker.expiresAt) < new Date()) {
    await db.update(workersTable).set({ status: "LOCKED" }).where(eq(workersTable.id, worker.id));
    logBus.warn(`Key expired and locked for ${worker.discordUsername}`);
    res.json({ valid: false, status: "EXPIRED", message: "Worker key has expired" });
    return;
  }

  logBus.info(`Worker authenticated: ${worker.discordUsername} (${worker.discordId})`);
  res.json({ valid: true, status: "VALID", worker: { id: worker.id, discordId: worker.discordId, discordUsername: worker.discordUsername } });
});

router.get("/workers/leaderboard", requireApiKey, async (req: Request, res: Response) => {
  const period = (req.query.period as string) || "alltime";
  const today = getTodayDate();

  const joinCondition = period === "today"
    ? and(eq(workersTable.id, dailyStatsTable.workerId), eq(dailyStatsTable.date, today))
    : eq(workersTable.id, dailyStatsTable.workerId);

  const stats = await db
    .select({
      discordId: workersTable.discordId,
      discordUsername: workersTable.discordUsername,
      totalGenerated: sql<number>`COALESCE(SUM(${dailyStatsTable.tokensGenerated}), 0)`,
      totalValid: sql<number>`COALESCE(SUM(${dailyStatsTable.tokensValid}), 0)`,
      totalLocked: sql<number>`COALESCE(SUM(${dailyStatsTable.tokensLocked}), 0)`,
      totalInvalid: sql<number>`COALESCE(SUM(${dailyStatsTable.tokensInvalid}), 0)`,
    })
    .from(workersTable)
    .leftJoin(dailyStatsTable, joinCondition)
    .groupBy(workersTable.id, workersTable.discordId, workersTable.discordUsername)
    .orderBy(desc(sql`COALESCE(SUM(${dailyStatsTable.tokensGenerated}), 0)`));

  const leaderboard = stats.map((s, i) => {
    const gen = Number(s.totalGenerated) || 0;
    const valid = Number(s.totalValid) || 0;
    return {
      rank: i + 1,
      discordUsername: s.discordUsername,
      discordId: s.discordId,
      totalGenerated: gen,
      totalValid: valid,
      totalLocked: Number(s.totalLocked) || 0,
      totalInvalid: Number(s.totalInvalid) || 0,
      todayGenerated: gen,
      todayValid: valid,
      unlockRate: gen > 0 ? Math.round((valid / gen) * 100) : 0,
    };
  });

  res.json({ leaderboard });
});

router.get("/workers/profile/:discordId", requireApiKey, async (req: Request, res: Response) => {
  const discordId = req.params.discordId as string;
  const today = getTodayDate();

  const [worker] = await db
    .select()
    .from(workersTable)
    .where(eq(workersTable.discordId, discordId))
    .limit(1);

  if (!worker) {
    res.status(404).json({ error: "Worker not found" });
    return;
  }

  const todayStats = await db
    .select()
    .from(dailyStatsTable)
    .where(and(eq(dailyStatsTable.workerId, worker.id), eq(dailyStatsTable.date, today)))
    .limit(1);

  const allTimeStats = await db
    .select({
      totalGenerated: sql<number>`SUM(${dailyStatsTable.tokensGenerated})`,
      totalValid: sql<number>`SUM(${dailyStatsTable.tokensValid})`,
      totalLocked: sql<number>`SUM(${dailyStatsTable.tokensLocked})`,
      totalInvalid: sql<number>`SUM(${dailyStatsTable.tokensInvalid})`,
    })
    .from(dailyStatsTable)
    .where(eq(dailyStatsTable.workerId, worker.id));

  const daily = todayStats[0] || { tokensGenerated: 0, tokensValid: 0, tokensLocked: 0, tokensInvalid: 0 };
  const allTime = allTimeStats[0] || { totalGenerated: 0, totalValid: 0, totalLocked: 0, totalInvalid: 0 };

  res.json({
    worker: {
      discordId: worker.discordId,
      discordUsername: worker.discordUsername,
      status: worker.status,
      expiresAt: worker.expiresAt,
      memberSince: worker.createdAt,
    },
    dailyStats: {
      generated: daily.tokensGenerated,
      valid: daily.tokensValid,
      locked: daily.tokensLocked,
      invalid: daily.tokensInvalid,
      unlockRate: daily.tokensGenerated
        ? Math.round((daily.tokensValid / daily.tokensGenerated) * 100)
        : 0,
    },
    allTimeStats: {
      generated: Number(allTime.totalGenerated) || 0,
      valid: Number(allTime.totalValid) || 0,
      locked: Number(allTime.totalLocked) || 0,
      invalid: Number(allTime.totalInvalid) || 0,
    },
  });
});

export default router;
