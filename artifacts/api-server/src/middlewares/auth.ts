import { type Request, type Response, type NextFunction } from "express";
import { verifySync } from "otplib";
import { db } from "@workspace/db";
import { workersTable } from "@workspace/db/schema";
import { eq } from "drizzle-orm";

function safeTotpVerify(token: string, secret: string): boolean {
  if (!token || !secret) return false;
  try {
    const result = verifySync({ token, secret });
    return result.valid === true;
  } catch (_err) {
    return false;
  }
}

/**
 * Worker-key-only auth: looks up the key in the workers table.
 * Attaches worker record to req for downstream use.
 */
export async function requireWorkerKey(req: Request, res: Response, next: NextFunction): Promise<void> {
  const apiKey = (req.headers["x-api-key"] as string | undefined)?.trim();
  if (!apiKey) {
    res.status(401).json({ error: "Missing x-api-key header" });
    return;
  }

  try {
    const [worker] = await db
      .select()
      .from(workersTable)
      .where(eq(workersTable.workerKey, apiKey))
      .limit(1);

    if (!worker) {
      res.status(401).json({ error: "Invalid worker key" });
      return;
    }

    if (worker.status !== "VALID") {
      res.status(403).json({ error: "Worker key is revoked or inactive" });
      return;
    }

    if (worker.expiresAt && new Date(worker.expiresAt) < new Date()) {
      res.status(403).json({ error: "Worker key has expired" });
      return;
    }

    (req as any).worker = worker;
    next();
  } catch (err) {
    res.status(500).json({ error: "Auth check failed" });
  }
}

/**
 * Admin auth: checks WORKER_API_KEY env var + TOTP.
 */
export function requireApiKey(req: Request, res: Response, next: NextFunction): void {
  const apiKey = req.headers["x-api-key"] as string;
  const totpCode = req.headers["x-totp-code"] as string;

  if (!apiKey) {
    res.status(401).json({ error: "Missing x-api-key header" });
    return;
  }

  if (apiKey !== process.env.WORKER_API_KEY) {
    res.status(401).json({ error: "Invalid API key" });
    return;
  }

  const totpSecret = process.env.TOTP_SECRET || "";

  if (!totpSecret) {
    res.status(500).json({ error: "Server 2FA not configured" });
    return;
  }

  if (!totpCode) {
    res.status(401).json({ error: "Missing x-totp-code header (2FA required)" });
    return;
  }

  if (!safeTotpVerify(totpCode, totpSecret)) {
    res.status(401).json({ error: "Invalid or expired 2FA code" });
    return;
  }

  next();
}
