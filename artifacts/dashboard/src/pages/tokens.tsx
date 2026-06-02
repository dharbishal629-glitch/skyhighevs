import React, { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { GlassCard, GlassButton, Badge, GlassInput, ProgressBar, SectionHeader } from "@/components/ui/cyber-components";
import { useFetchTokens } from "@/lib/api-client";
import { Key, Download, Search, RefreshCw, Copy, Check, ChevronLeft, ChevronRight, Filter, Zap, CheckCircle2, XCircle, AlertCircle, Loader2 } from "lucide-react";
import { format } from "date-fns";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/components/ui/cyber-components";

const PAGE_SIZE = 50;

interface ZeusResult { email: string; status?: string; trusted?: boolean; type?: string; message?: string; [key: string]: unknown }

export default function Tokens() {
  const { getHeaders, apiBaseUrl, config } = useAuth();
  const [filterStatus, setFilterStatus] = useState("");
  const [searchWorker, setSearchWorker] = useState("");
  const [page, setPage] = useState(1);
  const [copied, setCopied] = useState<string | null>(null);
  const [zeusOpen, setZeusOpen] = useState(false);
  const [zeusInput, setZeusInput] = useState("");
  const [zeusLoading, setZeusLoading] = useState(false);
  const [zeusResults, setZeusResults] = useState<ZeusResult[]>([]);
  const [zeusError, setZeusError] = useState("");

  const { data, isLoading, refetch } = useFetchTokens(
    { status: filterStatus || undefined, discordId: searchWorker || undefined },
    { request: { headers: getHeaders() } }
  );

  const tokens = data?.tokens || [];
  const totalPages = Math.max(1, Math.ceil(tokens.length / PAGE_SIZE));
  const pageTokens = tokens.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const copyToken = (t: string) => { navigator.clipboard.writeText(t); setCopied(t); setTimeout(() => setCopied(null), 1500); };

  const runZeusCheck = async () => {
    const emails = zeusInput.split("\n").map(e => e.trim()).filter(Boolean);
    if (emails.length === 0) { setZeusError("Enter at least one email."); return; }
    setZeusLoading(true); setZeusError(""); setZeusResults([]);
    try {
      const res = await fetch(`${apiBaseUrl}/api/zeus/check`, {
        method: "POST",
        headers: { ...getHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ emails }),
      });
      const data = await res.json() as { results?: ZeusResult[]; error?: string };
      if (!res.ok) { setZeusError(data.error || `Error ${res.status}`); }
      else { setZeusResults(data.results || []); }
    } catch {
      setZeusError("Could not reach API server.");
    }
    setZeusLoading(false);
  };

  const loadAllEmails = () => {
    const emails = tokens.filter(t => t.email).map(t => t.email as string);
    setZeusInput([...new Set(emails)].join("\n"));
  };

  const exportTokens = () => {
    const lines = tokens.map(t => `${t.email || ""}:${(t as any).accountPass || ""}:${t.token}`);
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/plain" }));
    a.download = `tokens_${format(new Date(), "yyyyMMdd_HHmm")}.txt`; a.click();
  };

  const copyAllValid = () => {
    const lines = tokens.filter(t => t.status === "VALID").map(t => `${t.email || ""}:${(t as any).accountPass || ""}:${t.token}`);
    navigator.clipboard.writeText(lines.join("\n"));
  };

  const stats = {
    valid: tokens.filter(t => t.status === "VALID").length,
    locked: tokens.filter(t => t.status === "LOCKED").length,
    invalid: tokens.filter(t => t.status === "INVALID").length,
  };

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Data Tokens"
        sub={`${tokens.length.toLocaleString()} records · Page ${page} of ${totalPages}`}
        action={
          <div className="flex items-center gap-2">
            <GlassButton size="sm" variant={zeusOpen ? "gold" : "secondary"} onClick={() => setZeusOpen(v => !v)}>
              <Zap className="w-3.5 h-3.5" />Zeus-X
            </GlassButton>
            <GlassButton size="sm" variant="gold" onClick={copyAllValid}><Copy className="w-3.5 h-3.5" />Copy Valid</GlassButton>
            <GlassButton size="sm" variant="secondary" onClick={exportTokens}><Download className="w-3.5 h-3.5" />Export</GlassButton>
            <GlassButton size="sm" variant="secondary" onClick={() => refetch()}><RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} /></GlassButton>
          </div>
        }
      />

      {/* Zeus-X Panel */}
      {zeusOpen && (
        <GlassCard className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-semibold text-slate-200">Zeus-X Email Checker</span>
            {!config.zeusEnabled && (
              <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                Enable in Config
              </span>
            )}
          </div>
          <div className="space-y-3">
            <div className="flex gap-2">
              <textarea
                value={zeusInput}
                onChange={e => setZeusInput(e.target.value)}
                placeholder="Paste emails here, one per line..."
                rows={4}
                className="flex-1 bg-white/5 border border-white/10 rounded-md px-3 py-2 text-xs font-mono text-white placeholder:text-white/20 focus:outline-none focus:border-amber-500/40 resize-none"
              />
            </div>
            <div className="flex gap-2 flex-wrap">
              <GlassButton size="sm" variant="gold" onClick={runZeusCheck} disabled={zeusLoading}>
                {zeusLoading ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Checking…</> : <><Zap className="w-3.5 h-3.5" />Check with Zeus-X</>}
              </GlassButton>
              <GlassButton size="sm" variant="secondary" onClick={loadAllEmails}>
                Load emails from table
              </GlassButton>
              {zeusResults.length > 0 && (
                <GlassButton size="sm" variant="secondary" onClick={() => setZeusResults([])}>
                  Clear results
                </GlassButton>
              )}
            </div>
            {zeusError && (
              <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />{zeusError}
              </div>
            )}
            {zeusResults.length > 0 && (
              <div className="space-y-1.5 max-h-64 overflow-y-auto">
                {zeusResults.map((r, i) => (
                  <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-lg text-xs" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    {r.status === "error" ? (
                      <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                    ) : r.trusted ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                    ) : (
                      <XCircle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                    )}
                    <span className="font-mono text-slate-300 flex-1">{r.email}</span>
                    {r.type && <span className="text-cyan-400/70">{String(r.type)}</span>}
                    {r.status && <span className={cn("font-medium", r.trusted ? "text-emerald-400" : r.status === "error" ? "text-red-400" : "text-amber-400")}>{String(r.status)}</span>}
                    {r.message && <span className="text-slate-600 text-[10px]">{String(r.message)}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </GlassCard>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Valid", value: stats.valid, color: "green" as const },
          { label: "Locked", value: stats.locked, color: "gold" as const },
          { label: "Invalid", value: stats.invalid, color: "red" as const },
        ].map(({ label, value, color }) => (
          <GlassCard key={label} className="p-4">
            <div className="text-xs text-slate-500 mb-1">{label}</div>
            <div className="text-xl font-display font-bold text-slate-100">{value.toLocaleString()}</div>
            <div className="mt-2"><ProgressBar value={value} max={tokens.length || 1} color={color} /></div>
          </GlassCard>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <Filter className="w-3.5 h-3.5 text-slate-600" />
        <div className="flex rounded-lg overflow-hidden border border-white/8">
          {["", "VALID", "LOCKED", "INVALID"].map(s => (
            <button key={s} onClick={() => { setFilterStatus(s); setPage(1); }}
              className={cn("px-3 py-1.5 text-xs font-medium transition-colors", filterStatus === s
                ? s === "VALID" ? "bg-emerald-500/20 text-emerald-400" : s === "LOCKED" ? "bg-amber-500/20 text-amber-400" : s === "INVALID" ? "bg-red-500/20 text-red-400" : "bg-violet-500/20 text-violet-400"
                : "text-slate-600 hover:text-slate-400 bg-transparent")}>
              {s || "ALL"}
            </button>
          ))}
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-600" />
          <GlassInput placeholder="Worker ID / username..." value={searchWorker} onChange={e => { setSearchWorker(e.target.value); setPage(1); }} className="pl-9 h-8 w-48 text-xs" />
        </div>
      </div>

      {/* Table */}
      <GlassCard className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              {["Token", "Email", "Status", "Generator", "Timestamp", ""].map(h => (
                <th key={h} className="p-3 text-slate-600 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={6} className="p-8 text-center text-slate-600 animate-pulse">Querying database...</td></tr>
            ) : pageTokens.length === 0 ? (
              <tr><td colSpan={6} className="p-8 text-center text-slate-600">No records match.</td></tr>
            ) : pageTokens.map(token => (
              <tr key={token.id} className="hover:bg-white/2 transition-colors group" style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <td className="p-3 font-mono">
                  <span className="text-slate-400 group-hover:text-slate-200 transition-colors truncate block max-w-[200px] md:max-w-sm" title={token.token}>
                    {token.token.length > 55 ? `${token.token.slice(0, 55)}…` : token.token}
                  </span>
                </td>
                <td className="p-3 text-slate-600 text-[11px]">{token.email || "—"}</td>
                <td className="p-3">
                  <Badge variant={token.status === "VALID" ? "valid" : token.status === "LOCKED" ? "expired" : "locked"}>{token.status}</Badge>
                </td>
                <td className="p-3 text-cyan-400/70 text-[11px]">{token.discordUsername || "—"}</td>
                <td className="p-3 text-slate-600 text-[10px]">{format(new Date(token.createdAt), "MMM dd HH:mm:ss")}</td>
                <td className="p-3">
                  <button onClick={() => copyToken(token.token)} className="text-slate-600 hover:text-cyan-400 transition-colors">
                    {copied === token.token ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </GlassCard>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-600">
            {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, tokens.length)} of {tokens.length.toLocaleString()}
          </span>
          <div className="flex items-center gap-1">
            <GlassButton size="xs" variant="secondary" onClick={() => setPage(1)} disabled={page === 1}>«</GlassButton>
            <GlassButton size="xs" variant="secondary" onClick={() => setPage(p => p - 1)} disabled={page === 1}><ChevronLeft className="w-3.5 h-3.5" /></GlassButton>
            <span className="px-3 text-xs text-slate-400">{page} / {totalPages}</span>
            <GlassButton size="xs" variant="secondary" onClick={() => setPage(p => p + 1)} disabled={page === totalPages}><ChevronRight className="w-3.5 h-3.5" /></GlassButton>
            <GlassButton size="xs" variant="secondary" onClick={() => setPage(totalPages)} disabled={page === totalPages}>»</GlassButton>
          </div>
        </div>
      )}
    </div>
  );
}
