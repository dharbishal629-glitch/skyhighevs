import React from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ── Glass Card ────────────────────────────────────────────
interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  glow?: "violet" | "gold" | "cyan" | "red" | "green" | "none";
  lift?: boolean;
  gradient?: boolean;
}

export function GlassCard({ className, children, glow = "none", lift = false, gradient = false, ...props }: GlassCardProps) {
  const glowMap = {
    violet: "glow-violet",
    gold: "glow-gold",
    cyan: "glow-cyan",
    red: "glow-red",
    green: "glow-green",
    none: "",
  };
  return (
    <div
      className={cn(
        "glass rounded-xl overflow-hidden relative",
        glowMap[glow],
        lift && "card-3d",
        gradient && "grad-border",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

// Legacy alias
export const CyberCard = GlassCard;

// ── Button ──────────────────────────────────────────────
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "gold" | "danger" | "ghost" | "outline";
  size?: "xs" | "sm" | "md" | "lg";
}

export function GlassButton({ className, variant = "primary", size = "md", children, ...props }: ButtonProps) {
  const base = "btn-3d relative inline-flex items-center justify-center font-semibold rounded-lg transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed select-none overflow-hidden";

  const variants = {
    primary:   "bg-gradient-to-b from-violet-500/30 to-violet-700/20 text-violet-200 border border-violet-500/40 hover:from-violet-500/40 hover:to-violet-700/30 hover:border-violet-400/70",
    secondary: "bg-gradient-to-b from-white/10 to-white/4 text-slate-300 border border-white/12 hover:from-white/15 hover:to-white/8 hover:border-white/22",
    gold:      "bg-gradient-to-b from-amber-400/25 to-amber-600/15 text-amber-200 border border-amber-400/40 hover:from-amber-400/35 hover:to-amber-600/25 hover:border-amber-400/70",
    danger:    "bg-gradient-to-b from-red-500/25 to-red-700/15 text-red-200 border border-red-500/40 hover:from-red-500/35 hover:to-red-700/25 hover:border-red-400/70",
    ghost:     "bg-transparent text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent",
    outline:   "bg-gradient-to-b from-white/6 to-transparent text-slate-300 border border-white/12 hover:border-violet-400/50 hover:text-violet-300",
  };

  const sizes = {
    xs: "px-2.5 py-1 text-xs gap-1",
    sm: "px-3 py-1.5 text-xs gap-1.5",
    md: "px-4 py-2 text-sm gap-2",
    lg: "px-6 py-3 text-sm gap-2",
  };

  return (
    <button className={cn(base, variants[variant], sizes[size], className)} {...props}>
      {children}
    </button>
  );
}

export const CyberButton = GlassButton;

// ── Input ──────────────────────────────────────────────
export function GlassInput({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full bg-white/4 border border-white/10 rounded-lg text-slate-200 font-sans text-sm px-3 py-2",
        "focus:outline-none focus:border-violet-500/50 focus:bg-violet-500/5 transition-all",
        "placeholder:text-slate-600",
        className
      )}
      {...props}
    />
  );
}

export const CyberInput = GlassInput;

// ── Textarea ──────────────────────────────────────────────
export function GlassTextarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full bg-white/4 border border-white/10 rounded-lg text-slate-200 font-sans text-sm px-3 py-2 resize-none",
        "focus:outline-none focus:border-violet-500/50 transition-all",
        "placeholder:text-slate-600",
        className
      )}
      {...props}
    />
  );
}

export const CyberTextarea = GlassTextarea;

