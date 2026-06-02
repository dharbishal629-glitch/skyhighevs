import { Router, type IRouter, type Request, type Response } from "express";
import multer from "multer";
import { pool } from "@workspace/db";
import { requireApiKey, requireWorkerKey } from "../middlewares/auth";
import { requireAdmin } from "../middlewares/admin";
import { logger } from "../lib/logger";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";

const execFileAsync = promisify(execFile);

const router: IRouter = Router();

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 50 * 1024 * 1024 },
});

async function ensureToolFilesTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS tool_files (
      id          SERIAL PRIMARY KEY,
      filename    TEXT NOT NULL,
      mime_type   TEXT NOT NULL DEFAULT 'application/octet-stream',
      file_data   BYTEA NOT NULL,
      file_size   INTEGER NOT NULL,
      uploaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
      uploaded_by TEXT NOT NULL DEFAULT 'admin',
      version     INTEGER NOT NULL DEFAULT 1
    )
  `);
}

router.post("/tool/upload", requireApiKey, requireAdmin, upload.single("file"), async (req: Request, res: Response) => {
  try {
    await ensureToolFilesTable();

    if (!req.file) {
      res.status(400).json({ error: "No file provided. Use multipart/form-data with field name 'file'." });
      return;
    }

    const { originalname, mimetype, buffer, size } = req.file;

    await pool.query(`DELETE FROM tool_files`);

    await pool.query(
      `INSERT INTO tool_files (filename, mime_type, file_data, file_size, uploaded_by)
       VALUES ($1, $2, $3, $4, $5)`,
      [originalname, mimetype, buffer, size, "admin"]
    );

    logger.info({ filename: originalname, size }, "Tool file uploaded by admin");

    res.json({
      success: true,
      filename: originalname,
      size,
      mimeType: mimetype,
      uploadedAt: new Date().toISOString(),
    });
  } catch (err: any) {
    logger.error({ err }, "Tool upload failed");
    res.status(500).json({ error: "Upload failed", detail: err?.message });
  }
});

router.get("/tool/info", requireApiKey, requireAdmin, async (_req: Request, res: Response) => {
  try {
    await ensureToolFilesTable();
    const result = await pool.query(
      `SELECT id, filename, mime_type, file_size, uploaded_at, version FROM tool_files ORDER BY id DESC LIMIT 1`
    );
    if (result.rows.length === 0) {
      res.json({ exists: false });
      return;
    }
    const row = result.rows[0];
    res.json({
      exists: true,
      filename: row.filename,
      mimeType: row.mime_type,
      size: row.file_size,
      uploadedAt: row.uploaded_at,
      version: row.version,
    });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to get tool info", detail: err?.message });
  }
});

router.delete("/tool/delete", requireApiKey, requireAdmin, async (_req: Request, res: Response) => {
  try {
    await ensureToolFilesTable();
    await pool.query(`DELETE FROM tool_files`);
    logger.info("Tool file deleted by admin");
    res.json({ success: true });
  } catch (err: any) {
    res.status(500).json({ error: "Failed to delete tool", detail: err?.message });
  }
});

router.get("/tool/download", requireWorkerKey, async (req: Request, res: Response) => {
  try {
    await ensureToolFilesTable();
    const result = await pool.query(
      `SELECT filename, mime_type, file_data, file_size FROM tool_files ORDER BY id DESC LIMIT 1`
    );
    if (result.rows.length === 0) {
      res.status(404).json({ error: "No tool file uploaded yet. Contact your admin." });
      return;
    }
    const { filename, mime_type, file_data, file_size } = result.rows[0];

    // Log download with worker info and client IP
    const worker = (req as any).worker;
    const clientIp =
      (req.headers["x-forwarded-for"] as string | undefined)?.split(",")[0]?.trim() ||
      req.socket.remoteAddress ||
      "unknown";
    logger.info(
      { filename, size: file_size, worker: worker?.discordUsername, ip: clientIp },
      "Tool downloaded by worker"
    );

    // Record the download event for rate-limit / audit tracking
    try {
      await pool.query(`
        CREATE TABLE IF NOT EXISTS tool_download_log (
          id          SERIAL PRIMARY KEY,
          worker_id   INTEGER,
          worker_key  TEXT,
          client_ip   TEXT,
          filename    TEXT,
          downloaded_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
      `);
      await pool.query(
        `INSERT INTO tool_download_log (worker_id, worker_key, client_ip, filename)
         VALUES ($1, $2, $3, $4)`,
        [worker?.id ?? null, worker?.workerKey ?? null, clientIp, filename]
      );

      // Rate-limit: max 5 downloads per worker per 10 minutes
      const recent = await pool.query(
        `SELECT COUNT(*) AS cnt FROM tool_download_log
         WHERE worker_key = $1
           AND downloaded_at > NOW() - INTERVAL '10 minutes'`,
        [worker?.workerKey ?? ""]
      );
      const cnt = Number((recent.rows[0] as any)?.cnt ?? 0);
      if (cnt > 5) {
        res.status(429).json({ error: "Too many downloads. Please wait before trying again." });
        return;
      }
    } catch (_logErr) {
      // Never block a valid download because of a log failure
    }

    // HMAC-sign the payload using the worker's own key as the secret.
    // The launcher verifies this signature before executing — prevents a
    // man-in-the-middle from substituting a different payload.
    const payloadBuf: Buffer = Buffer.isBuffer(file_data) ? file_data : Buffer.from(file_data);
    const hmacSecret = worker?.workerKey ?? "unsigned";
    const payloadHmac = crypto
      .createHmac("sha256", hmacSecret)
      .update(payloadBuf)
      .digest("hex");

    res.setHeader("Content-Type", mime_type);
    res.setHeader("Content-Disposition", `attachment; filename="${filename}"`);
    res.setHeader("Content-Length", file_size);
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("X-Payload-HMAC", payloadHmac);
    res.send(payloadBuf);
  } catch (err: any) {
    logger.error({ err }, "Tool download failed");
    res.status(500).json({ error: "Download failed", detail: err?.message });
  }
});

router.post("/tool/build-exe", requireApiKey, requireAdmin, upload.single("file"), async (req: Request, res: Response) => {
  if (process.env.VERCEL) {
    res.status(501).json({
      error: "PyInstaller builds are not supported on Vercel.",
      hint: "Build the .exe locally (pyinstaller --onefile your_tool.py) then upload it via 'Upload Tool File' above.",
    });
    return;
  }

  let workDir: string | null = null;
  try {
    if (!req.file) {
      res.status(400).json({ error: "No file provided." });
      return;
    }
    const { originalname, buffer } = req.file;
    if (!originalname.endsWith(".py")) {
      res.status(400).json({ error: "Only .py files are supported." });
      return;
    }

    const baseName = path.basename(originalname, ".py").replace(/[^a-zA-Z0-9_\-]/g, "_");
    workDir = await fs.mkdtemp(path.join(os.tmpdir(), "ctrlpnl-build-"));
    const pyPath = path.join(workDir, originalname);
    await fs.writeFile(pyPath, buffer);

    logger.info({ filename: originalname, workDir }, "Starting PyInstaller build");

    // Ensure pyinstaller is available — install it if missing
    const { execFile: execFileRaw } = await import("node:child_process");
    const { promisify: promisifyLocal } = await import("node:util");
    const execLocal = promisifyLocal(execFileRaw);

    const pyinstallerCheck = await execLocal("sh", ["-c", "command -v pyinstaller || pip install pyinstaller --quiet"])
      .catch(() => null);
    logger.info({ pyinstallerCheck }, "PyInstaller availability check");

    await execFileAsync("pyinstaller", [
      "--onefile",
      "--noconfirm",
      "--clean",
      "--distpath", path.join(workDir, "dist"),
      "--workpath", path.join(workDir, "build"),
      "--specpath", workDir,
      "--name", baseName,
      pyPath,
    ], { timeout: 300_000 });

    const outPath = path.join(workDir, "dist", baseName);
    let outBuf: Buffer;
    try {
      outBuf = await fs.readFile(outPath);
    } catch {
      res.status(500).json({ error: "Build completed but output binary not found. Check that the Python file has no import errors." });
      return;
    }

    logger.info({ filename: originalname, size: outBuf.length }, "PyInstaller build succeeded");

    res.setHeader("Content-Type", "application/octet-stream");
    res.setHeader("Content-Disposition", `attachment; filename="${baseName}"`);
    res.setHeader("Content-Length", outBuf.length);
    res.setHeader("Cache-Control", "no-store");
    res.send(outBuf);
  } catch (err: any) {
    logger.error({ err }, "PyInstaller build failed");
    const detail = err?.stderr || err?.message || "Unknown error";
    res.status(500).json({ error: "Build failed", detail });
  } finally {
    if (workDir) {
      fs.rm(workDir, { recursive: true, force: true }).catch(() => {});
    }
  }
});

export default router;
