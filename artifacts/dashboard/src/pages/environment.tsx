import React, { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  GlassCard, GlassButton, GlassInput, SectionHeader,
} from "@/components/ui/cyber-components";
import {
  Plus, Trash2, Save, RefreshCw, Eye, EyeOff,
  Terminal, CheckCircle2, XCircle, Loader2, Info, Copy, Check,
} from "lucide-react";

interface EnvEntry {
  key: string;
  value: string;
  description: string;
  updated_at: string;
}

const PRESETS: { key: string; description: string; masked: boolean }[] = [
  { key: "CTRL_API_URL",     description: "Your API server public URL (e.g. https://your-app.onrender.com)", masked: false },
  { key: "CTRL_API_KEY",     description: "Worker API Key injected into launcher (WORKER_API_KEY on server)", masked: true  },
  { key: "CTRL_TOTP_SECRET", description: "TOTP secret injected into launcher for 2FA",                     masked: true  },
];

function MaskedValue({ value }: { value: string }) {
  const [show, setShow] = useState(false);
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className="font-mono text-xs text-slate-300 truncate">
        {show ? value : "•".repeat(Math.min(value.length, 24))}
      </span>
      <button onClick={() => setShow(v => !v)} className="text-slate-600 hover:text-slate-400 flex-shrink-0">
        {show ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
      </button>
      <button onClick={copy} className="text-slate-600 hover:text-slate-400 flex-shrink-0">
        {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
      </button>
    </div>
  );
}

export default function EnvironmentPage() {
  const { getHeaders, apiBaseUrl } = useAuth();
  const base = apiBaseUrl || "";

  const [settings, setSettings] = useState<EnvEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<{ type: "ok" | "err" | "info"; msg: string } | null>(null);

  const [newKey, setNewKey]   = useState("");
  const [newVal, setNewVal]   = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [saving, setSaving]   = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const r = await fetch(`${base}/api/admin/env`, { headers: getHeaders() });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSettings(data.settings ?? []);
    } catch (e: any) {
      setStatus({ type: "err", msg: e?.message || "Failed to load" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function save(key: string, value: string, description: string) {
    setSaving(true);
    setStatus(null);
    try {
      const r = await fetch(`${base}/api/admin/env`, {
        method: "POST",
        headers: { ...getHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ key, value, description }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "Save failed");
      setStatus({ type: "ok", msg: `Saved: ${key}` });
      setNewKey(""); setNewVal(""); setNewDesc("");
      await load();
    } catch (e: any) {
      setStatus({ type: "err", msg: e?.message || "Save failed" });
    } finally {
      setSaving(false);
    }
  }

  async function del(key: string) {
    if (!confirm(`Delete "${key}"?`)) return;
    setDeleting(key);
    setStatus(null);
    try {
      const r = await fetch(`${base}/api/admin/env/${encodeURIComponent(key)}`, {
        method: "DELETE",
        headers: getHeaders(),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "Delete failed");
      setStatus({ type: "ok", msg: `Deleted: ${key}` });
      await load();
    } catch (e: any) {
      setStatus({ type: "err", msg: e?.message || "Delete failed" });
    } finally {
      setDeleting(null);
    }
  }

  const existingKeys = new Set(settings.map(s => s.key));
  const missingPresets = PRESETS.filter(p => !existingKeys.has(p.key));

  return (
    <div className="space-y-6 max-w-3xl">
      <SectionHeader
        icon={<Terminal className="w-5 h-5 text-emerald-400" />}
        title="Environment Variables"
        subtitle="Stored in the database — injected into launcher.py at download time. Change your server URL here without touching any code."
        action={
          <GlassButton size="sm" variant="secondary" onClick={load} disabled={loading}>
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </GlassButton>
        }
      />

      {status && (
        <div className={`flex items-center gap-2.5 px-4 py-3 rounded-xl text-sm border ${
          status.type === "ok"
            ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
            : "bg-red-500/10 border-red-500/20 text-red-300"
        }`}>
          {status.type === "ok"
            ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            : <XCircle className="w-4 h-4 flex-shrink-0" />}
          {status.msg}
        </div>
      )}

      {/* How it works */}
      <GlassCard className="p-4">
        <div className="flex items-start gap-3">
          <Info className="w-4 h-4 text-cyan-400 flex-shrink-0 mt-0.5" />
          <div className="space-y-1.5 text-[11px] text-slate-400 leading-relaxed">
            <p>
              <span className="text-slate-200 font-medium">How this works: </span>
              When a worker downloads <code className="font-mono text-violet-300">launcher.py</code>, the server
              reads these values from the database and embeds them directly into the script.
              The launcher then sets them as environment variables before running the tool.
            </p>
            <p>
              <span className="text-amber-300 font-medium">Moving to Render?</span>{" "}
              Update <code className="font-mono text-violet-300">CTRL_API_URL</code> to your Render URL here —
              next time any worker downloads a fresh launcher, it will point to the new server automatically.
            </p>
          </div>
        </div>
      </GlassCard>

      {/* Quick-set preset keys */}
      {missingPresets.length > 0 && (
        <GlassCard className="p-5">
          <p className="text-xs font-semibold text-slate-400 mb-3">Quick-add recommended variables</p>
          <div className="space-y-2">
            {missingPresets.map(p => (
              <button
                key={p.key}
                onClick={() => {
                  setNewKey(p.key);
                  setNewDesc(p.description);
                  setNewVal("");
                }}
                className="w-full text-left flex items-start gap-3 px-3 py-2.5 rounded-xl transition-all border border-white/6 hover:border-violet-500/30 hover:bg-violet-500/5"
              >
                <code className="font-mono text-xs text-violet-300 flex-shrink-0 mt-0.5">{p.key}</code>
                <span className="text-[11px] text-slate-500">{p.description}</span>
                <Plus className="w-3.5 h-3.5 text-slate-600 flex-shrink-0 mt-0.5 ml-auto" />
              </button>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Add new variable */}
      <GlassCard className="p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Plus className="w-4 h-4 text-violet-400" />
          <span className="text-sm font-semibold text-slate-200">Add / Update Variable</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">Key</label>
            <GlassInput
              value={newKey}
              onChange={e => setNewKey(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_"))}
              placeholder="MY_VARIABLE"
              className="font-mono text-xs"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">Value</label>
            <GlassInput
              value={newVal}
              onChange={e => setNewVal(e.target.value)}
              placeholder="value"
              className="font-mono text-xs"
            />
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">Description (optional)</label>
          <GlassInput
            value={newDesc}
            onChange={e => setNewDesc(e.target.value)}
            placeholder="What this variable is for"
            className="text-xs"
          />
        </div>
        <GlassButton
          variant="primary"
          size="sm"
          onClick={() => save(newKey, newVal, newDesc)}
          disabled={!newKey || saving}
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          {saving ? "Saving…" : "Save Variable"}
        </GlassButton>
      </GlassCard>

      {/* Current variables table */}
      <GlassCard className="p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-semibold text-slate-200">Stored Variables</span>
          <span className="text-xs text-slate-600 ml-auto">{settings.length} entries</span>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-slate-500 py-6">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : settings.length === 0 ? (
          <div className="py-8 text-center">
            <Terminal className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-sm text-slate-500">No variables set yet</p>
            <p className="text-[11px] text-slate-600 mt-1">Add CTRL_API_URL above to get started.</p>
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {settings.map(s => {
              const preset = PRESETS.find(p => p.key === s.key);
              return (
                <div key={s.key} className="py-3 first:pt-0 last:pb-0 flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <code className="font-mono text-xs text-violet-300">{s.key}</code>
                      {preset && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400 border border-violet-500/20">
                          launcher var
                        </span>
                      )}
                    </div>
                    <div className="mt-1">
                      {preset?.masked
                        ? <MaskedValue value={s.value} />
                        : <span className="font-mono text-xs text-slate-300 break-all">{s.value}</span>
                      }
                    </div>
                    {s.description && (
                      <p className="text-[10px] text-slate-600 mt-0.5">{s.description}</p>
                    )}
                    <p className="text-[9px] text-slate-700 mt-0.5">
                      Updated {new Date(s.updated_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <GlassButton
                      size="sm"
                      variant="secondary"
                      onClick={() => { setNewKey(s.key); setNewVal(s.value); setNewDesc(s.description); }}
                    >
                      <Save className="w-3 h-3" />
                    </GlassButton>
                    <GlassButton
                      size="sm"
                      variant="danger"
                      onClick={() => del(s.key)}
                      disabled={deleting === s.key}
                    >
                      {deleting === s.key
                        ? <Loader2 className="w-3 h-3 animate-spin" />
                        : <Trash2 className="w-3 h-3" />}
                    </GlassButton>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
