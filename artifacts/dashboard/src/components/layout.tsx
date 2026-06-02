import React, { memo, useEffect, useRef, useState } from "react";
import { Link, useLocation } from "wouter";
import { useAuth, useTotpTimer } from "@/lib/auth-context";
import {
  LayoutDashboard, Users, Key, Trophy, BarChart2, Settings, Settings2,
  Menu, X, Shield, ChevronRight, Clock, Copy, Check, ShieldCheck, Terminal,
} from "lucide-react";
import { cn } from "./ui/cyber-components";
import { motion, AnimatePresence } from "framer-motion";
import { format } from "date-fns";

const navItems = [
  { href: "/",            label: "Overview",    sub: "System stats",     icon: LayoutDashboard, color: "text-violet-400" },
  { href: "/workers",     label: "Workers",     sub: "Manage nodes",     icon: Users,           color: "text-blue-400" },
  { href: "/tokens",      label: "Tokens",      sub: "Data explorer",    icon: Key,             color: "text-cyan-400" },
  { href: "/leaderboard", label: "Leaderboard", sub: "Top performers",   icon: Trophy,          color: "text-amber-400" },
  { href: "/analytics",   label: "Analytics",   sub: "Charts & trends",  icon: BarChart2,       color: "text-emerald-400" },
  { href: "/tool-config", label: "Tool Config", sub: "Worker settings",  icon: Settings2,       color: "text-amber-400" },
  { href: "/tool-file",    label: "Tool File",    sub: "Secure launcher",   icon: ShieldCheck, color: "text-violet-400" },
  { href: "/environment",  label: "Environment",  sub: "Env vars & URLs",   icon: Terminal,    color: "text-emerald-400" },
  { href: "/settings",     label: "API Config",   sub: "Keys & server",     icon: Settings,    color: "text-slate-400" },
];

