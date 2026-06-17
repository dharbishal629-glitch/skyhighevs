import React, { useEffect, useState, useCallback } from "react";
import { useLocation } from "wouter";
import { Download, LogOut, RefreshCw, CheckCircle2, XCircle, Lock, TrendingUp, Activity, Check, Save, Settings } from "lucide-react";
import { format } from "date-fns";
import { CONFIG } from "../lib/config";

const API_BASE = CONFIG.API_BASE_URL.replace(/\/$/, "");

const API = (path: string, key: string) =>
  fetch(`${API_BASE}${path}`, { headers: { "x-api-key": key } }).then(r => r.json());

function StatBox({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: string | number; color: string }) {
  return (
    <div className="rounded-xl p-4 flex flex-col gap-1" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}>
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4" style={{ color }} />
        <span className="text-xs" style={{ color: "rgba(148,163,184,0.7)" }}>{label}</span>
      </div>
      <span className="text-2xl font-bold text-white">{value}</span>
    </div>
  );
}

function Toggle({ enabled, onToggle, label }: { enabled: boolean; onToggle: () => void; label: string }) {
  return (
    <button
      onClick={onToggle}
      className="flex items-center gap-2 text-xs transition-colors"
      style={{ color: enabled ? "#a78bfa" : "rgba(148,163,184,0.5)" }}
    >
      <div
        className="relative w-9 h-5 rounded-full transition-colors flex-shrink-0"
        style={{ background: enabled ? "rgba(139,92,246,0.5)" : "rgba(255,255,255,0.1)", border: `1px solid ${enabled ? "rgba(139,92,246,0.6)" : "rgba(255,255,255,0.1)"}` }}
      >
        <div
          className="absolute top-0.5 w-4 h-4 rounded-full transition-all"
          style={{
            left: enabled ? "calc(100% - 18px)" : "2px",
            background: enabled ? "#8b5cf6" : "rgba(148,163,184,0.4)",
          }}
        />
      </div>
      {label}
    </button>
  );
}

type WorkerSettings = {
  workerEditsEnabled: boolean;
  settings: {
    proxy:       { enabled: boolean; url: string };
    fingerprint: { enabled: boolean };
    adb:         { enabled: boolean };
    nopecha:     { enabled: boolean; key: string };
  };
};