// ── Select ────────────────────────────────────────────────
export function GlassSelect({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "bg-white/4 border border-white/10 rounded-lg text-slate-200 font-sans text-sm px-3 py-2",
        "focus:outline-none focus:border-violet-500/50 transition-all cursor-pointer",
        className
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export const CyberSelect = GlassSelect;

// ── Badge ─────────────────────────────────────────────────
export function Badge({ children, variant = "valid" }: { children: React.ReactNode; variant?: "valid" | "locked" | "expired" | "neutral" | "accent" | "danger" }) {
  const variants = {
    valid: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/25",
    locked: "bg-red-500/15 text-red-400 border border-red-500/25",
    expired: "bg-amber-500/15 text-amber-400 border border-amber-500/25",
    neutral: "bg-slate-500/15 text-slate-400 border border-slate-500/25",
    accent: "bg-violet-500/15 text-violet-400 border border-violet-500/25",
    danger: "bg-red-500/15 text-red-400 border border-red-500/25",
  };
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium rounded-md", variants[variant])}>
      {children}
    </span>
  );
}

export const CyberBadge = Badge;

// ── Progress bar ─────────────────────────────────────────
export function ProgressBar({ value, max = 100, color = "violet" }: { value: number; max?: number; color?: "violet" | "gold" | "cyan" | "red" | "green" }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const colors = {
    violet: "bg-gradient-to-r from-violet-600 to-violet-400",
    gold: "bg-gradient-to-r from-amber-600 to-amber-400",
    cyan: "bg-gradient-to-r from-cyan-600 to-cyan-400",
    red: "bg-gradient-to-r from-red-600 to-red-400",
    green: "bg-gradient-to-r from-emerald-600 to-emerald-400",
  };
  return (
    <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
      <div className={cn("h-full rounded-full bar-fill", colors[color])} style={{ width: `${pct}%` }} />
    </div>
  );
}

export const CyberProgress = ProgressBar;

// ── Stat Card ─────────────────────────────────────────────
export function StatCard({
  title, value, sub, icon: Icon, color = "violet", trend,
}: {
  title: string; value: string | number; sub?: string; icon: React.ElementType;
  color?: "violet" | "gold" | "cyan" | "red" | "green"; trend?: number;
}) {
  const palettes = {
    violet: { bg: "bg-violet-500/10", icon: "text-violet-400", val: "text-grad-violet", glow: "violet" as const, ring: "border-violet-500/20" },
    gold:   { bg: "bg-amber-500/10",  icon: "text-amber-400",  val: "text-grad-gold",   glow: "gold"   as const, ring: "border-amber-500/20" },
    cyan:   { bg: "bg-cyan-500/10",   icon: "text-cyan-400",   val: "text-grad-cyan",   glow: "cyan"   as const, ring: "border-cyan-500/20" },
    red:    { bg: "bg-red-500/10",    icon: "text-red-400",    val: "text-red-300",     glow: "red"    as const, ring: "border-red-500/20" },
    green:  { bg: "bg-emerald-500/10",icon: "text-emerald-400",val: "text-emerald-300", glow: "green"  as const, ring: "border-emerald-500/20" },
  };
  const p = palettes[color];

  return (
    <GlassCard glow={p.glow} lift className={cn("p-4 border", p.ring)}>
      <div className="flex items-start justify-between mb-3">
        <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center", p.bg)}>
          <Icon className={cn("w-4.5 h-4.5", p.icon)} style={{ width: 18, height: 18 }} />
        </div>
        {trend !== undefined && (
          <span className={cn("text-xs font-medium", trend >= 0 ? "text-emerald-400" : "text-red-400")}>
            {trend >= 0 ? "↑" : "↓"}{Math.abs(trend)}%
          </span>
        )}
      </div>
      <div className={cn("text-2xl font-display font-bold leading-none mb-1 stat-value", p.val)}>{value}</div>
      <div className="text-xs text-slate-500 font-sans">{title}</div>
      {sub && <div className="text-[10px] text-slate-600 mt-0.5">{sub}</div>}
    </GlassCard>
  );
}

// ── Section Header ────────────────────────────────────────
export function SectionHeader({
  title, sub, subtitle, hint, action, icon,
}: {
  title: string | React.ReactNode;
  sub?: string | React.ReactNode;
  subtitle?: string | React.ReactNode;
  hint?: string | React.ReactNode;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  const subText = sub ?? subtitle ?? hint;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
      <div className="min-w-0">
        <h2 className="text-base font-display font-semibold text-slate-100 leading-tight flex items-center gap-2">
          {icon && <span className="flex-shrink-0">{icon}</span>}
          {title}
        </h2>
        {subText && <p className="text-xs text-slate-500 mt-0.5">{subText}</p>}
      </div>
      {action && <div className="flex items-center gap-2 flex-wrap">{action}</div>}
    </div>
  );
}

// ── Divider ───────────────────────────────────────────────
export function Divider({ className }: { className?: string }) {
  return <div className={cn("h-px bg-gradient-to-r from-transparent via-violet-500/20 to-transparent my-4", className)} />;
}
