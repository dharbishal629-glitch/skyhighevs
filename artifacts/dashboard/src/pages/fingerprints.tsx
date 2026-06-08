import React, { useState, useRef } from "react";
import { useAuth } from "@/lib/auth-context";
import { GlassCard, GlassButton, SectionHeader } from "@/components/ui/cyber-components";
import { Fingerprint, Upload, Trash2, Plus, ToggleLeft, ToggleRight, RefreshCw, FileText, AlertTriangle } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface FpRecord {
  id: number;
  data: string;
  enabled: boolean;
  createdAt: string;
}

function ageDays(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const d  = Math.floor(ms / 86400000);
  if (d === 0) return "today";
  if (d === 1) return "1 day ago";
  return `${d} days ago`;
}

export default function FingerprintsPage() {
  const { getHeaders, apiBaseUrl } = useAuth();
  const { toast } = useToast();

  const [records, setRecords]   = useState<FpRecord[]>([]);
  const [loading, setLoading]   = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [singleText, setSingle] = useState("");
  const [bulkText, setBulk]     = useState("");
  const [activeTab, setTab]     = useState<"single" | "bulk">("single");
  const fileRef = useRef<HTMLInputElement>(null);

  const api = (path: string, opts?: RequestInit) =>
    fetch(`${apiBaseUrl}/api${path}`, { ...opts, headers: { ...getHeaders(), "Content-Type": "application/json", ...(opts?.headers || {}) } });

  async function load() {
    setLoading(true);
    setLoadError(null);
    try {
      const r = await api("/fingerprints/all");
      const j = await r.json();
      if (!r.ok) {
        const msg = j.error || `Server returned ${r.status}`;
        setLoadError(msg);
        toast({ title: "Load failed", description: msg, variant: "destructive" });
        return;
      }
      setRecords(j.fingerprints ?? []);
    } catch (e: any) {
      const msg = e?.message || "Network error — cannot reach the API server";
      setLoadError(msg);
      toast({ title: "Load failed", description: msg, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => { load(); }, []);

  async function addSingle() {
    if (!singleText.trim()) return;
    const r = await api("/fingerprints", { method: "POST", body: JSON.stringify({ data: singleText.trim() }) });
    const j = await r.json();
    if (j.success) { toast({ title: `Added 1 fingerprint` }); setSingle(""); load(); }
    else toast({ title: j.error || "Failed", variant: "destructive" });
  }

  async function addBulk(lines: string[]) {
    const valid = lines.map(l => l.trim()).filter(Boolean);
    if (!valid.length) return;
    const r = await api("/fingerprints", { method: "POST", body: JSON.stringify({ bulk: valid }) });
    const j = await r.json();
    if (j.success) { toast({ title: `Added ${j.inserted} fingerprint(s)` }); setBulk(""); load(); }
    else toast({ title: j.error || "Failed", variant: "destructive" });
  }

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
    await addBulk(lines);
    e.target.value = "";
  }

  async function toggle(id: number, cur: boolean) {
    await api(`/fingerprints/${id}`, { method: "PATCH", body: JSON.stringify({ enabled: !cur }) });
    setRecords(p => p.map(r => r.id === id ? { ...r, enabled: !cur } : r));
  }

  async function del(id: number) {
    await api(`/fingerprints/${id}`, { method: "DELETE" });
    setRecords(p => p.filter(r => r.id !== id));
    toast({ title: "Deleted" });
  }

  async function clearAll() {
    if (!confirm("Delete ALL fingerprints? This cannot be undone.")) return;
    await api("/fingerprints", { method: "DELETE" });
    setRecords([]);
    toast({ title: "All fingerprints cleared" });
  }

  const enabledCount = records.filter(r => r.enabled).length;

  return (
    <div className="space-y-6">
      <SectionHeader
        icon={Fingerprint}
        title="Fingerprint Manager"
        subtitle="Upload browser fingerprints — workers automatically pick a random enabled one each run"
        iconColor="text-violet-400"
      />

      {/* Stats bar */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Total",   value: records.length,                   color: "text-slate-300" },
          { label: "Enabled", value: enabledCount,                     color: "text-emerald-400" },
          { label: "Oldest",  value: records.length ? ageDays(records[0]?.createdAt) : "—", color: "text-violet-400" },
        ].map(s => (
          <GlassCard key={s.label} className="p-4 text-center">
            <div className={`text-2xl font-bold font-mono ${s.color}`}>{s.value}</div>
            <div className="text-[10px] text-slate-500 uppercase tracking-widest mt-1">{s.label}</div>
          </GlassCard>
        ))}
      </div>

      {/* Upload panel */}
      <GlassCard className="p-5 space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <Upload className="w-4 h-4 text-cyan-400" />
          <span className="text-sm font-semibold text-slate-200">Add Fingerprints</span>
        </div>

        {/* Tab selector */}
        <div className="flex gap-1 p-1 rounded-lg bg-white/4 w-fit" style={{ border: "1px solid rgba(255,255,255,0.07)" }}>
          {(["single", "bulk"] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded-md text-xs font-medium transition-all ${
                activeTab === t ? "bg-violet-600/30 text-violet-200 border border-violet-500/30" : "text-slate-400 hover:text-slate-300"
              }`}
            >
              {t === "single" ? "Single" : "Bulk (.txt)"}
            </button>
          ))}
        </div>

        {activeTab === "single" ? (
          <div className="space-y-3">
            <textarea
              value={singleText}
              onChange={e => setSingle(e.target.value)}
              placeholder='Paste fingerprint JSON here, e.g. {"userAgent":"Mozilla/5.0...","screen":{"width":1920,"height":1080},...}'
              rows={5}
              className="w-full bg-black/30 border border-white/10 rounded-lg p-3 text-xs font-mono text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-violet-500/40 resize-y"
            />
            <GlassButton onClick={addSingle} disabled={!singleText.trim()} className="flex items-center gap-2">
              <Plus className="w-3.5 h-3.5" /> Add Fingerprint
            </GlassButton>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-500/8 border border-amber-500/20">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-amber-300/80">One fingerprint JSON per line in the .txt file, or paste below.</p>
            </div>
            <textarea
              value={bulkText}
              onChange={e => setBulk(e.target.value)}
              placeholder={"Line 1: {\"userAgent\":\"Mozilla/5.0...\"}\nLine 2: {\"userAgent\":\"Mozilla/5.0...\"}"}
              rows={6}
              className="w-full bg-black/30 border border-white/10 rounded-lg p-3 text-xs font-mono text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-violet-500/40 resize-y"
            />
            <div className="flex gap-3">
              <GlassButton onClick={() => addBulk(bulkText.split("\n"))} disabled={!bulkText.trim()} className="flex items-center gap-2">
                <Plus className="w-3.5 h-3.5" /> Add from text
              </GlassButton>
              <GlassButton onClick={() => fileRef.current?.click()} className="flex items-center gap-2">
                <FileText className="w-3.5 h-3.5" /> Upload .txt file
              </GlassButton>
              <input ref={fileRef} type="file" accept=".txt,text/plain" className="hidden" onChange={onFileChange} />
            </div>
          </div>
        )}
      </GlassCard>

      {/* Fingerprint list */}
      <GlassCard className="p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Fingerprint className="w-4 h-4 text-violet-400" />
            <span className="text-sm font-semibold text-slate-200">Fingerprint Pool</span>
            <span className="text-xs text-slate-500 font-mono">{records.length} total · {enabledCount} enabled</span>
          </div>
          <div className="flex gap-2">
            <button onClick={load} className="p-1.5 rounded-lg hover:bg-white/8 text-slate-500 hover:text-slate-300 transition-colors">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
            {records.length > 0 && (
              <button onClick={clearAll} className="p-1.5 rounded-lg hover:bg-red-500/10 text-slate-500 hover:text-red-400 transition-colors">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {loadError ? (
          <div className="flex items-start gap-3 p-4 rounded-xl bg-red-500/8 border border-red-500/20">
            <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-300">Failed to load fingerprints</p>
              <p className="text-xs text-red-400/70 mt-0.5 font-mono">{loadError}</p>
              <button onClick={load} className="mt-2 text-xs text-red-300 hover:text-red-200 underline underline-offset-2">
                Retry
              </button>
            </div>
          </div>
        ) : records.length === 0 ? (
          <div className="text-center py-12 text-slate-600">
            <Fingerprint className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No fingerprints uploaded yet</p>
            <p className="text-xs mt-1">Workers will use local generation until you add fingerprints here</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
            {records.map((fp) => (
              <div
                key={fp.id}
                className={`flex items-start gap-3 p-3 rounded-xl transition-all ${
                  fp.enabled
                    ? "bg-emerald-500/5 border border-emerald-500/15"
                    : "bg-white/3 border border-white/6 opacity-60"
                }`}
              >
                {/* Toggle */}
                <button onClick={() => toggle(fp.id, fp.enabled)} className="flex-shrink-0 mt-0.5 transition-colors">
                  {fp.enabled
                    ? <ToggleRight className="w-5 h-5 text-emerald-400" />
                    : <ToggleLeft className="w-5 h-5 text-slate-600" />}
                </button>

                {/* Data preview */}
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-mono text-slate-400 truncate">{fp.data}</p>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-[10px] text-slate-600">#{fp.id}</span>
                    <span className="text-[10px] text-slate-600">Added {ageDays(fp.createdAt)}</span>
                    <span className={`text-[10px] font-medium ${fp.enabled ? "text-emerald-400" : "text-slate-600"}`}>
                      {fp.enabled ? "ACTIVE" : "DISABLED"}
                    </span>
                  </div>
                </div>

                {/* Delete */}
                <button
                  onClick={() => del(fp.id)}
                  className="flex-shrink-0 p-1 rounded-lg hover:bg-red-500/15 text-slate-600 hover:text-red-400 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      {/* Worker info */}
      <GlassCard className="p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-violet-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-slate-400 space-y-1">
            <p className="text-slate-300 font-medium">How workers use fingerprints</p>
            <p>Each worker session picks a random <span className="text-emerald-400 font-mono">ACTIVE</span> fingerprint and injects it into the browser before Discord loads. Discord's fraud detection sees a known fingerprint with history rather than a brand-new one.</p>
            <p className="text-violet-300">The older the fingerprint creation date, the more aged the account appears to Discord.</p>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
