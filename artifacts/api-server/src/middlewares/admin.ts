import { type Request, type Response, type NextFunction } from "express";
import crypto from "crypto";
import { pool } from "@workspace/db";

// ─── Access-code helpers ────────────────────────────────────────────────────
// The admin access-code is stored in env_settings (key = "admin_access_code")
// as a SHA-256 hash so the plaintext is never at rest.

function hashCode(raw: string): string {
  return crypto.createHash("sha256").update("ctrlpnl-admin:" + raw).digest("hex");
}

async function getStoredHash(): Promise<string | null> {
  try {
    await pool.query(`
      CREATE TABLE IF NOT EXISTS env_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
      )
    `);
    const r = await pool.query(
      `SELECT value FROM env_settings WHERE key = 'admin_access_code'`,
    );
    return r.rows[0]?.value ?? null;
  } catch {
    return null;
  }
}

// ─── Middleware ──────────────────────────────────────────────────────────────

/**
 * requireAdmin:
 *  - If NO access code is stored yet → setup mode, request passes through.
 *  - If a code IS stored → x-admin-key header must match.
 *  - Falls back to ADMIN_KEY env var for backwards-compat during migration.
 */
export async function requireAdmin(req: Request, res: Response, next: NextFunction): Promise<void> {
  const provided = (req.headers["x-admin-key"] as string | undefined)?.trim() ?? "";

  // 1. Check DB-stored hash first
  const storedHash = await getStoredHash();

  if (storedHash) {
    if (!provided) {
      res.status(403).json({ error: "Access code required" });
      return;
    }
    if (hashCode(provided) !== storedHash) {
      // Legacy env-var fallback for deployments that still have ADMIN_KEY set
      if (process.env.ADMIN_KEY && provided === process.env.ADMIN_KEY) {
        (req as any).isAdmin = true;
        next();
        return;
      }
      res.status(403).json({ error: "Invalid access code" });
      return;
    }
    (req as any).isAdmin = true;
    next();
    return;
  }

  // 2. No DB code set — fall back to env var if present
  if (process.env.ADMIN_KEY) {
    if (!provided || provided !== process.env.ADMIN_KEY) {
      res.status(403).json({ error: "Invalid access code" });
      return;
    }
    (req as any).isAdmin = true;
    next();
    return;
  }

  // 3. Nothing configured at all → setup mode, let through
  (req as any).isAdmin = true;
  (req as any).setupMode = true;
  next();
}

/** checkAdmin — sets req.isAdmin without blocking (for optional admin enrichment) */
export async function checkAdmin(req: Request, _res: Response, next: NextFunction): Promise<void> {
  const provided = (req.headers["x-admin-key"] as string | undefined)?.trim() ?? "";

  const storedHash = await getStoredHash();
  if (storedHash && provided && hashCode(provided) === storedHash) {
    (req as any).isAdmin = true;
  } else if (!storedHash && process.env.ADMIN_KEY && provided === process.env.ADMIN_KEY) {
    (req as any).isAdmin = true;
  } else if (!storedHash && !process.env.ADMIN_KEY) {
    // setup mode — treat as admin
    (req as any).isAdmin = true;
  }
  next();
}

// ─── Access-code management endpoints (exported for use in router) ───────────

export async function getAdminSetupStatus(): Promise<boolean> {
  const h = await getStoredHash();
  return h !== null;
}

export async function setAdminAccessCode(newCode: string): Promise<void> {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS env_settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL DEFAULT '',
      description TEXT NOT NULL DEFAULT '',
      updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
  `);
  await pool.query(
    `INSERT INTO env_settings (key, value, description, updated_at)
     VALUES ('admin_access_code', $1, 'Admin dashboard access code (hashed)', NOW())
     ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()`,
    [hashCode(newCode)],
  );
}

export { hashCode, getStoredHash };