export default function WorkerPortal() {
  const [, setLocation] = useLocation();
  const workerKey = sessionStorage.getItem("workerKey") || "";

  const [profile, setProfile]   = useState<any>(null);
  const [loading, setLoading]   = useState(true);
  const [dlStatus, setDlStatus] = useState<"idle" | "loading" | "done">("idle");

  // Worker Edits state
  const [workerSettings, setWorkerSettings] = useState<WorkerSettings | null>(null);
  const [editProxy, setEditProxy]           = useState("");
  const [editProxyOn, setEditProxyOn]       = useState(false);
  const [editFpOn, setEditFpOn]             = useState(false);
  const [editAdbOn, setEditAdbOn]           = useState(false);
  const [editNopechaOn, setEditNopechaOn]   = useState(false);
  const [editNopechaKey, setEditNopechaKey] = useState("");
  const [saving, setSaving]                 = useState(false);
  const [saveStatus, setSaveStatus]         = useState<"idle"|"ok"|"err">("idle");

  const logout = () => { sessionStorage.removeItem("workerKey"); setLocation("/worker-login"); };

  const load = useCallback(async () => {
    if (!workerKey) { setLocation("/worker-login"); return; }
    setLoading(true);
    try {
      const [me, ws] = await Promise.all([
        API("/api/worker/me", workerKey),
        API("/api/worker/my-settings", workerKey),
      ]);
      if (me.error) { logout(); return; }
      setProfile(me);
      if (ws && !ws.error) {
        setWorkerSettings(ws as WorkerSettings);
        const s = (ws as WorkerSettings).settings;
        setEditProxy(s.proxy.url);
        setEditProxyOn(s.proxy.enabled);
        setEditFpOn(s.fingerprint.enabled);
        setEditAdbOn(s.adb.enabled);
        setEditNopechaOn(s.nopecha.enabled);
        setEditNopechaKey(s.nopecha.key);
      }
    } catch { logout(); }
    finally { setLoading(false); }
  }, [workerKey]);

  useEffect(() => { load(); }, [load]);

  const saveSettings = async () => {
    setSaving(true);
    setSaveStatus("idle");
    try {
      const r = await fetch(`${API_BASE}/api/worker/my-settings`, {
        method: "PUT",
        headers: { "x-api-key": workerKey, "Content-Type": "application/json" },
        body: JSON.stringify({
          proxy:       { enabled: editProxyOn,   url: editProxy },
          fingerprint: { enabled: editFpOn },
          adb:         { enabled: editAdbOn },
          nopecha:     { enabled: editNopechaOn, key: editNopechaKey },
        }),
      });
      const d = await r.json();
      setSaveStatus(d.success ? "ok" : "err");
    } catch { setSaveStatus("err"); }
    finally {
      setSaving(false);
      setTimeout(() => setSaveStatus("idle"), 3000);
    }
  };

  const downloadLauncher = async () => {
    setDlStatus("loading");
    try {
      const r = await fetch(`${API_BASE}/api/tool/launcher`);
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "launcher.py";
      a.click();
      setDlStatus("done");
      setTimeout(() => setDlStatus("idle"), 3000);
    } catch { setDlStatus("idle"); }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center w-screen" style={{ minHeight: "100dvh", background: "hsl(228 30% 7%)" }}>
        <div style={{ width: 28, height: 28, border: "2px solid rgba(139,92,246,0.3)", borderTopColor: "#8b5cf6", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
        <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      </div>
    );
  }

  const s = profile?.stats ?? {};
  const expiresAt = profile?.expiresAt ? new Date(profile.expiresAt) : null;
  const expired = expiresAt && expiresAt < new Date();
  const daysLeft = expiresAt ? Math.max(0, Math.ceil((expiresAt.getTime() - Date.now()) / 86400000)) : null;
  const editsEnabled = workerSettings?.workerEditsEnabled ?? false;

  return (
    <div className="min-h-screen w-full" style={{ background: "hsl(228 30% 7%)", fontFamily: "system-ui, sans-serif" }}>
      {/* Top bar */}
      <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: "rgba(255,255,255,0.06)", background: "rgba(0,0,0,0.3)" }}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm"
            style={{ background: "linear-gradient(135deg, rgba(139,92,246,0.4), rgba(6,182,212,0.2))", border: "1px solid rgba(139,92,246,0.3)" }}>
            ⚡
          </div>
          <div>
            <span className="text-sm font-semibold text-white">CTRL.PNL</span>
            <span className="ml-2 text-xs px-1.5 py-0.5 rounded" style={{ background: "rgba(139,92,246,0.2)", color: "#a78bfa" }}>Worker</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={load} className="text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-colors"
            style={{ color: "rgba(148,163,184,0.7)", border: "1px solid rgba(255,255,255,0.07)" }}>
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
          <button onClick={logout} className="text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-colors"
            style={{ color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)" }}>
            <LogOut className="w-3 h-3" /> Logout
          </button>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-6 space-y-5">
        {/* Profile card */}
        <div className="rounded-xl p-5" style={{ background: "linear-gradient(135deg, rgba(139,92,246,0.12), rgba(6,182,212,0.06))", border: "1px solid rgba(139,92,246,0.2)" }}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs mb-1" style={{ color: "rgba(148,163,184,0.6)" }}>Logged in as</p>
              <h2 className="text-xl font-bold text-white">{profile?.discordUsername}</h2>
              <p className="text-xs font-mono mt-0.5" style={{ color: "rgba(148,163,184,0.5)" }}>ID: {profile?.discordId}</p>
            </div>
            <div className="flex flex-col items-end gap-1.5">
              <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                style={{
                  background: expired ? "rgba(239,68,68,0.15)" : "rgba(16,185,129,0.15)",
                  color: expired ? "#ef4444" : "#10b981",
                  border: `1px solid ${expired ? "rgba(239,68,68,0.3)" : "rgba(16,185,129,0.3)"}`,
                }}>
                {profile?.status}
              </span>
              {expiresAt && (
                <p className="text-xs" style={{ color: expired ? "#ef4444" : "rgba(148,163,184,0.6)" }}>
                  {expired ? "Expired" : `Expires in ${daysLeft}d`} · {format(expiresAt, "MMM d, yyyy")}
                </p>
              )}
              {!expiresAt && <p className="text-xs" style={{ color: "rgba(148,163,184,0.5)" }}>No expiry</p>}
            </div>
          </div>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatBox icon={Activity}    label="Generated"   value={s.tokensGenerated ?? 0}   color="#8b5cf6" />
          <StatBox icon={CheckCircle2} label="Valid"       value={s.tokensValid ?? 0}        color="#10b981" />
          <StatBox icon={Lock}         label="Locked"      value={s.tokensLocked ?? 0}       color="#f59e0b" />
          <StatBox icon={TrendingUp}   label="Unlock Rate" value={`${s.unlockRate ?? 0}%`}   color="#06b6d4" />
        </div>

        {/* Worker Edits settings */}
        <div className="rounded-xl p-5 space-y-4" style={{
          background: editsEnabled ? "rgba(139,92,246,0.06)" : "rgba(255,255,255,0.02)",
          border: editsEnabled ? "1px solid rgba(139,92,246,0.25)" : "1px solid rgba(255,255,255,0.06)",
        }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Settings className="w-4 h-4" style={{ color: editsEnabled ? "#a78bfa" : "rgba(148,163,184,0.4)" }} />
              <div>
                <h3 className="text-sm font-semibold text-white">My Settings</h3>
                <p className="text-xs mt-0.5" style={{ color: "rgba(148,163,184,0.5)" }}>
                  {editsEnabled
                    ? "Worker Edits is ON — your settings override the global config."
                    : "Worker Edits is OFF — ask your admin to enable it so your settings take effect."}
                </p>
              </div>
            </div>
            {editsEnabled && (
              <button
                onClick={saveSettings}
                disabled={saving}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                style={{
                  background: saveStatus === "ok"  ? "rgba(16,185,129,0.2)"  :
                              saveStatus === "err" ? "rgba(239,68,68,0.2)"   :
                              "linear-gradient(135deg, rgba(139,92,246,0.5), rgba(37,99,235,0.4))",
                  color:  saveStatus === "ok"  ? "#10b981" :
                          saveStatus === "err" ? "#ef4444" : "white",
                  border: saveStatus === "ok"  ? "1px solid rgba(16,185,129,0.4)"  :
                          saveStatus === "err" ? "1px solid rgba(239,68,68,0.4)" :
                          "1px solid rgba(139,92,246,0.3)",
                  opacity: saving ? 0.6 : 1,
                  cursor: saving ? "wait" : "pointer",
                }}
              >
                {saveStatus === "ok"  ? <><Check className="w-3.5 h-3.5" />Saved!</>  :
                 saveStatus === "err" ? <>Failed</>                                     :
                 saving               ? <>Saving...</>                                  :
                 <><Save className="w-3.5 h-3.5" />Save</>}
              </button>
            )}
          </div>

          {/* Settings grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Proxy */}
            <div className="rounded-lg p-3 space-y-2" style={{ background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <Toggle enabled={editProxyOn} onToggle={() => setEditProxyOn(v => !v)} label="Proxy" />
              {editProxyOn && (
                <input
                  type="text"
                  placeholder="http://user:pass@host:port"
                  value={editProxy}
                  onChange={e => setEditProxy(e.target.value)}
                  disabled={!editsEnabled}
                  className="w-full bg-transparent border rounded px-2 py-1.5 text-xs font-mono text-slate-300 outline-none transition-colors"
                  style={{ borderColor: "rgba(255,255,255,0.1)", opacity: editsEnabled ? 1 : 0.5 }}
                />
              )}
              {!editProxyOn && <p className="text-[10px]" style={{ color: "rgba(148,163,184,0.35)" }}>Disabled — uses admin config</p>}
            </div>

            {/* Fingerprint */}
            <div className="rounded-lg p-3 space-y-2" style={{ background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <Toggle enabled={editFpOn} onToggle={() => setEditFpOn(v => !v)} label="Fingerprint" />
              <p className="text-[10px]" style={{ color: "rgba(148,163,184,0.35)" }}>
                {editFpOn ? "Enabled — tool fetches a fingerprint from the pool" : "Disabled — uses admin config"}
              </p>
            </div>

            {/* ADB */}
            <div className="rounded-lg p-3 space-y-2" style={{ background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <Toggle enabled={editAdbOn} onToggle={() => setEditAdbOn(v => !v)} label="ADB IP Rotation" />
              <p className="text-[10px]" style={{ color: "rgba(148,163,184,0.35)" }}>
                {editAdbOn ? "Enabled — requires USB device connected" : "Disabled — uses admin config"}
              </p>
            </div>

            {/* NoPeCHA */}
            <div className="rounded-lg p-3 space-y-2" style={{ background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <Toggle enabled={editNopechaOn} onToggle={() => setEditNopechaOn(v => !v)} label="NoPeCHA" />
              {editNopechaOn && (
                <input
                  type="text"
                  placeholder="NoPeCHA API key"
                  value={editNopechaKey}
                  onChange={e => setEditNopechaKey(e.target.value)}
                  disabled={!editsEnabled}
                  className="w-full bg-transparent border rounded px-2 py-1.5 text-xs font-mono text-slate-300 outline-none transition-colors"
                  style={{ borderColor: "rgba(255,255,255,0.1)", opacity: editsEnabled ? 1 : 0.5 }}
                />
              )}
              {!editNopechaOn && <p className="text-[10px]" style={{ color: "rgba(148,163,184,0.35)" }}>Disabled — uses admin config</p>}
            </div>
          </div>

          {!editsEnabled && (
            <p className="text-[11px] text-center" style={{ color: "rgba(148,163,184,0.4)" }}>
              Settings are read-only until your admin enables Worker Edits for your account.
            </p>
          )}
        </div>

        {/* Download launcher */}
        <div className="rounded-xl p-5" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)" }}>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h3 className="text-sm font-semibold text-white mb-0.5">Secure Launcher</h3>
              <p className="text-xs" style={{ color: "rgba(148,163,184,0.6)" }}>
                Runs the tool entirely in-memory — nothing written to disk.
              </p>
            </div>
            <button
              onClick={downloadLauncher}
              disabled={dlStatus === "loading"}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all"
              style={{
                background: dlStatus === "done" ? "rgba(16,185,129,0.2)" : "linear-gradient(135deg, #7c3aed, #2563eb)",
                color: dlStatus === "done" ? "#10b981" : "white",
                border: dlStatus === "done" ? "1px solid rgba(16,185,129,0.4)" : "none",
                cursor: dlStatus === "loading" ? "wait" : "pointer",
              }}
            >
              {dlStatus === "done" ? <><Check className="w-4 h-4" />Downloaded!</> :
               dlStatus === "loading" ? <><RefreshCw className="w-4 h-4 animate-spin" />Downloading...</> :
               <><Download className="w-4 h-4" />Download launcher.py</>}
            </button>
          </div>
          <div className="mt-4 px-3 py-2 rounded-lg text-xs font-mono" style={{ background: "rgba(0,0,0,0.3)", color: "rgba(148,163,184,0.7)" }}>
            python launcher.py
          </div>
        </div>
      </div>
    </div>
  );
}
