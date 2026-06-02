import React, { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { GlassCard, GlassButton, SectionHeader, Badge } from "@/components/ui/cyber-components";
import {
  Upload, Trash2, Download, FileCode2, RefreshCw,
  CheckCircle2, XCircle, AlertCircle, Loader2, ShieldCheck, Info, Cpu,
} from "lucide-react";

interface ToolInfo {
  exists: boolean;
  filename?: string;
  mimeType?: string;
  size?: number;
  uploadedAt?: string;
  version?: number;
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export default function ToolFilePage() {
  const { getHeaders, apiBaseUrl } = useAuth();
  const [info, setInfo] = useState<ToolInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [status, setStatus] = useState<{ type: "ok" | "err" | "info"; msg: string } | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const buildRef = useRef<HTMLInputElement>(null);

  const [building, setBuilding] = useState(false);
  const [buildStatus, setBuildStatus] = useState<{ type: "ok" | "err" | "info"; msg: string } | null>(null);

  const base = apiBaseUrl || "";

  async function fetchInfo() {
    setLoading(true);
    try {
      const r = await fetch(`${base}/api/tool/info`, { headers: getHeaders() });
      const data = await r.json();
      setInfo(data);
    } catch {
      setInfo(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchInfo(); }, []);

  async function handleUpload(file: File) {
    if (!file) return;
    setUploading(true);
    setStatus(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch(`${base}/api/tool/upload`, {
        method: "POST",
        headers: getHeaders(),
        body: form,
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "Upload failed");
      setStatus({ type: "ok", msg: `Uploaded: ${data.filename} (${formatBytes(data.size)})` });
      await fetchInfo();
    } catch (err: any) {
      setStatus({ type: "err", msg: err?.message || "Upload failed" });
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Delete the uploaded tool file? Workers won't be able to download it until you upload a new one.")) return;
    setDeleting(true);
    setStatus(null);
    try {
      const r = await fetch(`${base}/api/tool/delete`, { method: "DELETE", headers: getHeaders() });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "Delete failed");
      setStatus({ type: "ok", msg: "Tool file deleted." });
      await fetchInfo();
    } catch (err: any) {
      setStatus({ type: "err", msg: err?.message || "Delete failed" });
    } finally {
      setDeleting(false);
    }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
    if (fileRef.current) fileRef.current.value = "";
  };

  async function handleBuild(file: File) {
    if (!file) return;
    if (!file.name.endsWith(".py")) {
      setBuildStatus({ type: "err", msg: "Only .py files are supported." });
      return;
    }
    setBuilding(true);
    setBuildStatus({ type: "info", msg: "Building… this can take up to 60 seconds." });
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch(`${base}/api/tool/build-exe`, {
        method: "POST",
        headers: getHeaders(),
        body: form,
      });
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        throw new Error(data.error || `HTTP ${r.status}`);
      }
      const blob = await r.blob();
      const filename = r.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] || file.name.replace(".py", "");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      setBuildStatus({ type: "ok", msg: `Built & downloaded: ${filename} (${(blob.size / 1024 / 1024).toFixed(1)} MB)` });
    } catch (err: any) {
      setBuildStatus({ type: "err", msg: err?.message || "Build failed" });
    } finally {
      setBuilding(false);
      if (buildRef.current) buildRef.current.value = "";
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        icon={<ShieldCheck className="w-5 h-5 text-violet-400" />}
        title="Secure Tool Distribution"
        subtitle="Upload your tool once — workers download it through their authenticated launcher. Decompilers get nothing."
      />

      {status && (
        <div className={`flex items-center gap-2.5 px-4 py-3 rounded-xl text-sm border ${
          status.type === "ok"
            ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
            : status.type === "err"
            ? "bg-red-500/10 border-red-500/20 text-red-300"
            : "bg-blue-500/10 border-blue-500/20 text-blue-300"
        }`}>
          {status.type === "ok" ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> :
           status.type === "err" ? <XCircle className="w-4 h-4 flex-shrink-0" /> :
           <Info className="w-4 h-4 flex-shrink-0" />}
          {status.msg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Upload area */}
        <GlassCard className="p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Upload className="w-4 h-4 text-violet-400" />
            <span className="text-sm font-semibold text-slate-200">Upload Tool File</span>
          </div>

          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed cursor-pointer transition-all py-10 gap-3 ${
              dragOver
                ? "border-violet-500 bg-violet-500/10"
                : "border-slate-700/60 hover:border-violet-500/40 hover:bg-violet-500/5"
            }`}
          >
            {uploading ? (
              <Loader2 className="w-10 h-10 text-violet-400 animate-spin" />
            ) : (
              <FileCode2 className="w-10 h-10 text-slate-600" />
            )}
            <div className="text-center">
              <p className="text-sm font-medium text-slate-300">
                {uploading ? "Uploading…" : "Drop file here or click to browse"}
              </p>
              <p className="text-[11px] text-slate-600 mt-1">Any file type · Max 50 MB</p>
            </div>
            <input ref={fileRef} type="file" className="hidden" onChange={onFileChange} />
          </div>

          <p className="text-[11px] text-slate-600 leading-relaxed">
            Replaces any existing tool. The old file is permanently deleted.
          </p>
        </GlassCard>

        {/* Current file status */}
        <GlassCard className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileCode2 className="w-4 h-4 text-cyan-400" />
              <span className="text-sm font-semibold text-slate-200">Current Tool</span>
            </div>
            <button onClick={fetchInfo} className="text-slate-600 hover:text-slate-400 transition-colors">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>

          {loading ? (
            <div className="flex items-center gap-2 text-slate-500 text-sm py-4">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading…
            </div>
          ) : info?.exists ? (
            <div className="space-y-3">
              <div className="p-4 rounded-xl space-y-2.5" style={{ background: "rgba(6,182,212,0.06)", border: "1px solid rgba(6,182,212,0.15)" }}>
                <div className="flex items-start justify-between gap-2">
                  <div className="font-mono text-sm text-cyan-300 break-all">{info.filename}</div>
                  <Badge variant="valid">Active</Badge>
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div>
                    <span className="text-slate-600">Size</span>
                    <div className="text-slate-300 font-mono">{formatBytes(info.size || 0)}</div>
                  </div>
                  <div>
                    <span className="text-slate-600">Uploaded</span>
                    <div className="text-slate-300">{info.uploadedAt ? new Date(info.uploadedAt).toLocaleString() : "—"}</div>
                  </div>
                </div>
              </div>

              <div className="flex gap-2">
                <GlassButton
                  variant="danger"
                  size="sm"
                  onClick={handleDelete}
                  disabled={deleting}
                  className="flex-1"
                >
                  {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                  Delete
                </GlassButton>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <AlertCircle className="w-8 h-8 text-amber-500/60" />
              <p className="text-sm text-slate-500">No tool uploaded yet</p>
              <p className="text-[11px] text-slate-600">Upload a file on the left to enable worker downloads.</p>
            </div>
          )}
        </GlassCard>
      </div>

      {/* Build Executable */}
      <GlassCard className="p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-orange-400" />
          <span className="text-sm font-semibold text-slate-200">Build Standalone Executable</span>
          <span className="ml-auto text-[10px] font-mono px-2 py-0.5 rounded-full bg-orange-500/10 border border-orange-500/20 text-orange-400">Linux</span>
        </div>
        <p className="text-[11px] text-slate-500 leading-relaxed">
          Upload a <code className="font-mono text-orange-300">.py</code> file and the server will bundle it with PyInstaller into a single self-contained executable — no Python installation needed on the worker machine. The binary downloads automatically when the build finishes.
        </p>

        {buildStatus && (
          <div className={`flex items-center gap-2.5 px-4 py-3 rounded-xl text-sm border ${
            buildStatus.type === "ok"
              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
              : buildStatus.type === "err"
              ? "bg-red-500/10 border-red-500/20 text-red-300"
              : "bg-blue-500/10 border-blue-500/20 text-blue-300"
          }`}>
            {buildStatus.type === "ok" ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> :
             buildStatus.type === "err" ? <XCircle className="w-4 h-4 flex-shrink-0" /> :
             <Loader2 className="w-4 h-4 flex-shrink-0 animate-spin" />}
            {buildStatus.msg}
          </div>
        )}

        <div className="flex items-center gap-3">
          <GlassButton
            variant="outline"
            size="sm"
            onClick={() => buildRef.current?.click()}
            disabled={building}
            className="flex items-center gap-2"
            style={{ borderColor: "rgba(251,146,60,0.3)", color: "#fb923c", background: "rgba(251,146,60,0.08)" }}
          >
            {building
              ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Building…</>
              : <><Cpu className="w-3.5 h-3.5" />Select .py file &amp; Build</>}
          </GlassButton>
          <span className="text-[11px] text-slate-600">Build takes ~30–60 s</span>
          <input ref={buildRef} type="file" accept=".py" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleBuild(f); }} />
        </div>
      </GlassCard>

      {/* How it works */}
      <GlassCard className="p-5 space-y-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-violet-400" />
          <span className="text-sm font-semibold text-slate-200">How the Secure Launcher Works</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            {
              step: "1",
              title: "Worker runs launcher.py",
              desc: "The launcher is a tiny stub with zero tool logic — nothing to decompile.",
              color: "text-violet-400",
            },
            {
              step: "2",
              title: "Key + 2FA verified",
              desc: "Launcher sends the worker key and live TOTP code. Invalid = no download.",
              color: "text-cyan-400",
            },
            {
              step: "3",
              title: "Tool streams securely",
              desc: "Server streams the real tool binary only to authenticated workers. You can swap it any time.",
              color: "text-emerald-400",
            },
          ].map(({ step, title, desc, color }) => (
            <div key={step} className="flex gap-3">
              <div className={`text-2xl font-bold font-mono ${color} opacity-40 flex-shrink-0 leading-none`}>{step}</div>
              <div>
                <div className="text-sm font-medium text-slate-200">{title}</div>
                <div className="text-[11px] text-slate-500 mt-1 leading-relaxed">{desc}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-2 p-3 rounded-lg text-[11px] text-slate-500 leading-relaxed" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
          <span className="text-slate-400 font-medium">Give workers: </span>
          <code className="font-mono text-violet-300">launcher.py</code> + their worker key.
          The launcher auto-generates the 2FA code and downloads the tool only when the key is valid.
          To swap the tool, just upload a new file above — workers get the new version on their next launch.
        </div>
      </GlassCard>

      {/* Launcher download */}
      <GlassCard className="p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Download className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-semibold text-slate-200">Launcher Script</span>
        </div>
        <p className="text-[11px] text-slate-500 leading-relaxed">
          Give this script to workers. It asks for their key, generates the 2FA code, downloads the tool, and runs it.
          There's nothing in it to decompile — the actual tool lives only on this server.
        </p>
        <a
          href={`${base}/api/tool/launcher`}
          download="launcher.py"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-emerald-300 transition-all hover:text-emerald-200"
          style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.2)" }}
        >
          <Download className="w-4 h-4" />
          Download launcher.py
        </a>
      </GlassCard>
    </div>
  );
}
