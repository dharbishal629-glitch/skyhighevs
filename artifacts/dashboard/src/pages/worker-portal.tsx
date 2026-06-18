import React, { useEffect, useState, useCallback } from "react";
import { useLocation } from "wouter";
import { LogOut, RefreshCw, CheckCircle2, Lock, TrendingUp, Activity, Check, Save, Settings } from "lucide-react";
import { format } from "date-fns";
import { CONFIG } from "../lib/config";

const API_BASE = CONFIG.API_BASE_URL.replace(/\/$/, "");

const API = (path: string, key: string) =>
  fetch(`${API_BASE}${path}`, { headers: { "x-api-key": key } }).then(r => r.json());

function StatBox({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: string | number; color: string }) {
  return (
    <div className="rounded-xl p-4 flex flex-col gap-1" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}>
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4 flex-shrink-0" style={{ color }} />
        <span className="text-xs" style={{ color: "rgba(148,163,184,0.7)" }}>{label}</span>
      </div>
      <span className="text-2xl font-bold text-white">{value}</span>
    </div>
  );
}

function Toggle({ enabled, onToggle, label, disabled }: { enabled: boolean; onToggle: () => void; label: string; disabled?: boolean }) {
  return (
    <button
      onClick={onToggle}
      disabled={disabled}
      className="flex items-center gap-2 text-xs transition-colors"
      style={{ color: enabled ? "#a78bfa" : "rgba(148,163,184,0.5)", opacity: disabled ? 0.5 : 1, cursor: disabled ? "not-allowed" : "pointer" }}
    >
      <div
        className="relative w-9 h-5 rounded-full transition-colors flex-shrink-0"
        style={{ background: enabled ? "rgba(139,92,246,0.5)" : "rgba(255,255,255,0.1)", border: `1px solid ${enabled ? "rgba(139,92,246,0.6)" : "rgba(255,255,255,0.1)"}` }}
      >
        <div
          className="absolute top-0.5 w-4 h-4 rounded-full transition-all"
          style={{ left: enabled ? "calc(100% - 18px)" : "2px", background: enabled ? "#8b5cf6" : "rgba(148,163,184,0.4)" }}
        />
      </div>
      {label}
    </button>
  );
}

type WorkerSettings = {
  workerEditsEnabled: boolean;
  settings: {
    proxy:   { enabled: boolean; url: string };
    adb:     { enabled: boolean };
    nopecha: { enabled: boolean; key: string };
    cooldown: number;
  };
};

