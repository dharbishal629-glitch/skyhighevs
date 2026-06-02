import { Router, type IRouter, type Request, type Response } from "express";
import { requireApiKey } from "../middlewares/auth";
import {
  getAdminSetupStatus,
  setAdminAccessCode,
  getStoredHash,
  hashCode,
} from "../middlewares/admin";

const router: IRouter = Router();

/** GET /api/admin/status — is an access code already configured? */
router.get("/admin/status", async (_req: Request, res: Response) => {
  try {
    const configured = await getAdminSetupStatus();
    res.json({ configured });
  } catch (err: any) {
    res.status(500).json({ error: err?.message || "Status check failed" });
  }
});

/**
 * POST /api/admin/setup
 * Set the access code for the first time.
 * Only works when NO code is configured yet (setup mode).
 * Requires: { newCode: string }  (min 4 chars)
 */
router.post("/admin/setup", requireApiKey, async (req: Request, res: Response) => {
  try {
    const configured = await getAdminSetupStatus();
    if (configured) {
      res.status(403).json({ error: "Access code already set. Use /api/admin/change-code to update it." });
      return;
    }

    const { newCode } = req.body ?? {};
    if (!newCode || typeof newCode !== "string" || newCode.trim().length < 4) {
      res.status(400).json({ error: "newCode must be at least 4 characters" });
      return;
    }

    await setAdminAccessCode(newCode.trim());
    res.json({ success: true, message: "Access code saved. Use it to log in." });
  } catch (err: any) {
    res.status(500).json({ error: err?.message || "Setup failed" });
  }
});

/**
 * POST /api/admin/change-code
 * Change the access code. Requires the current code to be supplied.
 * Body: { currentCode: string, newCode: string }
 */
router.post("/admin/change-code", requireApiKey, async (req: Request, res: Response) => {
  try {
    const { currentCode, newCode } = req.body ?? {};

    if (!newCode || typeof newCode !== "string" || newCode.trim().length < 4) {
      res.status(400).json({ error: "newCode must be at least 4 characters" });
      return;
    }

    const storedHash = await getStoredHash();

    // If no code set yet, allow direct setup
    if (!storedHash) {
      await setAdminAccessCode(newCode.trim());
      res.json({ success: true, message: "Access code saved." });
      return;
    }

    // Verify current code
    if (!currentCode || hashCode(currentCode.trim()) !== storedHash) {
      res.status(403).json({ error: "Current access code is incorrect" });
      return;
    }

    await setAdminAccessCode(newCode.trim());
    res.json({ success: true, message: "Access code updated." });
  } catch (err: any) {
    res.status(500).json({ error: err?.message || "Change failed" });
  }
});

export default router;
