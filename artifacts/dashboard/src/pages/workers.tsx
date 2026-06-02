import React, { useState, useMemo } from "react";
import { useAuth } from "@/lib/auth-context";
import { GlassCard, GlassButton, Badge, GlassInput, ProgressBar, SectionHeader } from "@/components/ui/cyber-components";
import { useListWorkers, useCreateWorkerKey, useDeleteWorkerKey } from "@/lib/api-client";
import { useQueryClient } from "@tanstack/react-query";
import { Users, Plus, ShieldOff, Copy, Check, Download, Search, RefreshCw, ChevronDown, ChevronUp, CheckSquare, Square, Trash2, ArrowUpDown } from "lucide-react";
import { format } from "date-fns";
import * as Dialog from "@radix-ui/react-dialog";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { cn } from "@/components/ui/cyber-components";

const schema = z.object({
  discordId: z.string().min(1, "Required"),
  discordUsername: z.string().min(1, "Required"),
  durationDays: z.coerce.number().min(0).optional(),
});

type SortField = "discordUsername" | "tokensGenerated" | "unlockRate";

export default function Workers() {
  const { getHeaders } = useAuth();
  const qc = useQueryClient();
  const [copied, setCopied] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [sort, setSort] = useState<{ field: SortField; dir: "asc" | "desc" }>({ field: "tokensGenerated", dir: "desc" });
  const [expanded, setExpanded] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data, isLoading, isError, refetch } = useListWorkers({ request: { headers: getHeaders() } });

  const createMut = useCreateWorkerKey({
    request: { headers: getHeaders() },
    mutation: { onSuccess: () => { qc.invalidateQueries({ queryKey: ["/api/workers/list"] }); setDialogOpen(false); reset(); } }
  });

  const revokeMut = useDeleteWorkerKey({
    request: { headers: getHeaders() },
    mutation: { onSuccess: () => qc.invalidateQueries({ queryKey: ["/api/workers/list"] }) }
  });

  const { register, handleSubmit, reset, formState: { errors } } = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema), defaultValues: { durationDays: 0 }
  });

  const workers = useMemo(() => {
    let list = data?.workers || [];
    if (statusFilter !== "ALL") list = list.filter(w => w.status === statusFilter);
    if (search) list = list.filter(w => w.discordUsername.toLowerCase().includes(search.toLowerCase()) || w.discordId.includes(search));
    return [...list].sort((a, b) => {
      let av: any = a[sort.field as keyof typeof a] ?? 0;
      let bv: any = b[sort.field as keyof typeof b] ?? 0;
      if (typeof av === "string") av = av.toLowerCase();
      if (typeof bv === "string") bv = bv.toLowerCase();
      return sort.dir === "asc" ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
    });
  }, [data, statusFilter, search, sort]);

  const copyKey = (key: string) => { navigator.clipboard.writeText(key); setCopied(key); setTimeout(() => setCopied(null), 2000); };

  const exportCsv = () => {
    const rows = ["username,discordId,status,generated,rate,expires"].concat(
      workers.map(w => `${w.discordUsername},${w.discordId},${w.status},${w.tokensGenerated},${w.unlockRate}%,${w.expiresAt || "NEVER"}`)
    );
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([rows.join("\n")], { type: "text/csv" }));
    a.download = `workers_${format(new Date(), "yyyyMMdd_HHmm")}.csv`; a.click();
  };

  const toggleSelect = (id: string) => setSelected(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const bulkRevoke = () => {
    if (!confirm(`Revoke ${selected.size} worker(s)?`)) return;
    workers.filter(w => selected.has(w.discordId) && w.status === "VALID").forEach(w => revokeMut.mutate({ data: { discordId: w.discordId } }));
    setSelected(new Set());
  };

  const toggleSort = (field: SortField) => setSort(s => s.field === field ? { field, dir: s.dir === "asc" ? "desc" : "asc" } : { field, dir: "desc" });

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Worker Nodes"
        sub={`${workers.length} workers · ${workers.reduce((s, w) => s + (w.tokensGenerated || 0), 0).toLocaleString()} total tokens`}
        action={
          <div className="flex items-center gap-2 flex-wrap">
            {selected.size > 0 && <GlassButton size="sm" variant="danger" onClick={bulkRevoke}><Trash2 className="w-3.5 h-3.5" />Revoke {selected.size}</GlassButton>}
            <GlassButton size="sm" variant="secondary" onClick={exportCsv}><Download className="w-3.5 h-3.5" />Export</GlassButton>
            <GlassButton size="sm" variant="secondary" onClick={() => refetch()}><RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} /></GlassButton>
            <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
              <Dialog.Trigger asChild>
                <GlassButton size="sm" variant="primary"><Plus className="w-3.5 h-3.5" />Deploy Worker</GlassButton>
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50" />
                <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-md focus:outline-none">
                  <GlassCard className="p-6 border border-violet-500/20">
                    <Dialog.Title className="text-base font-display font-semibold text-slate-100 mb-4">Deploy New Worker</Dialog.Title>
                    <form onSubmit={handleSubmit(v => createMut.mutate({ data: { ...v, durationDays: v.durationDays === 0 ? null : v.durationDays } }))} className="space-y-3">
                      <div>
                        <label className="text-[11px] text-slate-500 uppercase tracking-wider block mb-1">Discord User ID</label>
                        <GlassInput {...register("discordId")} placeholder="1234567890" />
                        {errors.discordId && <p className="text-red-400 text-xs mt-1">{errors.discordId.message}</p>}
                      </div>
                      <div>
                        <label className="text-[11px] text-slate-500 uppercase tracking-wider block mb-1">Discord Username</label>
                        <GlassInput {...register("discordUsername")} placeholder="username" />
                      </div>
                      <div>
                        <label className="text-[11px] text-slate-500 uppercase tracking-wider block mb-1">Duration (days · 0 = infinite)</label>
                        <GlassInput type="number" {...register("durationDays")} />
                      </div>
                      <div className="flex justify-end gap-2 mt-4">
                        <Dialog.Close asChild><GlassButton variant="secondary" size="sm" type="button">Cancel</GlassButton></Dialog.Close>
                        <GlassButton variant="primary" size="sm" type="submit" disabled={createMut.isPending}>
                          {createMut.isPending ? "Processing..." : "Generate Key"}
                        </GlassButton>
                      </div>
                    </form>
                  </GlassCard>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          </div>
        }
      />

      {isError && (
        <div className="px-4 py-3 rounded-xl border border-red-500/30 bg-red-500/5 text-red-400 text-sm font-sans">
          Failed to load workers — check your API URL, Worker Key, and TOTP Secret in Settings.
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-600" />
          <GlassInput placeholder="Search username / ID..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9 h-8 w-52 text-xs" />
        </div>
        <div className="flex rounded-lg overflow-hidden border border-white/8">
          {["ALL","VALID","LOCKED","EXPIRED"].map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={cn("px-3 py-1.5 text-xs font-medium transition-colors", statusFilter === s
                ? s === "VALID" ? "bg-emerald-500/20 text-emerald-400" : s === "LOCKED" ? "bg-red-500/20 text-red-400" : s === "EXPIRED" ? "bg-amber-500/20 text-amber-400" : "bg-violet-500/20 text-violet-400"
                : "text-slate-600 hover:text-slate-400 bg-transparent")}>
              {s}
            </button>
          ))}
        </div>
        {selected.size > 0 && (
          <button onClick={() => setSelected(new Set())} className="text-xs text-slate-600 hover:text-slate-400">Clear ({selected.size})</button>
        )}
      </div>

      {/* Table */}
      <GlassCard className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <th className="p-3 w-8">
                <button onClick={() => selected.size === workers.length ? setSelected(new Set()) : setSelected(new Set(workers.map(w => w.discordId)))} className="text-slate-600 hover:text-slate-300">
                  {selected.size === workers.length && workers.length > 0 ? <CheckSquare className="w-3.5 h-3.5 text-violet-400" /> : <Square className="w-3.5 h-3.5" />}
                </button>
              </th>
              {[
                { label: "Worker", field: null },
                { label: "Status", field: null },
                { label: "Key", field: null },
                { label: "Generated", field: "tokensGenerated" as SortField },
                { label: "Rate", field: "unlockRate" as SortField },
                { label: "Expires", field: null },
                { label: "", field: null },
              ].map(({ label, field }) => (
                <th key={label} className="p-3 text-slate-600 font-medium">
                  {field ? (
                    <button className="flex items-center gap-1 hover:text-slate-400 transition-colors" onClick={() => toggleSort(field)}>
                      {label} <ArrowUpDown className="w-3 h-3" />
                    </button>
                  ) : label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={8} className="p-8 text-center text-slate-600 animate-pulse">Loading workers...</td></tr>
            ) : workers.length === 0 ? (
              <tr><td colSpan={8} className="p-8 text-center text-slate-600">No workers match the current filter.</td></tr>
            ) : workers.map(worker => {
              const isSelected = selected.has(worker.discordId);
              const isExpanded = expanded === worker.discordId;
              return (
                <React.Fragment key={worker.id}>
                  <tr className={cn("transition-colors group", isSelected ? "bg-violet-500/5" : "hover:bg-white/2")} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <td className="p-3">
                      <button onClick={() => toggleSelect(worker.discordId)} className="text-slate-600 hover:text-violet-400">
                        {isSelected ? <CheckSquare className="w-3.5 h-3.5 text-violet-400" /> : <Square className="w-3.5 h-3.5" />}
                      </button>
                    </td>
                    <td className="p-3">
                      <div className="font-medium text-slate-200">{worker.discordUsername}</div>
                      <div className="text-[10px] text-slate-600">{worker.discordId}</div>
                    </td>
                    <td className="p-3">
                      <Badge variant={worker.status === "VALID" ? "valid" : worker.status === "LOCKED" ? "locked" : "expired"}>{worker.status}</Badge>
                    </td>
                    <td className="p-3 font-mono">
                      <div className="flex items-center gap-2">
                        <span className="text-slate-600 blur-sm group-hover:blur-none transition-all group-hover:text-slate-400">{worker.workerKey.substring(0, 14)}…</span>
                        <button onClick={() => copyKey(worker.workerKey)} className="text-slate-600 hover:text-cyan-400 transition-colors">
                          {copied === worker.workerKey ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                        </button>
                      </div>
                    </td>
                    <td className="p-3 text-slate-300 font-mono">{(worker.tokensGenerated || 0).toLocaleString()}</td>
                    <td className="p-3">
                      <div className={cn("font-mono font-semibold text-xs", worker.unlockRate >= 50 ? "text-emerald-400" : "text-red-400")}>{worker.unlockRate}%</div>
                      <div className="w-14 mt-1"><ProgressBar value={worker.unlockRate} color={worker.unlockRate >= 50 ? "green" : "red"} /></div>
                    </td>
                    <td className="p-3 text-slate-600 text-[11px]">{worker.expiresAt ? format(new Date(worker.expiresAt), "MMM dd, yy") : "Never"}</td>
                    <td className="p-3">
                      <div className="flex items-center gap-1">
                        <button onClick={() => setExpanded(isExpanded ? null : worker.discordId)} className="p-1.5 rounded-lg text-slate-600 hover:text-slate-300 hover:bg-white/5 transition-colors">
                          {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        </button>
                        {worker.status === "VALID" && (
                          <button onClick={() => { if (confirm(`Revoke ${worker.discordUsername}?`)) revokeMut.mutate({ data: { discordId: worker.discordId } }); }}
                            className="p-1.5 rounded-lg text-slate-600 hover:text-red-400 hover:bg-red-500/10 transition-colors">
                            <ShieldOff className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr style={{ background: 'rgba(139,92,246,0.04)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                      <td colSpan={8} className="px-6 py-4">
                        <div className="grid grid-cols-3 gap-4 text-xs font-mono">
                          <div>
                            <p className="text-slate-600 text-[10px] uppercase tracking-wider mb-1">Full Worker Key</p>
                            <p className="text-slate-400 break-all bg-black/30 p-2 rounded-lg border border-white/5">{worker.workerKey}</p>
                          </div>
                          <div>
                            <p className="text-slate-600 text-[10px] uppercase tracking-wider mb-1">Total Generated</p>
                            <p className="text-2xl font-display font-bold text-violet-300">{(worker.tokensGenerated || 0).toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="text-slate-600 text-[10px] uppercase tracking-wider mb-1">Efficiency</p>
                            <p className={cn("text-2xl font-display font-bold", worker.unlockRate >= 50 ? "text-emerald-400" : "text-red-400")}>{worker.unlockRate}%</p>
                            <div className="mt-2"><ProgressBar value={worker.unlockRate} color={worker.unlockRate >= 50 ? "green" : "red"} /></div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </GlassCard>
    </div>
  );
}