export default function WorkerPortal() {
  const [, setLocation] = useLocation();
  const workerKey = sessionStorage.getItem("workerKey") || "";

  const [profile, setProfile]   = useState<any>(null);
  const [loading, setLoading]   = useState(true);
  const [dlStatus, setDlStatus] = useState<"idle" | "loading" | "done">("idle");

  const [workerSettings, setWorkerSettings] = useState<WorkerSettings | null>(null);
  const [editProxy, setEditProxy]           = useState("");
  const [editProxyOn, setEditProxyOn]       = useState(false);
  const [editAdbOn, setEditAdbOn]           = useState(false);
  const [editNopechaOn, setEditNopechaOn]   = useState(false);
  const [editNopechaKey, setEditNopechaKey] = useState("");
  const [editCooldown, setEditCooldown]     = useState(0);
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
        setEditAdbOn(s.adb.enabled);
        setEditNopechaOn(s.nopecha.enabled);
        setEditNopechaKey(s.nopecha.key);
        setEditCooldown(s.cooldown ?? 0);
      }
    } catch { logout(); }
    finally { setLoading(false); }
  }, [workerKey]);

  useEffect(() => { load(); }, [load]);

  const saveSettings = async () => {
    setSaving(true); setSaveStatus("idle");
    try {
      const r = await fetch(`${API_BASE}/api/worker/my-settings`, {
        method: "PUT",
        headers: { "x-api-key": workerKey, "Content-Type": "application/json" },
        body: JSON.stringify({
          proxy:   { enabled: editProxyOn,   url: editProxy },
          adb:     { enabled: editAdbOn },
          nopecha: { enabled: editNopechaOn, key: editNopechaKey },
          cooldown: editCooldown,
        }),
      });
      const d = await r.json();
      setSaveStatus(d.success ? "ok" : "err");
    } catch { setSaveStatus("err"); }
    finally { setSaving(false); setTimeout(() => setSaveStatus("idle"), 3000); }
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
    <div style={{ minHeight: "100dvh", width: "100%", background: "hsl(228 30% 7%)", fontFamily: "system-ui, sans-serif", overflowY: "auto", WebkitOverflowScrolling: "touch" }}>
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b sticky top-0 z-10" style={{ borderColor: "rgba(255,255,255,0.06)", background: "rgba(10,10,20,0.95)", backdropFilter: "blur(8px)" }}>
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center text-xs flex-shrink-0"
            style={{ background: "linear-gradient(135deg, rgba(139,92,246,0.4), rgba(6,182,212,0.2))", border: "1px solid rgba(139,92,246,0.3)" }}>
            ⚡
          </div>
          <div>
            <span className="text-sm font-semibold text-white">CTRL.PNL</span>
            <span className="ml-2 text-xs px-1.5 py-0.5 rounded" style={{ background: "rgba(139,92,246,0.2)", color: "#a78bfa" }}>Worker</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="text-xs flex items-center gap-1 px-2 py-1.5 rounded-lg transition-colors" style={{ color: "rgba(148,163,184,0.7)", border: "1px solid rgba(255,255,255,0.07)" }}>
            <RefreshCw className="w-3 h-3" />
          </button>
          <button onClick={logout} className="text-xs flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg" style={{ color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)" }}>
            <LogOut className="w-3 h-3" /> Out
          </button>
        </div>
      </div>

      <div className="px-4 py-4 space-y-4 max-w-2xl mx-auto pb-8">
        {/* Profile card */}
        <div className="rounded-xl p-4" style={{ background: "linear-gradient(135deg, rgba(139,92,246,0.12), rgba(6,182,212,0.06))", border: "1px solid rgba(139,92,246,0.2)" }}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs mb-0.5" style={{ color: "rgba(148,163,184,0.6)" }}>Logged in as</p>
              <h2 className="text-lg font-bold text-white">{profile?.discordUsername}</h2>
              <p className="text-xs font-mono mt-0.5" style={{ color: "rgba(148,163,184,0.5)" }}>{profile?.discordId}</p>
            </div>
            <div className="flex flex-col items-end gap-1">
              <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                style={{ background: expired ? "rgba(239,68,68,0.15)" : "rgba(16,185,129,0.15)", color: expired ? "#ef4444" : "#10b981", border: `1px solid ${expired ? "rgba(239,68,68,0.3)" : "rgba(16,185,129,0.3)"}` }}>
                {profile?.status}
              </span>
              {expiresAt && (
                <p className="text-xs" style={{ color: expired ? "#ef4444" : "rgba(148,163,184,0.6)" }}>
                  {expired ? "Expired" : `${daysLeft}d left`} · {format(expiresAt, "MMM d, yyyy")}
                </p>
              )}
              {!expiresAt && <p className="text-xs" style={{ color: "rgba(148,163,184,0.5)" }}>No expiry</p>}
            </div>
          </div>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 gap-3">
          <StatBox icon={Activity}     label="Generated"   value={s.tokensGenerated ?? 0}  color="#8b5cf6" />
          <StatBox icon={CheckCircle2} label="Valid"        value={s.tokensValid ?? 0}       color="#10b981" />
          <StatBox icon={Lock}         label="Locked"       value={s.tokensLocked ?? 0}      color="#f59e0b" />
          <StatBox icon={TrendingUp}   label="Unlock Rate"  value={`${s.unlockRate ?? 0}%`}  color="#06b6d4" />
        </div>

        {/* My Settings */}
        <div className="rounded-xl p-4 space-y-3" style={{
          background: editsEnabled ? "rgba(139,92,246,0.06)" : "rgba(255,255,255,0.02)",
          border: editsEnabled ? "1px solid rgba(139,92,246,0.25)" : "1px solid rgba(255,255,255,0.06)",
        }}>
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <Settings className="w-4 h-4 flex-shrink-0" style={{ color: editsEnabled ? "#a78bfa" : "rgba(148,163,184,0.4)" }} />
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-white">My Settings</h3>
                <p className="text-xs truncate" style={{ color: "rgba(148,163,184,0.5)" }}>
                  {editsEnabled ? "Worker Edits ON — your settings are active." : "OFF — ask admin to enable Worker Edits."}
                </p>
              </div>
            </div>
            {editsEnabled && (
              <button
                onClick={saveSettings}
                disabled={saving}
                className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                style={{
                  background: saveStatus === "ok" ? "rgba(16,185,129,0.2)" : saveStatus === "err" ? "rgba(239,68,68,0.2)" : "linear-gradient(135deg, rgba(139,92,246,0.5), rgba(37,99,235,0.4))",
                  color:  saveStatus === "ok" ? "#10b981" : saveStatus === "err" ? "#ef4444" : "white",
                  border: saveStatus === "ok" ? "1px solid rgba(16,185,129,0.4)" : saveStatus === "err" ? "1px solid rgba(239,68,68,0.4)" : "1px solid rgba(139,92,246,0.3)",
                  opacity: saving ? 0.6 : 1, cursor: saving ? "wait" : "pointer",
                }}
              >
                {saveStatus === "ok" ? <><Check className="w-3.5 h-3.5" />Saved</> : saveStatus === "err" ? <>Failed</> : saving ? <>Saving…</> : <><Save className="w-3.5 h-3.5" />Save</>}
              </button>
            )}
          </div>

          {/* Settings cards */}
          <div className="grid grid-cols-1 gap-2">
            {/* Proxy */}
            <div className="rounded-lg p-3 space-y-2" style={{ background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <Toggle enabled={editProxyOn} onToggle={() => setEditProxyOn(v => !v)} label="Proxy" disabled={!editsEnabled} />
              {editProxyOn ? (
                <input type="text" placeholder="http://user:pass@host:port" value={editProxy} onChange={e => setEditProxy(e.target.value)} disabled={!editsEnabled}
                  className="w-full bg-transparent border rounded px-2 py-1.5 text-xs font-mono text-slate-300 outline-none"
                  style={{ borderColor: "rgba(255,255,255,0.1)", opacity: editsEnabled ? 1 : 0.5 }} />
              ) : (
                <p className="text-[10px]" style={{ color: "rgba(148,163,184,0.35)" }}>Uses admin config</p>
              )}
            </div>

            {/* ADB */}
            <div className="rounded-lg p-3 space-y-1" style={{ background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <Toggle enabled={editAdbOn} onToggle={() => setEditAdbOn(v => !v)} label="ADB IP Rotation" disabled={!editsEnabled} />
              <p className="text-[10px]" style={{ color: "rgba(148,163,184,0.35)" }}>
                {editAdbOn ? "Enabled — requires USB device" : "Uses admin config"}
              </p>
            </div>

            {/* NoPeCHA */}
            <div className="rounded-lg p-3 space-y-2" style={{ background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <Toggle enabled={editNopechaOn} onToggle={() => setEditNopechaOn(v => !v)} label="NoPeCHA" disabled={!editsEnabled} />
              {editNopechaOn ? (
                <input type="text" placeholder="NoPeCHA API key" value={editNopechaKey} onChange={e => setEditNopechaKey(e.target.value)} disabled={!editsEnabled}
                  className="w-full bg-transparent border rounded px-2 py-1.5 text-xs font-mono text-slate-300 outline-none"
                  style={{ borderColor: "rgba(255,255,255,0.1)", opacity: editsEnabled ? 1 : 0.5 }} />
              ) : (
                <p className="text-[10px]" style={{ color: "rgba(148,163,184,0.35)" }}>Uses admin config</p>
              )}
            </div>

            {/* Cooldown */}
            <div className="rounded-lg p-3 space-y-2" style={{ background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <p className="text-xs" style={{ color: editsEnabled ? "rgba(148,163,184,0.8)" : "rgba(148,163,184,0.4)" }}>Cooldown (seconds)</p>
              <div className="flex items-center gap-2">
                <input type="number" min="0" max="3600" placeholder="0" value={editCooldown} onChange={e => setEditCooldown(Math.max(0, Number(e.target.value)))} disabled={!editsEnabled}
                  className="w-24 bg-transparent border rounded px-2 py-1.5 text-xs font-mono text-slate-300 outline-none"
                  style={{ borderColor: "rgba(255,255,255,0.1)", opacity: editsEnabled ? 1 : 0.5 }} />
                <span className="text-[10px]" style={{ color: "rgba(148,163,184,0.35)" }}>
                  {editCooldown > 0 ? `${editCooldown}s between accounts` : "No cooldown (uses admin config)"}
                </span>
              </div>
            </div>
          </div>

          {!editsEnabled && (
            <p className="text-[11px] text-center pt-1" style={{ color: "rgba(148,163,184,0.4)" }}>
              Settings are read-only until your admin enables Worker Edits.
            </p>
          )}
        </div>

      </div>
    </div>
  );
}
