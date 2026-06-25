import { Router, type IRouter, type Request, type Response } from "express";
import { pool } from "@workspace/db";
import { requireApiKey } from "../middlewares/auth";
import { getEnvSetting } from "./envSettings";

const router: IRouter = Router();

async function ensureTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS account_logs (
      id           SERIAL PRIMARY KEY,
      email        TEXT NOT NULL,
      account_pass TEXT,
      token        TEXT NOT NULL,
      email_pass   TEXT,
      is_hotmail   BOOLEAN NOT NULL DEFAULT false,
      verified     BOOLEAN NOT NULL DEFAULT false,
      status       TEXT NOT NULL DEFAULT 'VALID',
      worker_id    TEXT,
      created_at   TIMESTAMP NOT NULL DEFAULT NOW()
    )
  `);
}

function statusEmoji(s: string) {
  if (s === "VALID")   return "✅ VALID";
  if (s === "LOCKED")  return "🔒 LOCKED";
  return "❌ " + (s || "UNKNOWN");
}

function embedColor(s: string) {
  if (s === "VALID")  return 0x10B981; // green
  if (s === "LOCKED") return 0xF59E0B; // yellow
  return 0xEF4444;                      // red
}

async function sendWebhook(webhookUrl: string, payload: object) {
  const r = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`Webhook returned ${r.status}: ${text.slice(0, 200)}`);
  }
}

router.post("/logs/account-created", requireApiKey, async (req: Request, res: Response) => {
  try {
    await ensureTable();
    const {
      email, accountPass, token, emailPass,
      isHotmail, verified, status = "VALID", workerId,
    } = req.body;

    if (!email || !token) {
      res.status(400).json({ error: "email and token are required" });
      return;
    }

    await pool.query(
      `INSERT INTO account_logs
         (email, account_pass, token, email_pass, is_hotmail, verified, status, worker_id)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
      [email, accountPass ?? null, token, emailPass ?? null,
       isHotmail ?? false, verified ?? false, status, workerId ?? null]
    );

    const webhookUrl = await getEnvSetting("LOG_WEBHOOK_URL");
    if (webhookUrl) {
      const ep        = emailPass  ? `\`${emailPass}\`` : "—";
      const hmVal     = isHotmail  ? "✅ Yes" : "❌ No";
      const verVal    = verified   ? "✅ Yes" : "❌ No";
      const copyStr   = [email, accountPass, token, ...(emailPass ? [emailPass] : [])].join(":");

      const embed = {
        title: "Account Created",
        color: embedColor(status),
        fields: [
          { name: "Email",    value: `\`${email}\``,       inline: true  },
          { name: "Password", value: `\`${accountPass ?? "—"}\``, inline: true },
          { name: "\u200b",   value: "\u200b",              inline: true  },
          { name: "Status",   value: statusEmoji(status),  inline: true  },
          { name: "Email Verified",           value: verVal, inline: true },
          { name: "\u200b",   value: "\u200b",              inline: true  },
          { name: "Hotmail / Outlook",          value: hmVal, inline: true },
          { name: "Hotmail / Outlook Password", value: ep,    inline: true },
          { name: "\u200b",   value: "\u200b",              inline: true  },
          { name: "📋 Copy", value: `\`\`\`\n${copyStr}\n\`\`\``, inline: false },
        ],
        footer: { text: "SKYHIGH GEN LOGS" },
        timestamp: new Date().toISOString(),
      };

      try {
        await sendWebhook(webhookUrl, { embeds: [embed] });
      } catch (whErr: any) {
        console.error("[AccLog] Webhook error:", whErr.message);
      }
    }

    res.json({ ok: true });
  } catch (err: any) {
    console.error("[AccLog] Error:", err);
    res.status(500).json({ error: err?.message || "Failed to save log" });
  }
});

export default router;
