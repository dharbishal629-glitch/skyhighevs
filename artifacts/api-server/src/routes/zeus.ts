import { Router, type IRouter, type Request, type Response } from "express";
import { requireApiKey } from "../middlewares/auth";
import { requireAdmin } from "../middlewares/admin";

const router: IRouter = Router();

const ZEUS_API_BASE = "https://zeus-x.ru/api";

router.get("/zeus/status", requireApiKey, requireAdmin, async (_req: Request, res: Response) => {
  const apiKey = process.env.ZEUS_API_KEY;
  if (!apiKey) {
    res.json({ configured: false, message: "ZEUS_API_KEY not set on server." });
    return;
  }
  res.json({ configured: true });
});

router.post("/zeus/check", requireApiKey, requireAdmin, async (req: Request, res: Response) => {
  const apiKey = process.env.ZEUS_API_KEY;
  if (!apiKey) {
    res.status(503).json({ error: "ZEUS_API_KEY is not configured on the server. Add it to your Render environment variables." });
    return;
  }

  const { emails } = req.body as { emails: string[] };
  if (!emails || !Array.isArray(emails) || emails.length === 0) {
    res.status(400).json({ error: "emails array is required" });
    return;
  }

  try {
    const results = await Promise.allSettled(
      emails.map(async (email: string) => {
        const response = await fetch(`${ZEUS_API_BASE}/check`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${apiKey}`,
            "X-API-Key": apiKey,
          },
          body: JSON.stringify({ email }),
        });

        if (!response.ok) {
          return { email, status: "error", message: `HTTP ${response.status}` };
        }

        const data = await response.json() as Record<string, unknown>;
        return { email, ...data };
      })
    );

    const processed = results.map((r, i) => {
      if (r.status === "fulfilled") return r.value;
      return { email: emails[i], status: "error", message: String(r.reason) };
    });

    res.json({ results: processed, total: processed.length });
  } catch (err: any) {
    res.status(502).json({ error: "Failed to reach zeus-x.ru", detail: err?.message });
  }
});

export default router;
