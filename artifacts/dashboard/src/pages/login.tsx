import React, { useState, useEffect } from "react";
import { useAuth, useTotpTimer } from "@/lib/auth-context";
import { Eye, EyeOff, AlertCircle, Loader2, ShieldCheck, Settings, KeyRound } from "lucide-react";
import { useLocation } from "wouter";

export default function Login() {
  const { login, isSetup, totpCode, autoTotpEnabled, config, checkAdminSetup, adminConfigured } = useAuth();
  const totpTimeLeft = useTotpTimer();
  const [, setLocation] = useLocation();

  const [accessCode, setAccessCode] = useState("");
  const [manualCode, setManualCode] = useState("");
  const [showCode, setShowCode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Setup mode: no access code configured yet
  const [setupMode, setSetupMode] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [confirmCode, setConfirmCode] = useState("");
  const [showNewCode, setShowNewCode] = useState(false);
  const [setupLoading, setSetupLoading] = useState(false);
  const [setupError, setSetupError] = useState("");

  useEffect(() => {
    checkAdminSetup();
  }, []);

  useEffect(() => {
    // If DB says no code is configured, show setup form
    setSetupMode(!adminConfigured);
  }, [adminConfigured]);

  const handleConnect = async () => {
    if (!accessCode) { setError("Access code is required."); return; }
    if (!autoTotpEnabled && !manualCode) { setError("Enter your 2FA code."); return; }
    setLoading(true);
    setError("");
    const result = await login(accessCode, autoTotpEnabled ? undefined : manualCode);
    setLoading(false);
    if (!result.success) {
      setError(result.error || "Connection failed.");
    } else {
      setLocation("/");
    }
  };

  const handleSetup = async () => {
    if (!newCode || newCode.length < 4) { setSetupError("Access code must be at least 4 characters."); return; }
    if (newCode !== confirmCode) { setSetupError("Codes don't match."); return; }
    if (!autoTotpEnabled && !manualCode) { setSetupError("Enter your 2FA code to verify."); return; }
    setSetupLoading(true);
    setSetupError("");
    try {
      const baseUrl = config.apiUrl.replace(/\/$/, "");
      const code = autoTotpEnabled ? totpCode : manualCode;
      const res = await fetch(`${baseUrl}/api/admin/setup`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": config.workerKey,
          "x-totp-code": code,
        },
        body: JSON.stringify({ newCode }),
      });
      const data = await res.json();
      if (!res.ok) {
        setSetupError(data.error || `Error: HTTP ${res.status}`);
      } else {
        // Auto-login after setup
        await checkAdminSetup();
        setSetupMode(false);
        setAccessCode(newCode);
        const result = await login(newCode, autoTotpEnabled ? undefined : manualCode);
        if (result.success) setLocation("/");
      }
    } catch {
      setSetupError("Could not reach the API server.");
    }
    setSetupLoading(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") setupMode ? handleSetup() : handleConnect();
  };

  return (
    <div className="min-h-screen bg-[#080c14] flex items-center justify-center p-4">
      <div className="w-full max-w-sm" onKeyDown={handleKeyDown}>

        {/* Logo */}
        <div className="flex items-center gap-3 mb-8">
          <img src="/logo.svg" alt="CTRL.PNL" className="w-9 h-9 flex-shrink-0" style={{ filter: 'drop-shadow(0 0 8px rgba(139,92,246,0.6))' }} />
          <div>
            <div className="text-white font-bold text-lg leading-none tracking-tight">CTRL.PNL</div>
            <div className="text-white/30 text-[11px] font-mono mt-0.5">v2.0 — restricted access</div>
          </div>
        </div>

        {/* Not setup warning */}
        {!isSetup && (
          <div className="mb-4 flex items-start gap-2 bg-amber-500/10 border border-amber-500/20 rounded-xl px-4 py-3 text-amber-300 text-xs">
            <AlertCircle size={13} className="mt-0.5 shrink-0" />
            <span>
              Worker Key &amp; TOTP Secret not configured.{" "}
              <button onClick={() => setLocation("/config")} className="underline font-semibold hover:text-amber-200">
                Go to Config
              </button>{" "}to set them up first.
            </span>
          </div>
        )}

        {setupMode ? (
          /* ── First-time setup ─────────────────────────────────── */
          <div className="bg-white/[0.03] border border-violet-500/20 rounded-xl p-6 flex flex-col gap-5">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <KeyRound size={15} className="text-violet-400" />
                <h1 className="text-white font-semibold text-base">Create Access Code</h1>
              </div>
              <p className="text-white/40 text-xs leading-relaxed">
                No access code is set yet. Create a short code (4+ chars) — you'll use this to log in every time.
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-mono font-semibold tracking-widest text-violet-400/80 uppercase">New Access Code</label>
              <div className="relative">
                <input
                  type={showNewCode ? "text" : "password"}
                  value={newCode}
                  onChange={e => setNewCode(e.target.value)}
                  placeholder="e.g. sky-2049"
                  autoComplete="new-password"
                  className="w-full bg-white/5 border border-white/10 rounded-md px-3 py-2.5 text-sm font-mono text-white placeholder:text-white/20 focus:outline-none focus:border-violet-500/60 transition-all pr-10"
                />
                <button type="button" onClick={() => setShowNewCode(v => !v)} tabIndex={-1}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition-colors">
                  {showNewCode ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-mono font-semibold tracking-widest text-violet-400/80 uppercase">Confirm Code</label>
              <input
                type={showNewCode ? "text" : "password"}
                value={confirmCode}
                onChange={e => setConfirmCode(e.target.value)}
                placeholder="Repeat your code"
                autoComplete="new-password"
                className="w-full bg-white/5 border border-white/10 rounded-md px-3 py-2.5 text-sm font-mono text-white placeholder:text-white/20 focus:outline-none focus:border-violet-500/60 transition-all"
              />
            </div>

            {/* 2FA */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-mono font-semibold tracking-widest text-violet-400/80 uppercase">2FA Code</label>
              {autoTotpEnabled ? (
                <div className="flex items-center gap-3 bg-violet-500/10 border border-violet-500/20 rounded-md px-4 py-2.5">
                  <span className="text-2xl font-mono font-bold text-violet-300 tracking-[0.4em] flex-1">{totpCode || "······"}</span>
                  <div className="flex flex-col items-end gap-1">
                    <span className="text-[10px] text-slate-500">Auto</span>
                    <div className="w-12 h-1 bg-white/5 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-1000"
                        style={{ width: `${(totpTimeLeft / 30) * 100}%`, background: totpTimeLeft <= 5 ? '#ef4444' : 'linear-gradient(to right, #8b5cf6, #a78bfa)' }} />
                    </div>
                  </div>
                </div>
              ) : (
                <input type="text" value={manualCode}
                  onChange={e => setManualCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="6-digit code" maxLength={6}
                  className="w-full bg-white/5 border border-white/10 rounded-md px-3 py-2.5 text-sm font-mono text-white placeholder:text-white/20 focus:outline-none focus:border-violet-500/60 transition-all tracking-[0.4em] text-center"
                />
              )}
            </div>

            {setupError && (
              <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5 text-red-400 text-xs">
                <AlertCircle size={13} className="mt-0.5 shrink-0" />
                <span>{setupError}</span>
              </div>
            )}

            <button onClick={handleSetup} disabled={setupLoading || !isSetup}
              className="w-full flex items-center justify-center gap-2 bg-violet-500/20 hover:bg-violet-500/30 border border-violet-500/30 hover:border-violet-500/50 text-violet-300 font-semibold text-sm py-2.5 rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed">
              {setupLoading ? <><Loader2 size={14} className="animate-spin" />Saving…</> : <><KeyRound size={14} />Set Access Code & Login</>}
            </button>
          </div>
        ) : (
          /* ── Normal login ─────────────────────────────────────── */
          <div className="bg-white/[0.03] border border-white/8 rounded-xl p-6 flex flex-col gap-5">
            <div>
              <h1 className="text-white font-semibold text-base">Admin Login</h1>
              <p className="text-white/40 text-xs mt-1 leading-relaxed">
                Enter your access code to open the control panel.
              </p>
            </div>

            {/* Access Code */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-mono font-semibold tracking-widest text-cyan-400/80 uppercase">Access Code</label>
              <div className="relative">
                <input
                  type={showCode ? "text" : "password"}
                  value={accessCode}
                  onChange={e => setAccessCode(e.target.value)}
                  placeholder="Your access code"
                  autoComplete="current-password"
                  className="w-full bg-white/5 border border-white/10 rounded-md px-3 py-2.5 text-sm font-mono text-white placeholder:text-white/20 focus:outline-none focus:border-cyan-500/60 focus:bg-white/8 transition-all pr-10"
                />
                <button type="button" onClick={() => setShowCode(v => !v)} tabIndex={-1}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition-colors">
                  {showCode ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            {/* 2FA Code */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-mono font-semibold tracking-widest text-cyan-400/80 uppercase">2FA Code</label>
              {autoTotpEnabled ? (
                <div className="flex items-center gap-3 bg-violet-500/10 border border-violet-500/20 rounded-md px-4 py-2.5">
                  <span className="text-2xl font-mono font-bold text-violet-300 tracking-[0.4em] flex-1">{totpCode || "······"}</span>
                  <div className="flex flex-col items-end gap-1">
                    <span className="text-[10px] text-slate-500">Auto</span>
                    <div className="w-12 h-1 bg-white/5 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-1000"
                        style={{ width: `${(totpTimeLeft / 30) * 100}%`, background: totpTimeLeft <= 5 ? '#ef4444' : 'linear-gradient(to right, #8b5cf6, #a78bfa)' }} />
                    </div>
                  </div>
                </div>
              ) : (
                <input type="text" value={manualCode}
                  onChange={e => setManualCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="6-digit code" maxLength={6}
                  className="w-full bg-white/5 border border-white/10 rounded-md px-3 py-2.5 text-sm font-mono text-white placeholder:text-white/20 focus:outline-none focus:border-cyan-500/60 focus:bg-white/8 transition-all tracking-[0.4em] text-center"
                />
              )}
            </div>

            {error && (
              <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5 text-red-400 text-xs">
                <AlertCircle size={13} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <button onClick={handleConnect} disabled={loading || !isSetup}
              className="w-full flex items-center justify-center gap-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 hover:border-cyan-500/50 text-cyan-300 font-semibold text-sm py-2.5 rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed">
              {loading ? <><Loader2 size={14} className="animate-spin" />Connecting…</> : <><ShieldCheck size={14} />Login</>}
            </button>
          </div>
        )}

        <button onClick={() => setLocation("/config")}
          className="mt-4 w-full flex items-center justify-center gap-1.5 text-white/20 hover:text-white/40 text-[11px] transition-colors">
          <Settings size={11} />
          Configure API Server
        </button>
      </div>
    </div>
  );
}
