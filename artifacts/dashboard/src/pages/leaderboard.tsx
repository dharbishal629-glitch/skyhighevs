import React from "react";
import { useAuth } from "@/lib/auth-context";
import { GlassCard, ProgressBar, SectionHeader } from "@/components/ui/cyber-components";
import { useGetLeaderboard } from "@/lib/api-client";
import { Trophy, Target, Crosshair, Zap } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/components/ui/cyber-components";

export default function Leaderboard() {
  const { getHeaders } = useAuth();
  const { data, isLoading, isError } = useGetLeaderboard({ request: { headers: getHeaders() } });
  const board = data?.leaderboard || [];
  const topTotal = board[0]?.totalGenerated || 1;

  const medals = [
    { emoji: "🥇", bg: "rgba(251,191,36,0.08)", border: "rgba(251,191,36,0.25)", num: "text-amber-400" },
    { emoji: "🥈", bg: "rgba(203,213,225,0.06)", border: "rgba(203,213,225,0.18)", num: "text-slate-400" },
    { emoji: "🥉", bg: "rgba(180,83,9,0.08)",   border: "rgba(180,83,9,0.25)",    num: "text-amber-700" },
  ];

  return (
    <div className="space-y-5 max-w-3xl mx-auto">
      <div className="text-center py-2">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-500/20 to-amber-600/10 border border-amber-500/25 mb-3 glow-gold">
          <Trophy className="w-7 h-7 text-amber-400" />
        </div>
        <h2 className="text-2xl font-display font-bold text-slate-100">Leaderboard</h2>
        <p className="text-sm text-slate-500 mt-1">Workers ranked by total generation & efficiency</p>
      </div>

      {isError ? (
        <GlassCard className="p-6 text-center border-red-500/30 bg-red-500/5">
          <p className="text-red-400 font-sans text-sm font-medium">Failed to load leaderboard — check your API URL, Worker Key, and TOTP Secret in Settings.</p>
        </GlassCard>
      ) : isLoading ? (
        <div className="text-center text-slate-600 animate-pulse py-12 font-sans">Calculating rankings...</div>
      ) : board.length === 0 ? (
        <GlassCard className="p-12 text-center text-slate-600 border-dashed">No generation data yet.</GlassCard>
      ) : (
        <div className="space-y-2">
          {board.map((entry, idx) => {
            const m = idx < 3 ? medals[idx] : null;
            const barPct = (entry.totalGenerated / topTotal) * 100;
            return (
              <motion.div
                key={entry.discordId}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.06, duration: 0.28 }}
              >
                <GlassCard
                  className="overflow-hidden relative"
                  style={m ? { background: m.bg, borderColor: m.border } : {}}
                >
                  {/* Background progress fill */}
                  <div
                    className="absolute inset-y-0 left-0 opacity-30 transition-all duration-1000"
                    style={{ width: `${barPct}%`, background: m ? `rgba(251,191,36,0.12)` : `rgba(139,92,246,0.08)` }}
                  />
                  <div className="relative flex items-center gap-4 px-5 py-4">
                    {/* Rank */}
                    <div className="flex-shrink-0 w-10 text-center">
                      {m ? (
                        <span className="text-2xl">{m.emoji}</span>
                      ) : (
                        <span className="text-lg font-display font-bold text-slate-600">#{entry.rank}</span>
                      )}
                    </div>
                    {/* Name */}
                    <div className="flex-1 min-w-0">
                      <div className={cn("font-display font-semibold text-sm uppercase tracking-wide truncate", m ? m.num : "text-slate-200")}>
                        {entry.discordUsername}
                      </div>
                      <div className="text-[10px] text-slate-600">ID: {entry.discordId}</div>
                    </div>
                    {/* Stats */}
                    <div className="flex items-center gap-5 font-sans text-xs">
                      <div className="text-center hidden sm:block">
                        <div className="text-slate-600 flex items-center gap-1 justify-center mb-0.5"><Crosshair className="w-2.5 h-2.5" />Total</div>
                        <div className="font-semibold text-slate-200">{entry.totalGenerated.toLocaleString()}</div>
                      </div>
                      <div className="text-center hidden sm:block">
                        <div className="text-slate-600 flex items-center gap-1 justify-center mb-0.5"><Target className="w-2.5 h-2.5" />Valid</div>
                        <div className="font-semibold text-emerald-400">{entry.totalValid.toLocaleString()}</div>
                      </div>
                      <div className="text-center w-20">
                        <div className="text-slate-600 flex items-center gap-1 justify-center mb-0.5"><Zap className="w-2.5 h-2.5" />Rate</div>
                        <div className={cn("text-lg font-display font-bold", entry.unlockRate >= 50 ? "text-emerald-400" : "text-red-400")}>{entry.unlockRate}%</div>
                        <div className="mt-1"><ProgressBar value={entry.unlockRate} color={entry.unlockRate >= 50 ? "green" : "red"} /></div>
                      </div>
                    </div>
                  </div>
                </GlassCard>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
