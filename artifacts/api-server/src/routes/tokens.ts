import { Router, type IRouter, type Request, type Response } from "express";
import { db } from "@workspace/db";
import { tokensTable, workersTable, dailyStatsTable } from "@workspace/db/schema";
import { eq, and, or, inArray, sql, isNull, isNotNull } from "drizzle-orm";
import { requireApiKey } from "../middlewares/auth";
import { requireAdmin } from "../middlewares/admin";
import { logBus } from "../lib/logBus";

const router: IRouter = Router();

function getTodayDate(): string {
  return new Date().toISOString().split("T")[0];
}

router.post("/tokens/save", requireApiKey, async (req: Request, res: Response) => {
  const { token, email, accountPass, workerKey, status } = req.body;

  if (!token) {
    logBus.warn(`[!] /tokens/save rejected: missing token field (workerKey=${workerKey || "<none>"})`);
    res.status(400).json({ error: "token is required" });
    return;
  }

  const tokenStatus: string = (status || "VALID").toUpperCase();

  const [worker] = workerKey
    ? await db.select().from(workersTable).where(eq(workersTable.workerKey, workerKey)).limit(1)
    : [null];

  if (workerKey && !worker) {
    logBus.warn(`[!] /tokens/save: workerKey "${workerKey}" did not match any worker — token will be saved ORPHANED (worker_id=NULL). This token will be invisible to /my-value until rescued.`);
  }

  const existing = await db.select().from(tokensTable).where(eq(tokensTable.token, token)).limit(1);

  if (existing.length > 0) {
    await db
      .update(tokensTable)
      .set({ status: tokenStatus, checkedAt: new Date() })
      .where(eq(tokensTable.token, token));
    if (worker) {
      logBus.warn(`[~] Duplicate token re-submitted by ${worker.discordUsername} — status refreshed (NOT counted in stats)`);
    }
    res.json({
      success:   true,
      duplicate: true,
      updated:   true,
      created:   false,
      message:   "Token already exists in database. Status was refreshed but this submission is NOT counted as a new token.",
    });
    return;
  }

  // Insert and get the actual DB row back — proves it was written
  let insertedId: number;
  try {
    const [inserted] = await db.insert(tokensTable).values({
      token,
      email: email || null,
      accountPass: accountPass || null,
      status: tokenStatus,
      workerId: worker ? worker.id : null,
      workerKey: workerKey || null,
    }).returning({ id: tokensTable.id });
    insertedId = inserted.id;
  } catch (err: any) {
    const msg = err?.message || String(err);
    logBus.error(`[X] /tokens/save INSERT FAILED for workerKey="${workerKey || "<none>"}" status=${tokenStatus} — DB error: ${msg}`);
    res.status(500).json({ success: false, error: "Database insert failed", detail: msg });
    return;
  }

  let todayTotal = 1;

  if (worker) {
    const today = getTodayDate();
    const validInc = tokenStatus === "VALID" ? 1 : 0;
    const lockedInc = tokenStatus === "LOCKED" ? 1 : 0;
    const invalidInc = tokenStatus === "INVALID" ? 1 : 0;

    const existingStats = await db
      .select()
      .from(dailyStatsTable)
      .where(and(eq(dailyStatsTable.workerId, worker.id), eq(dailyStatsTable.date, today)))
      .limit(1);

    if (existingStats.length > 0) {
      const [updated] = await db
        .update(dailyStatsTable)
        .set({
          tokensGenerated: sql`${dailyStatsTable.tokensGenerated} + 1`,
          tokensValid: sql`${dailyStatsTable.tokensValid} + ${validInc}`,
          tokensLocked: sql`${dailyStatsTable.tokensLocked} + ${lockedInc}`,
          tokensInvalid: sql`${dailyStatsTable.tokensInvalid} + ${invalidInc}`,
        })
        .where(and(eq(dailyStatsTable.workerId, worker.id), eq(dailyStatsTable.date, today)))
        .returning({ tokensGenerated: dailyStatsTable.tokensGenerated });
      todayTotal = Number(updated?.tokensGenerated ?? 1);
    } else {
      await db.insert(dailyStatsTable).values({
        workerId: worker.id,
        date: today,
        tokensGenerated: 1,
        tokensValid: validInc,
        tokensLocked: lockedInc,
        tokensInvalid: invalidInc,
      });
      todayTotal = 1;
    }

    const statusIcon = tokenStatus === "VALID" ? "+" : tokenStatus === "LOCKED" ? "!" : "-";
    logBus.info(`[${statusIcon}] Token #${insertedId} saved by ${worker.discordUsername} — status: ${tokenStatus} | today: ${todayTotal}`);
  }

  // savedBy is ONLY present when the DB row was confirmed created.
  // main.py must check for this field — if absent, the save failed.
  res.json({
    success:    true,
    created:    true,
    tokenId:    insertedId,           // actual DB row id — proof of insert
    savedBy:    worker?.discordUsername ?? null,   // username shown in tool logs
    todayTotal: todayTotal,           // running count for today (this worker)
  });
});

