import React, { useEffect, useRef, useState, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";
import { GlassCard, GlassButton, StatCard, SectionHeader, ProgressBar } from "@/components/ui/cyber-components";
import { useGetDashboardStats } from "@/lib/api-client";
import {
  Activity, Users, Key, AlertTriangle, RefreshCw,
  Terminal as TerminalIcon, Maximize2, Minimize2, Trash2,
  Download, CheckCircle2, XCircle, Lock, TrendingUp, Zap,
  MoreVertical, LogOut, Settings, Copy, Database,
} from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useLocation } from "wouter";
import { format } from "date-fns";
import { AreaChart, Area, ResponsiveContainer, Tooltip } from "recharts";

function buildSparkline(total: number, len = 14) {
  if (!total) return Array.from({ length: len }, (_, i) => ({ t: i, v: 0 }));
  const avg = total / len;
  return Array.from({ length: len }, (_, i) => ({ t: i, v: Math.round(avg) }));
}

const LVL_COLOR: Record<string, string> = {
  ERROR: "text-red-400",
  WARN: "text-amber-400",
  INFO: "text-slate-300",
  DEBUG: "text-slate-600",
};

interface Log { time: string; level: string; msg: string; raw: string }

export default function Dashboard() {
  const { getHeaders, apiBaseUrl, apiKey, totpCode, logout } = useAuth();
  const [, setLocation] = useLocation();

  const { data: stats, isLoading, error, refetch } = useGetDashboardStats({ request: { headers: getHeaders() } });

  useEffect(() => {
    const i = setInterval(() => refetch(), 30000);
    return () => clearInterval(i);
  }, [refetch]);

  const [logs, setLogs] = useState<Log[]>([]);
  const [logFilter, setLogFilter] = useState("ALL");
  const [expanded, setExpanded] = useState(false);
  const [connected, setConnected] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const evsRef = useRef<EventSource | null>(null);

  const addLog = useCallback((time: string, level: string, msg: string) => {
    setLogs(p => [...p, { time, level, msg, raw: `[${time}][${level}] ${msg}` }].slice(-500));
  }, []);

  useEffect(() => {
    if (!apiBaseUrl || !apiKey || !totpCode) return;
    evsRef.current?.close();
    try {
      const url = new URL("/api/logs/stream", apiBaseUrl.startsWith("http") ? apiBaseUrl : window.location.origin);
      url.searchParams.set("x-api-key", apiKey);
      url.searchParams.set("x-totp-code", totpCode);
      const sse = new EventSource(url.toString());
      evsRef.current = sse;
      sse.onopen = () => { setConnected(true); addLog(format(new Date(), "HH:mm:ss"), "INFO", "Stream connected"); };
      sse.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data);
          addLog(format(new Date(d.timestamp), "HH:mm:ss"), (d.level || "INFO").toUpperCase(), d.message);
        } catch { addLog(format(new Date(), "HH:mm:ss"), "INFO", e.data); }
      };
      sse.onerror = () => { setConnected(false); addLog(format(new Date(), "HH:mm:ss"), "WARN", "Disconnected — reconnects with next TOTP cycle"); sse.close(); };
    } catch {}
    return () => { evsRef.current?.close(); setConnected(false); };
  }, [apiBaseUrl, apiKey, totpCode, addLog]);

  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);

  const exportLogs = () => {
    const blob = new Blob([logs.map(l => l.raw).join("\n")], { type: "text/plain" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `logs_${format(new Date(), "yyyyMMdd_HHmm")}.txt`; a.click();
  };

  const filtered = logFilter === "ALL" ? logs : logs.filter(l => l.level === logFilter);
  const tSparkData = buildSparkline(stats?.tokensToday || 0);
  const vSparkData = buildSparkline(stats?.validToday || 0);

  return (
    <div className="space-y-5">
      {/* Header */}
      <SectionHeader
        title="System Overview"
        sub="Real-time telemetry · Auto-refresh every 30s"
        action={
          <>
            {error && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-[11px]">
                <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                <span className="hidden sm:inline">API error — check Config</span>
                <span className="sm:hidden">API error</span>
              </div>
            )}
            <GlassButton size="sm" variant="secondary" onClick={() => refetch()}>
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
              Sync
            </GlassButton>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors hover:bg-white/8"
                  style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
                  <MoreVertical className="w-4 h-4 text-slate-400" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48" style={{ background: 'rgba(12,12,22,0.97)', border: '1px solid rgba(139,92,246,0.2)' }}>
                <DropdownMenuItem onClick={() => refetch()} className="gap-2 text-slate-300 hover:text-white cursor-pointer">
                  <RefreshCw className="w-3.5 h-3.5" /> Refresh Stats
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => { navigator.clipboard.writeText(apiBaseUrl); }} className="gap-2 text-slate-300 hover:text-white cursor-pointer">
                  <Copy className="w-3.5 h-3.5" /> Copy API URL
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setLocation("/settings")} className="gap-2 text-slate-300 hover:text-white cursor-pointer">
                  <Settings className="w-3.5 h-3.5" /> Settings
                </DropdownMenuItem>
                <DropdownMenuSeparator style={{ background: 'rgba(139,92,246,0.15)' }} />
                <DropdownMenuItem onClick={() => { logout(); setLocation("/login"); }} className="gap-2 text-red-400 hover:text-red-300 cursor-pointer">
                  <LogOut className="w-3.5 h-3.5" /> Logout
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      />

      {/* 8 stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard title="Active Workers" value={`${stats?.activeWorkers ?? "—"}/${stats?.totalWorkers ?? "—"}`} icon={Users} color="violet" sub="nodes online" />
        <StatCard title="Tokens Today" value={stats?.tokensToday ?? "—"} icon={Activity} color="cyan" sub="this session" />
        <StatCard title="Valid Today" value={stats?.validToday ?? "—"} icon={CheckCircle2} color="green" />
        <StatCard
          title="Unlock Rate"
          value={`${stats?.unlockRateToday ?? "—"}%`}
          icon={TrendingUp}
          color={Number(stats?.unlockRateToday) >= 50 ? "green" : "red"}
          sub="today's efficiency"
        />
        <StatCard title="Total DB Tokens" value={stats?.totalTokens ?? "—"} icon={Zap} color="violet" />
        <StatCard title="Total Valid" value={stats?.validTokens ?? "—"} icon={Key} color="green" />
        <StatCard title="Total Locked" value={stats?.lockedTokens ?? "—"} icon={Lock} color="gold" />
        <StatCard title="Total Invalid" value={stats?.invalidTokens ?? "—"} icon={XCircle} color="red" />
      </div>

      {/* Mini trend charts */}
      <div className="grid grid-cols-2 gap-3">
        {[
          { label: "Tokens Generated Today", data: tSparkData, color: "#06b6d4", gradId: "g1", gradColor: "rgba(6,182,212," },
          { label: "Valid Tokens Today", data: vSparkData, color: "#10b981", gradId: "g2", gradColor: "rgba(16,185,129," },
        ].map(({ label, data, color, gradId, gradColor }) => (
          <GlassCard key={label} className="p-4">
            <div className="text-xs text-slate-500 mb-2">{label}</div>
            <div className="h-16">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={color} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={color} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <Area type="monotone" dataKey="v" stroke={color} fill={`url(#${gradId})`} strokeWidth={1.5} dot={false} />
                  <Tooltip formatter={(v: number) => [v, "tokens"]} labelFormatter={() => ""} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Terminal */}
      <GlassCard className={`flex flex-col transition-all duration-300 ${expanded ? "fixed inset-4 z-50" : "h-64"}`}>
        {/* Terminal header bar */}
        <div className="flex-shrink-0 flex items-center gap-3 px-4 py-2.5 border-b border-white/6">
          <div className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-red-500"}`} />
            <TerminalIcon className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-xs font-mono text-slate-400">LIVE LOG STREAM</span>
          </div>
          {/* Level filters */}
          <div className="flex items-center gap-1 ml-2">
            {["ALL","INFO","WARN","ERROR"].map(l => (
              <button
                key={l}
                onClick={() => setLogFilter(l)}
                className={`text-[10px] font-medium px-2 py-0.5 rounded transition-colors ${
                  logFilter === l
                    ? l === "ERROR" ? "bg-red-500/20 text-red-400" : l === "WARN" ? "bg-amber-500/20 text-amber-400" : "bg-violet-500/20 text-violet-400"
                    : "text-slate-600 hover:text-slate-400"
                }`}
              >
                {l}
              </button>
            ))}
          </div>
          <div className="flex-1" />
          <button onClick={exportLogs} className="text-[10px] text-slate-600 hover:text-slate-400 flex items-center gap-1"><Download className="w-3 h-3" />Export</button>
          <button onClick={() => setLogs([])} className="text-[10px] text-slate-600 hover:text-red-400 flex items-center gap-1"><Trash2 className="w-3 h-3" />Clear</button>
          <button onClick={() => setExpanded(v => !v)} className="text-slate-600 hover:text-slate-300">
            {expanded ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
        {/* Log body */}
        <div className="flex-1 p-3 overflow-y-auto font-mono text-[11px] scanline" style={{ background: 'rgba(4,4,10,0.8)' }}>
          {filtered.length === 0 && <div className="text-slate-700 blink">Awaiting stream</div>}
          {filtered.map((log, i) => (
            <div key={i} className="flex gap-2 mb-0.5 leading-relaxed">
              <span className="text-slate-700 flex-shrink-0">[{log.time}]</span>
              <span className={`flex-shrink-0 w-10 ${LVL_COLOR[log.level] || "text-slate-500"}`}>[{log.level.slice(0,4)}]</span>
              <span className={LVL_COLOR[log.level] || "text-slate-400"}>{log.msg}</span>
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      </GlassCard>
    </div>
  );
}