/* ─────────────────────────────────────────────────────────────────────────
   NavbarStatus — isolated component that ticks every second.
   Lives entirely on its own; re-renders here do NOT propagate to siblings.
───────────────────────────────────────────────────────────────────────── */
const NavbarStatus = memo(function NavbarStatus({ apiBaseUrl }: { apiBaseUrl: string }) {
  const { totpCode, autoTotpEnabled } = useAuth();
  const timeLeft = useTotpTimer();
  const [now, setNow]     = useState(new Date());
  const [online, setOnline] = useState(true);
  const [copied, setCopied] = useState(false);

  // Clock — runs every second, isolated here
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const copyTotp = () => {
    if (!totpCode) return;
    navigator.clipboard.writeText(totpCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  // API health check every 30s
  useEffect(() => {
    let tid: ReturnType<typeof setTimeout>;
    const check = async () => {
      try {
        const r = await fetch(`${apiBaseUrl}/api/healthz`);
        setOnline(r.ok || r.status !== 0);
      } catch { setOnline(false); }
      tid = setTimeout(check, 30000);
    };
    check();
    return () => clearTimeout(tid);
  }, [apiBaseUrl]);

  return (
    <>
      {/* TOTP indicator */}
      {autoTotpEnabled && (
        <button
          onClick={copyTotp}
          title="Click to copy 2FA code"
          className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg group transition-all hover:border-violet-500/30"
          style={{ background: 'rgba(139,92,246,0.08)', border: '1px solid rgba(139,92,246,0.15)' }}
        >
          <Shield className="w-3.5 h-3.5 text-violet-400" />
          <span className="font-mono text-sm font-medium text-violet-300 tracking-[0.3em]">
            {totpCode || "——————"}
          </span>
          {copied
            ? <Check className="w-3.5 h-3.5 text-emerald-400" />
            : <Copy className="w-3 h-3 text-slate-600 group-hover:text-violet-400 transition-colors" />}
          <div className="relative w-5 h-5 flex-shrink-0">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 20 20">
              <circle cx="10" cy="10" r="8" fill="none" stroke="rgba(139,92,246,0.18)" strokeWidth="2" />
              <circle
                cx="10" cy="10" r="8" fill="none"
                stroke={timeLeft <= 5 ? "#ef4444" : "#8b5cf6"}
                strokeWidth="2"
                strokeDasharray="50.3"
                strokeDashoffset={50.3 - (timeLeft / 30) * 50.3}
                style={{ transition: 'stroke-dashoffset 1s linear, stroke 0.3s' }}
              />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-[8px] font-mono text-slate-400">{timeLeft}</span>
          </div>
        </button>
      )}

      {/* Online status */}
      <div className={cn(
        "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium",
        online
          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
          : "bg-red-500/10 text-red-400 border border-red-500/20"
      )}>
        <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", online ? "bg-emerald-400 animate-pulse" : "bg-red-400")} />
        <span className="hidden sm:inline">{online ? "Live" : "Down"}</span>
      </div>

      {/* Clock */}
      <div className="hidden lg:flex items-center gap-1 text-xs text-slate-500">
        <Clock className="w-3 h-3" />
        {format(now, "HH:mm:ss")}
      </div>
    </>
  );
});

/* ─────────────────────────────────────────────────────────────────────────
   DrawerTOTP — isolated TOTP panel inside the nav drawer
───────────────────────────────────────────────────────────────────────── */
const DrawerTOTP = memo(function DrawerTOTP({ online }: { online?: boolean }) {
  const { totpCode, autoTotpEnabled } = useAuth();
  const timeLeft = useTotpTimer();
  const [copied, setCopied] = useState(false);

  const copy = () => {
    if (!totpCode) return;
    navigator.clipboard.writeText(totpCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div className="m-4 p-4 rounded-xl" style={{ background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.15)' }}>
      <div className="flex items-center gap-2 mb-3">
        <Shield className="w-3.5 h-3.5 text-violet-400" />
        <span className="text-xs font-medium text-slate-300">2FA Code</span>
        {autoTotpEnabled && (
          <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">AUTO</span>
        )}
      </div>
      {autoTotpEnabled ? (
        <div className="text-center py-1">
          <button
            type="button"
            onClick={copy}
            title="Click to copy"
            className="inline-flex items-center gap-2 group cursor-pointer"
          >
            <div className="text-2xl font-mono font-bold text-violet-300 tracking-[0.5em]">{totpCode || "······"}</div>
            {copied
              ? <Check className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              : <Copy className="w-3.5 h-3.5 text-slate-600 group-hover:text-violet-400 transition-colors flex-shrink-0" />}
          </button>
          <div className="text-[10px] text-slate-500 mt-1">Refreshes in {timeLeft}s</div>
          <div className="w-full h-1 bg-white/5 rounded-full mt-2 overflow-hidden">
            <div className="h-full rounded-full"
              style={{
                width: `${(timeLeft / 30) * 100}%`,
                background: timeLeft <= 5 ? '#ef4444' : 'linear-gradient(to right, #8b5cf6, #a78bfa)',
                transition: 'width 1s linear, background 0.3s',
              }} />
          </div>
        </div>
      ) : (
        <Link href="/config">
          <div className="text-center py-2 text-[11px] text-amber-400/70 hover:text-amber-400 cursor-pointer transition-colors">
            ⚙ Set TOTP Secret in Config
          </div>
        </Link>
      )}
    </div>
  );
});

/* ─────────────────────────────────────────────────────────────────────────
   PageContent — wraps children; memoised so parent re-renders never
   trickle into the page (only actual prop/context changes will).
───────────────────────────────────────────────────────────────────────── */
const PageContent = memo(function PageContent({ children, location }: { children: React.ReactNode; location: string }) {
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.18 }}
        className="relative z-10 p-4 md:p-6 max-w-[1400px] mx-auto"
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
});

/* ─────────────────────────────────────────────────────────────────────────
   Layout — stable shell; no per-second state here.
───────────────────────────────────────────────────────────────────────── */
export function Layout({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();
  const { apiBaseUrl, logout } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const mainRef = useRef<HTMLElement>(null);

  const currentPage = navItems.find(n => n.href === location);

  // Close drawer and scroll to top on route change — stable, no interval
  useEffect(() => {
    setDrawerOpen(false);
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [location]);

  return (
    <div className="flex flex-col w-screen overflow-hidden" style={{ height: '100dvh' }}>

      {/* ── TOP NAVBAR ── */}
      <header className="navbar-3d flex-shrink-0 h-14 flex items-center px-4 gap-3 relative z-30">

        {/* Logo */}
        <div className="flex items-center gap-2.5 mr-2">
          <img src="/logo.svg" alt="CTRL.PNL" className="w-8 h-8 flex-shrink-0" style={{ filter: 'drop-shadow(0 0 6px rgba(139,92,246,0.5))' }} />
          <div className="hidden sm:block">
            <div className="text-sm font-bold text-white leading-none tracking-wide">CTRL.PNL</div>
            <div className="text-[9px] text-slate-500 leading-none mt-0.5 font-mono">v2.0</div>
          </div>
        </div>

        {/* Breadcrumb */}
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {currentPage && (
            <>
              <currentPage.icon className={cn("w-4 h-4 flex-shrink-0", currentPage.color)} />
              <span className="text-sm font-medium text-slate-200 truncate">{currentPage.label}</span>
            </>
          )}
        </div>

        {/* Right side — isolated, ticks every second without touching the rest */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <NavbarStatus apiBaseUrl={apiBaseUrl} />

          {/* Hamburger */}
          <button
            onClick={() => setDrawerOpen(v => !v)}
            className="w-9 h-9 rounded-lg flex items-center justify-center transition-colors hover:bg-white/8"
            style={{ border: '1px solid rgba(255,255,255,0.08)' }}
          >
            {drawerOpen
              ? <X style={{ width: 18, height: 18 }} className="text-slate-300" />
              : <Menu style={{ width: 18, height: 18 }} className="text-slate-300" />}
          </button>
        </div>
      </header>

      {/* ── DRAWER OVERLAY ── */}
      <AnimatePresence>
        {drawerOpen && (
          <motion.div
            key="overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/55 backdrop-blur-sm"
            onClick={() => setDrawerOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* ── NAV DRAWER ── */}
      <AnimatePresence>
        {drawerOpen && (
          <motion.aside
            key="drawer"
            initial={{ x: "-100%" }}
            animate={{ x: 0 }}
            exit={{ x: "-100%" }}
            transition={{ type: "spring", damping: 28, stiffness: 280 }}
            className="drawer-3d fixed left-0 top-14 bottom-0 w-72 z-50 flex flex-col overflow-y-auto"
          >
            <nav className="flex-1 p-4 space-y-1">
              <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest px-3 mb-2">Navigation</p>
              {navItems.map((item) => {
                const isActive = location === item.href;
                return (
                  <Link key={item.href} href={item.href}>
                    <div className={cn(
                      "flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all cursor-pointer group",
                      isActive
                        ? "nav-item-active"
                        : "hover:bg-white/5 border border-transparent hover:border-white/8"
                    )}>
                      <div className={cn(
                        "w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors",
                        isActive ? "bg-violet-600/20" : "bg-white/5 group-hover:bg-white/8"
                      )}>
                        <item.icon className={cn("w-4 h-4", isActive ? "text-violet-300" : item.color)} style={{ width: 16, height: 16 }} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className={cn("text-sm font-medium", isActive ? "text-violet-200" : "text-slate-300 group-hover:text-white")}>{item.label}</div>
                        <div className="text-[10px] text-slate-600">{item.sub}</div>
                      </div>
                      {isActive && <ChevronRight className="w-3.5 h-3.5 text-violet-400 flex-shrink-0" />}
                    </div>
                  </Link>
                );
              })}
            </nav>

            {/* Isolated TOTP panel */}
            <DrawerTOTP />

            {/* Logout */}
            <div className="px-4 pb-5">
              <button
                onClick={logout}
                className="w-full py-2 rounded-lg text-xs text-slate-500 hover:text-red-400 hover:bg-red-500/8 transition-all border border-transparent hover:border-red-500/15"
              >
                Sign out
              </button>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* ── MAIN CONTENT ── */}
      <main ref={mainRef} className="flex-1 overflow-y-auto overflow-x-hidden relative">
        <div className="pointer-events-none fixed inset-0 z-0">
          <div className="absolute top-0 right-0 w-80 h-80 rounded-full opacity-8 blur-3xl"
            style={{ background: 'radial-gradient(circle, #8b5cf6, transparent)' }} />
          <div className="absolute bottom-0 left-0 w-64 h-64 rounded-full opacity-6 blur-3xl"
            style={{ background: 'radial-gradient(circle, #06b6d4, transparent)' }} />
        </div>

        <PageContent location={location}>
          {children}
        </PageContent>
      </main>
    </div>
  );
}