router.get("/tokens/fetch", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  const { workerKey, discordId, status } = req.query as Record<string, string>;

  // ── Resolve discordId → worker first, so we can OR-match orphaned tokens
  //    (tokens saved with workerId=NULL but workerKey set still belong to this user).
  let resolvedWorkerKey: string | null = null;
  let resolvedWorkerId: number | null = null;
  if (discordId) {
    const [w] = await db
      .select({ id: workersTable.id, workerKey: workersTable.workerKey })
      .from(workersTable)
      .where(eq(workersTable.discordId, discordId))
      .limit(1);
    if (w) {
      resolvedWorkerId  = w.id;
      resolvedWorkerKey = w.workerKey;
    }
  }

  let query = db.select({
    id: tokensTable.id,
    token: tokensTable.token,
    email: tokensTable.email,
    accountPass: tokensTable.accountPass,
    status: tokensTable.status,
    workerId: tokensTable.workerId,
    workerKey: tokensTable.workerKey,
    createdAt: tokensTable.createdAt,
    checkedAt: tokensTable.checkedAt,
    discordUsername: workersTable.discordUsername,
  })
    .from(tokensTable)
    .leftJoin(workersTable, eq(tokensTable.workerId, workersTable.id));

  const conditions = [];

  if (workerKey) conditions.push(eq(tokensTable.workerKey, workerKey));
  if (discordId) {
    if (resolvedWorkerId !== null && resolvedWorkerKey) {
      conditions.push(or(
        eq(tokensTable.workerId,  resolvedWorkerId),
        eq(tokensTable.workerKey, resolvedWorkerKey),
      )!);
    } else if (resolvedWorkerId !== null) {
      conditions.push(eq(tokensTable.workerId, resolvedWorkerId));
    } else {
      // discordId provided but no worker found — fall back to the join filter so we get []
      conditions.push(eq(workersTable.discordId, discordId));
    }
  }
  if (status) conditions.push(eq(tokensTable.status, status.toUpperCase()));

  const results = conditions.length > 0
    ? await query.where(and(...conditions))
    : await query;

  // Tag orphans so the bot can show a warning
  const orphanCount = results.filter(r => r.workerId === null).length;

  res.json({ tokens: results, count: results.length, orphanCount });
});

// ── Diagnostic: per-worker token breakdown (orphans, status, total) ────────────
router.get("/tokens/diag/:discordId", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  const discordId = req.params.discordId as string;

  const [w] = await db
    .select({ id: workersTable.id, workerKey: workersTable.workerKey, discordUsername: workersTable.discordUsername })
    .from(workersTable)
    .where(eq(workersTable.discordId, discordId))
    .limit(1);

  if (!w) {
    res.status(404).json({ error: "Worker not found for that discordId" });
    return;
  }

  // Tokens linked properly via worker_id
  const linked = await db.select().from(tokensTable).where(eq(tokensTable.workerId, w.id));

  // Tokens orphaned but matching their workerKey (NOT linked via worker_id)
  const orphans = await db
    .select()
    .from(tokensTable)
    .where(and(eq(tokensTable.workerKey, w.workerKey), isNull(tokensTable.workerId)));

  // Today's daily stats counter (what the dashboard graphs show)
  const today = getTodayDate();
  const [todayStat] = await db
    .select()
    .from(dailyStatsTable)
    .where(and(eq(dailyStatsTable.workerId, w.id), eq(dailyStatsTable.date, today)))
    .limit(1);

  const breakdown = (rows: typeof linked) => ({
    total:   rows.length,
    valid:   rows.filter(r => r.status === "VALID").length,
    locked:  rows.filter(r => r.status === "LOCKED").length,
    invalid: rows.filter(r => r.status === "INVALID").length,
  });

  res.json({
    worker: { id: w.id, discordId, discordUsername: w.discordUsername, workerKey: w.workerKey },
    linked:  breakdown(linked),
    orphaned: breakdown(orphans),
    combined: breakdown([...linked, ...orphans]),
    todayDailyStats: todayStat || null,
  });
});

// ── Rescue: re-link orphaned tokens (workerKey matches but worker_id is NULL) ──
router.post("/tokens/rescue/:discordId", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  const discordId = req.params.discordId as string;

  const [w] = await db
    .select({ id: workersTable.id, workerKey: workersTable.workerKey, discordUsername: workersTable.discordUsername })
    .from(workersTable)
    .where(eq(workersTable.discordId, discordId))
    .limit(1);

  if (!w) {
    res.status(404).json({ error: "Worker not found for that discordId" });
    return;
  }

  const updated = await db
    .update(tokensTable)
    .set({ workerId: w.id })
    .where(and(eq(tokensTable.workerKey, w.workerKey), isNull(tokensTable.workerId)))
    .returning({ id: tokensTable.id });

  if (updated.length > 0) {
    logBus.info(`[+] Rescued ${updated.length} orphaned token(s) for ${w.discordUsername} — now linked to worker_id=${w.id}`);
  }

  res.json({ success: true, rescued: updated.length });
});

router.delete("/tokens/user/:discordId", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  const discordId = req.params.discordId as string;

  const workers = await db
    .select({ id: workersTable.id })
    .from(workersTable)
    .where(eq(workersTable.discordId, discordId))
    .limit(1);

  if (workers.length === 0) {
    res.status(404).json({ error: "Worker not found" });
    return;
  }

  const workerId = workers[0].id;

  const deleted = await db
    .delete(tokensTable)
    .where(eq(tokensTable.workerId, workerId))
    .returning({ id: tokensTable.id });

  res.json({ success: true, deleted: deleted.length });
});

router.post("/tokens/check", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  const { tokens } = req.body as { tokens: string[] };

  if (!tokens || !Array.isArray(tokens) || tokens.length === 0) {
    res.status(400).json({ error: "tokens array is required" });
    return;
  }

  const results = await db
    .select()
    .from(tokensTable)
    .where(inArray(tokensTable.token, tokens));

  const response = tokens.map((t) => {
    const found_token = results.find((r) => r.token === t);
    return {
      token: t,
      status: found_token ? found_token.status : "NOT_IN_DB",
      email: found_token?.email || null,
      checkedAt: found_token?.checkedAt || null,
    };
  });

  res.json({ results: response });
});

export default router;
