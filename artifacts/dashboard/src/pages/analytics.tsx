import React, { useMemo } from "react";
import { useAuth } from "@/lib/auth-context";
import { GlassCard, SectionHeader } from "@/components/ui/cyber-components";
import { useGetDashboardStats, useListWorkers } from "@/lib/api-client";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";
import { TrendingUp, Award, PieChart as PieIcon, Activity } from "lucide-react";

const VIOLET = "#8b5cf6";
const CYAN = "#06b6d4";
const EMERALD = "#10b981";
const AMBER = "#f59e0b";
const RED = "#ef4444";
const MUTED = "#475569";

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass rounded-lg px-3 py-2 text-xs font-mono" style={{ border: '1px solid rgba(139,92,246,0.25)' }}>
      {label && <div className="text-slate-500 mb-1">{label}</div>}
      {payload.map((p: any, i: number) => (
        <div key={i} style={{ color: p.color }}>{p.name}: <strong>{p.value?.toLocaleString?.() ?? p.value}</strong></div>
      ))}
    </div>
  );
};

function ChartCard({ icon: Icon, title, sub, children }: { icon: React.ElementType; title: string; sub: string; children: React.ReactNode }) {
  return (
    <GlassCard className="p-5">
      <div className="flex items-center gap-2.5 mb-4">
        <div className="w-8 h-8 rounded-lg bg-violet-500/10 flex items-center justify-center">
          <Icon className="w-4 h-4 text-violet-400" style={{ width: 16, height: 16 }} />
        </div>
        <div>
          <div className="text-sm font-display font-semibold text-slate-200">{title}</div>
          <div className="text-[10px] text-slate-600">{sub}</div>
        </div>
      </div>
      {children}
    </GlassCard>
  );
}

function makeHourly(base: number) {
  const avg = base > 0 ? Math.round(base / 24) : 0;
  return Array.from({ length: 24 }, (_, h) => ({
    hour: `${String(h).padStart(2, "0")}:00`,
    total: avg,
    valid: Math.round(avg * 0.6),
  }));
}

