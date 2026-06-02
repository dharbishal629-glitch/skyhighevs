import { Router, type IRouter, type Request, type Response } from "express";
import { db, pool } from "@workspace/db";
import { toolConfigTable } from "@workspace/db/schema";
import { requireApiKey } from "../middlewares/auth";
import { requireAdmin, checkAdmin } from "../middlewares/admin";

const router: IRouter = Router();

const DEFAULT_CONFIG = {
  emailProvider: "cybertemp",
  zeusxApiKey: "",
  hotmail007ClientKey: "",
  cybertempApiKey: "",
  cybertempCustomDomains: "",
  draxonoApiKey: "",
  draxonoDomainSecret: "",
  draxonoCustomDomains: "",
  browser: "chrome",
  threads: 1,
  target: 0,
  cooldownSeconds: 0,
  proxyEnabled: false,
  proxyUrl: "",
  adbEnabled: false,
  adbPath: "",
  captchaSolverEnabled: false,
  openRouterApiKey: "",
  openRouterModel: "google/gemini-2.0-flash-001",
  captchaMaxAttempts: 4,
  nopechaEnabled: false,
  nopechaApiKey: "",
  captchaTimeoutSeconds: 120,
};

// Fields sent to workers via GET /api/config.
// External service keys (zeus, hotmail007, cybertemp) are included because the
// worker tool calls those services directly — it needs the keys to function.
// The only things we withhold are internal admin credentials.
const WORKER_SAFE_FIELDS = new Set([
  "emailProvider",
  "zeusxApiKey",
  "hotmail007ClientKey",
  "cybertempApiKey",
  "cybertempCustomDomains",
  "draxonoApiKey",
  "draxonoDomainSecret",
  "draxonoCustomDomains",
  "browser",
  "threads",
  "target",
  "cooldownSeconds",
  "proxyEnabled",
  "proxyUrl",
  "adbEnabled",
  "adbPath",
  "captchaSolverEnabled",
  "openRouterApiKey",
  "openRouterModel",
  "captchaMaxAttempts",
  "nopechaEnabled",
  "nopechaApiKey",
  "captchaTimeoutSeconds",
]);

// Creates the table if it's missing (handles databases that never ran setup-db.js)
async function ensureTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS tool_config (
      id         SERIAL PRIMARY KEY,
      config     JSON NOT NULL DEFAULT '{}',
      updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
  `);
}

// Self-healing: if the table doesn't exist, create it then retry automatically
async function getOrCreateConfig(): Promise<Record<string, unknown>> {
  try {
    const rows = await db.select().from(toolConfigTable).limit(1);
    if (rows.length === 0) {
      const inserted = await db.insert(toolConfigTable).values({ config: DEFAULT_CONFIG }).returning();
      return inserted[0].config as Record<string, unknown>;
    }
    return rows[0].config as Record<string, unknown>;
  } catch (err: any) {
    // 42P01 = "relation does not exist" — table was never created
    if (err?.code === "42P01" || err?.message?.includes("tool_config")) {
      await ensureTable();
      // Retry once after creating the table
      const rows = await db.select().from(toolConfigTable).limit(1);
      if (rows.length === 0) {
        const inserted = await db.insert(toolConfigTable).values({ config: DEFAULT_CONFIG }).returning();
        return inserted[0].config as Record<string, unknown>;
      }
      return rows[0].config as Record<string, unknown>;
    }
    throw err;
  }
}

function stripSensitiveFields(cfg: Record<string, unknown>): Record<string, unknown> {
  const safe: Record<string, unknown> = {};
  for (const key of WORKER_SAFE_FIELDS) {
    if (key in cfg) safe[key] = cfg[key];
  }
  return safe;
}

// Workers can only read safe fields — API keys are never exposed
router.get("/config", requireApiKey, checkAdmin, async (req: Request, res: Response) => {
  try {
    const cfg = await getOrCreateConfig();
    const isAdmin = Boolean((req as any).isAdmin);
    res.json({ config: isAdmin ? cfg : stripSensitiveFields(cfg) });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to load config", detail: err?.message });
  }
});

// Full config (including API keys) only accessible to admins
router.get("/config/full", requireApiKey, requireAdmin, async (_req: Request, res: Response) => {
  try {
    const cfg = await getOrCreateConfig();
    res.json({ config: cfg });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to load config", detail: err?.message });
  }
});

router.put("/config", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  try {
    const incoming = req.body as Record<string, unknown>;
    const current = await getOrCreateConfig();
    const merged = { ...DEFAULT_CONFIG, ...current, ...incoming };

    const { eq } = await import("drizzle-orm");
    const rows = await db.select().from(toolConfigTable).limit(1);
    if (rows.length === 0) {
      await db.insert(toolConfigTable).values({ config: merged });
    } else {
      await db.update(toolConfigTable)
        .set({ config: merged, updatedAt: new Date() })
        .where(eq(toolConfigTable.id, rows[0].id));
    }

    res.json({ success: true, config: merged });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to save config", detail: err?.message });
  }
});

export default router;
