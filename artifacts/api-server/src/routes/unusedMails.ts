import { Router, type IRouter, type Request, type Response } from "express";
import { db } from "@workspace/db";
import { unusedMailsTable } from "@workspace/db/schema";
import { sql } from "drizzle-orm";
import { requireApiKeyOrWorkerKey } from "../middlewares/auth";
import { logBus } from "../lib/logBus";

const router: IRouter = Router();

/**
 * POST /api/unused-mails
 * Called by main.py when a Zeus-X email fails registration/token capture.
 * Stores it so ANY worker can reuse it on the next cycle instead of buying new.
 */
router.post("/unused-mails", requireApiKeyOrWorkerKey, async (req: Request, res: Response) => {
  try {
    const { email, password, refreshToken, accessToken, clientId, uuid, mailType } = req.body as {
      email: string;
      password?: string;
      refreshToken?: string;
      accessToken?: string;
      clientId?: string;
      uuid?: string;
      mailType?: string;
    };

    if (!email) {
      res.status(400).json({ error: "email is required" });
      return;
    }

    await db.insert(unusedMailsTable).values({
      email,
      password:     password     || null,
      refreshToken: refreshToken || null,
      accessToken:  accessToken  || null,
      clientId:     clientId     || null,
      uuid:         uuid         || null,
      mailType:     mailType     || null,
    });

    logBus.info(`[UnusedMail] Stored ${email} (${mailType || "?"}) — pool grows`);
    res.json({ success: true });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to store unused mail", detail: err?.message });
  }
});

/**
 * GET /api/unused-mails/pop
 * Atomically claims + deletes the oldest unused email and returns it.
 * Returns { email: null } when the pool is empty.
 */
router.get("/unused-mails/pop", requireApiKeyOrWorkerKey, async (_req: Request, res: Response) => {
  try {
    const rows = await db
      .delete(unusedMailsTable)
      .where(
        sql`id = (SELECT id FROM unused_mails ORDER BY created_at ASC LIMIT 1)`
      )
      .returning();

    if (!rows || rows.length === 0) {
      res.json({ email: null });
      return;
    }

    const mail = rows[0];
    logBus.info(`[UnusedMail] Popped ${mail.email} — reusing this cycle`);
    res.json({
      success:      true,
      email:        mail.email,
      password:     mail.password,
      refreshToken: mail.refreshToken,
      accessToken:  mail.accessToken,
      clientId:     mail.clientId,
      uuid:         mail.uuid,
      mailType:     mail.mailType,
    });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to pop unused mail", detail: err?.message });
  }
});

/**
 * GET /api/unused-mails/count
 * How many emails are waiting in the pool.
 */
router.get("/unused-mails/count", requireApiKeyOrWorkerKey, async (_req: Request, res: Response) => {
  try {
    const [{ count }] = await db
      .select({ count: sql<number>`COUNT(*)` })
      .from(unusedMailsTable);
    res.json({ count: Number(count) });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to count unused mails", detail: err?.message });
  }
});

/**
 * DELETE /api/unused-mails/clear
 * Wipe the entire pool (admin action).
 */
router.delete("/unused-mails/clear", requireApiKeyOrWorkerKey, async (_req: Request, res: Response) => {
  try {
    const deleted = await db.delete(unusedMailsTable).returning({ id: unusedMailsTable.id });
    logBus.warn(`[UnusedMail] Pool cleared — ${deleted.length} email(s) removed`);
    res.json({ success: true, cleared: deleted.length });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to clear unused mails", detail: err?.message });
  }
});

export default router;