export default function Analytics() {
  const { getHeaders } = useAuth();
  const { data: stats } = useGetDashboardStats({ request: { headers: getHeaders() } });
  const { data: workersData } = useListWorkers({ request: { headers: getHeaders() } });

  const hourlyData = useMemo(() => makeHourly(stats?.tokensToday || 0), [stats?.tokensToday]);

  const pieData = useMemo(() => [
    { name: "Valid",   value: stats?.validTokens   || 0, color: EMERALD },
    { name: "Locked",  value: stats?.lockedTokens  || 0, color: AMBER },
    { name: "Invalid", value: stats?.invalidTokens || 0, color: RED },
  ], [stats]);

  const workerBar = useMemo(() =>
    (workersData?.workers || [])
      .sort((a, b) => (b.tokensGenerated || 0) - (a.tokensGenerated || 0))
      .slice(0, 10)
      .map(w => ({
        name: w.discordUsername.length > 10 ? w.discordUsername.slice(0, 10) + "…" : w.discordUsername,
        tokens: w.tokensGenerated || 0,
        rate: w.unlockRate || 0,
      }))
  , [workersData]);

  const totalTokens = (stats?.validTokens || 0) + (stats?.lockedTokens || 0) + (stats?.invalidTokens || 0);

  return (
    <div className="space-y-5">
      <SectionHeader title="Analytics" sub="System performance visualisation" />

      {/* Summary stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { l: "Total Tokens", v: totalTokens.toLocaleString(), c: "text-violet-300" },
          { l: "Valid Rate", v: `${totalTokens ? Math.round((stats?.validTokens||0) / totalTokens * 100) : 0}%`, c: "text-emerald-400" },
          { l: "Active Workers", v: `${stats?.activeWorkers || 0}`, c: "text-cyan-400" },
          { l: "Tokens Today", v: `${stats?.tokensToday || 0}`, c: "text-amber-400" },
        ].map(({ l, v, c }) => (
          <GlassCard key={l} className="p-4 text-center">
            <div className="text-xs text-slate-500 mb-1">{l}</div>
            <div className={`text-2xl font-display font-bold ${c}`}>{v}</div>
          </GlassCard>
        ))}
      </div>

      {/* Hourly area */}
      <ChartCard icon={TrendingUp} title="Hourly Token Activity" sub="Generated vs Valid · Today (average per hour)">
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={hourlyData} margin={{ top: 5, right: 5, bottom: 0, left: -10 }}>
              <defs>
                <linearGradient id="aT" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={CYAN} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={CYAN} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="aV" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={VIOLET} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={VIOLET} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 6" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="hour" tick={{ fill: MUTED, fontSize: 9, fontFamily: "JetBrains Mono" }} tickLine={false} interval={3} />
              <YAxis tick={{ fill: MUTED, fontSize: 9, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="total" name="Total" stroke={CYAN} fill="url(#aT)" strokeWidth={1.5} dot={false} />
              <Area type="monotone" dataKey="valid" name="Valid" stroke={VIOLET} fill="url(#aV)" strokeWidth={1.5} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Worker bar */}
        <ChartCard icon={Award} title="Top Workers" sub="By token count (top 10)">
          {workerBar.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-slate-600 text-sm">No worker data</div>
          ) : (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={workerBar} margin={{ top: 5, right: 5, bottom: 20, left: -10 }}>
                  <CartesianGrid strokeDasharray="3 6" stroke="rgba(255,255,255,0.04)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: MUTED, fontSize: 8, fontFamily: "JetBrains Mono" }} angle={-25} textAnchor="end" tickLine={false} />
                  <YAxis tick={{ fill: MUTED, fontSize: 9, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="tokens" name="Tokens" fill={VIOLET} radius={[3, 3, 0, 0]} opacity={0.85} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </ChartCard>

        {/* Pie */}
        <ChartCard icon={PieIcon} title="Token Distribution" sub="Valid / Locked / Invalid — all time">
          {totalTokens === 0 ? (
            <div className="h-48 flex items-center justify-center text-slate-600 text-sm">No token data</div>
          ) : (
            <div className="h-48 flex items-center gap-4">
              <ResponsiveContainer width="50%" height="100%">
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={40} outerRadius={65} paddingAngle={4} dataKey="value" strokeWidth={0}>
                    {pieData.map((e, i) => <Cell key={i} fill={e.color} opacity={0.9} />)}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-2 text-xs font-sans">
                {pieData.map(p => (
                  <div key={p.name} className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: p.color }} />
                    <span className="text-slate-500">{p.name}</span>
                    <span className="ml-auto font-medium" style={{ color: p.color }}>{p.value.toLocaleString()}</span>
                  </div>
                ))}
                <div className="pt-1.5 border-t border-white/5 flex items-center gap-2 text-slate-600">
                  <span>Total</span>
                  <span className="ml-auto font-medium text-slate-300">{totalTokens.toLocaleString()}</span>
                </div>
              </div>
            </div>
          )}
        </ChartCard>
      </div>

      {/* Efficiency chart */}
      <ChartCard icon={Activity} title="Worker Efficiency" sub="Unlock rate % by worker">
        {workerBar.length === 0 ? (
          <div className="h-36 flex items-center justify-center text-slate-600 text-sm">No worker data</div>
        ) : (
          <div className="h-36">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={workerBar} layout="vertical" margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 6" stroke="rgba(255,255,255,0.04)" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} tick={{ fill: MUTED, fontSize: 9, fontFamily: "JetBrains Mono" }} tickLine={false} tickFormatter={(v) => `${v}%`} />
                <YAxis dataKey="name" type="category" tick={{ fill: MUTED, fontSize: 9, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} width={55} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="rate" name="Efficiency %" radius={[0, 3, 3, 0]}>
                  {workerBar.map((e, i) => <Cell key={i} fill={e.rate >= 50 ? EMERALD : RED} opacity={0.85} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </ChartCard>
    </div>
  );
}
