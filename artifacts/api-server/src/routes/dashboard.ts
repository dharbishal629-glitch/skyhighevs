import { Router, type IRouter, type Request, type Response } from "express";
import { db } from "@workspace/db";
import { workersTable, tokensTable } from "@workspace/db/schema";
import { sql } from "drizzle-orm";
import { requireApiKey } from "../middlewares/auth";
import { requireAdmin } from "../middlewares/admin";
import { logBus } from "../lib/logBus";
import { verifySync } from "otplib";

const router: IRouter = Router();

router.get("/dashboard/stats", requireApiKey, requireAdmin, async (_req: Request, res: Response) => {
  const today = new Date().toISOString().split("T")[0];

  const [workerStats] = await db
    .select({
      total: sql<number>`COUNT(*)`,
      active: sql<number>`COUNT(*) FILTER (WHERE ${workersTable.status} = 'VALID')`,
      locked: sql<number>`COUNT(*) FILTER (WHERE ${workersTable.status} = 'LOCKED')`,
    })
    .from(workersTable);

  const [tokenStats] = await db
    .select({
      total: sql<number>`COUNT(*)`,
      valid: sql<number>`COUNT(*) FILTER (WHERE ${tokensTable.status} = 'VALID')`,
      locked: sql<number>`COUNT(*) FILTER (WHERE ${tokensTable.status} = 'LOCKED')`,
      invalid: sql<number>`COUNT(*) FILTER (WHERE ${tokensTable.status} = 'INVALID')`,
    })
    .from(tokensTable);

  // Count today's tokens directly from tokensTable (reliable even without a worker key)
  const [todayStats] = await db
    .select({
      generated: sql<number>`COUNT(*)`,
      valid: sql<number>`COUNT(*) FILTER (WHERE ${tokensTable.status} = 'VALID')`,
      locked: sql<number>`COUNT(*) FILTER (WHERE ${tokensTable.status} = 'LOCKED')`,
      invalid: sql<number>`COUNT(*) FILTER (WHERE ${tokensTable.status} = 'INVALID')`,
    })
    .from(tokensTable)
    .where(sql`DATE(${tokensTable.createdAt}) = ${today}`);

  const totalTokens = Number(tokenStats?.total || 0);
  const validTokens = Number(tokenStats?.valid || 0);
  const tokensToday = Number(todayStats?.generated || 0);
  const validToday = Number(todayStats?.valid || 0);
  const lockedToday = Number(todayStats?.locked || 0);
  const invalidToday = Number(todayStats?.invalid || 0);

  logBus.info("Dashboard stats fetched");

  res.json({
    totalWorkers: Number(workerStats?.total || 0),
    activeWorkers: Number(workerStats?.active || 0),
    lockedWorkers: Number(workerStats?.locked || 0),
    totalTokens,
    validTokens,
    lockedTokens: Number(tokenStats?.locked || 0),
    invalidTokens: Number(tokenStats?.invalid || 0),
    tokensToday,
    validToday,
    lockedToday,
    invalidToday,
    unlockRateToday: tokensToday > 0 ? Math.round((validToday / tokensToday) * 100) : 0,
    unlockRateAllTime: totalTokens > 0 ? Math.round((validTokens / totalTokens) * 100) : 0,
  });
});

router.get("/logs/stream", (req: Request, res: Response) => {
  const apiKey = req.query["x-api-key"] as string;
  const totpCode = req.query["x-totp-code"] as string;

  if (!apiKey || apiKey !== process.env.WORKER_API_KEY) {
    res.status(401).json({ error: "Invalid API key" });
    return;
  }

  const totpSecret = process.env.TOTP_SECRET || "";
  if (!totpSecret || !totpCode) {
    res.status(401).json({ error: "Invalid or expired 2FA code" });
    return;
  }

  let totpValid = false;
  try {
    const result = verifySync({ token: totpCode, secret: totpSecret });
    totpValid = result.valid === true;
  } catch (_err) {
    totpValid = false;
  }
  if (!totpValid) {
    res.status(401).json({ error: "Invalid or expired 2FA code" });
    return;
  }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.flushHeaders();

  // Send buffered recent logs
  const recent = logBus.getBuffer().slice(-50);
  for (const entry of recent) {
    res.write(`data: ${JSON.stringify(entry)}\n\n`);
  }

  const onLog = (entry: object) => {
    res.write(`data: ${JSON.stringify(entry)}\n\n`);
  };

  logBus.on("log", onLog);

  // Heartbeat every 15s
  const heartbeat = setInterval(() => {
    res.write(`: heartbeat\n\n`);
  }, 15000);

  req.on("close", () => {
    clearInterval(heartbeat);
    logBus.off("log", onLog);
  });
});

export default router;
