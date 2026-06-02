import React, { useState } from "react";
import { useAuth, AppConfig, useTotpTimer } from "@/lib/auth-context";
import { GlassCard, GlassButton, GlassInput, Badge, SectionHeader } from "@/components/ui/cyber-components";
import { cn } from "@/components/ui/cyber-components";
import {
  RefreshCw, CheckCircle2, XCircle, Check, Eye, EyeOff,
  Shield, Server, Globe, LogOut, Mail, Zap, Save, Copy, KeyRound, Lock,
} from "lucide-react";
import { useLocation } from "wouter";

function Field({ label, hint, value, onChange, masked, placeholder, monospace }: {
  label: string; hint?: string; value: string;
  onChange: (v: string) => void; masked?: boolean;
  placeholder?: string; monospace?: boolean;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">{label}</label>
      {hint && <p className="text-[10px] text-slate-600 -mt-0.5">{hint}</p>}
      <div className="relative">
        <GlassInput
          type={masked && !show ? "password" : "text"}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className={cn("pr-10", monospace && "font-mono text-xs")}
        />
        {masked && (
          <button type="button" onClick={() => setShow(v => !v)} tabIndex={-1}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-400 transition-colors">
            {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
          </button>
        )}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { config, saveAppConfig, totpCode, autoTotpEnabled, isAuthenticated, logout, getHeaders } = useAuth();
  const totpTimeLeft = useTotpTimer();
  const [codeCopied, setCodeCopied] = useState(false);

  // Access code change state
  const [accCurrent, setAccCurrent] = useState("");
  const [accNew, setAccNew] = useState("");
  const [accConfirm, setAccConfirm] = useState("");
  const [showAccCurrent, setShowAccCurrent] = useState(false);
  const [showAccNew, setShowAccNew] = useState(false);
  const [accLoading, setAccLoading] = useState(false);
  const [accMsg, setAccMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const handleChangeAccessCode = async () => {
    if (!accNew || accNew.length < 4) { setAccMsg({ type: "err", text: "New code must be at least 4 characters." }); return; }
    if (accNew !== accConfirm) { setAccMsg({ type: "err", text: "New codes don't match." }); return; }
    setAccLoading(true); setAccMsg(null);
    try {
      const res = await fetch(`${config.apiUrl.replace(/\/$/, "")}/api/admin/change-code`, {
        method: "POST",
        headers: { ...getHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ currentCode: accCurrent, newCode: accNew }),
      });
      const data = await res.json();
      if (!res.ok) setAccMsg({ type: "err", text: data.error || `Error ${res.status}` });
      else {
        setAccMsg({ type: "ok", text: "Access code updated! Use it next login." });
        setAccCurrent(""); setAccNew(""); setAccConfirm("");
      }
    } catch { setAccMsg({ type: "err", text: "Could not reach API server." }); }
    setAccLoading(false);
  };

  const copyTotpCode = () => {
    if (!totpCode) return;
    navigator.clipboard.writeText(totpCode).then(() => {
      setCodeCopied(true);
      setTimeout(() => setCodeCopied(false), 1500);
    });
  };
  const [, setLocation] = useLocation();
  const [form, setForm] = useState<AppConfig>({ ...config });
  const [saved, setSaved] = useState(false);
  const [testStatus, setTestStatus] = useState<"idle" | "loading" | "ok" | "fail">("idle");
  const [testMsg, setTestMsg] = useState("");

  const set = (key: keyof AppConfig) => (v: string | boolean) =>
    setForm(f => ({ ...f, [key]: v }));

  const handleSave = () => {
    saveAppConfig(form);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const testConn = async () => {
    setTestStatus("loading"); setTestMsg("");
    try {
      const res = await fetch(`${form.apiUrl.replace(/\/$/, "")}/api/healthz`);
      if (res.ok) {
        setTestStatus("ok"); setTestMsg("API server is online and reachable.");
      } else {
        setTestStatus("fail"); setTestMsg(`Server replied HTTP ${res.status}. Check your API URL.`);
      }
    } catch {
      setTestStatus("fail"); setTestMsg("Could not reach the API server. Check the URL.");
    }
  };

  const handleLogout = () => {
    logout();
    setLocation("/");
  };

  return (
    <div className="space-y-5 max-w-2xl">
      <SectionHeader
        title="Config"
        sub="All settings saved to this browser"
        action={
          <GlassButton size="sm" variant={saved ? "primary" : "gold"} onClick={handleSave}>
            {saved ? <><Check className="w-3.5 h-3.5" />Saved!</> : <><Save className="w-3.5 h-3.5" />Save All</>}
          </GlassButton>
        }
      />

      {/* ── API Connection ─────────────────────────── */}
      <GlassCard className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Server className="w-4 h-4 text-violet-400" />
          <span className="text-sm font-semibold text-slate-200">API Connection</span>
        </div>
        <div className="space-y-3">
          <Field
            label="API Server URL"
            hint="Your public API server URL (e.g. https://your-app.onrender.com). Leave blank if dashboard and API share the same server."
            value={form.apiUrl}
            onChange={set("apiUrl")}
            placeholder="https://your-api.onrender.com"
          />
          <Field
            label="Worker API Key"
            hint="The WORKER_API_KEY set on your Render server."
            value={form.workerKey}
            onChange={set("workerKey")}
            placeholder="WAK-…"
            masked
            monospace
          />
          <Field
            label="TOTP Secret (2FA)"
            hint="Your BASE32 TOTP secret from the server. Auto-generates 2FA codes."
            value={form.totpSecret}
            onChange={set("totpSecret")}
            placeholder="ABCDEFGH1234…"
            masked
            monospace
          />
          {autoTotpEnabled && (
            <button
              type="button"
              onClick={copyTotpCode}
              title="Click to copy"
              className="flex items-center gap-4 p-3 rounded-xl mt-1 w-full text-left group transition-all hover:border-violet-500/30"
              style={{ background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.15)' }}
            >
              <Shield className="w-4 h-4 text-violet-400 flex-shrink-0" />
              <div>
                <p className="text-[10px] text-slate-600 mb-0.5">Current 2FA Code</p>
                <p className="text-xl font-mono font-bold text-violet-300 tracking-[0.4em]">{totpCode || "······"}</p>
              </div>
              <div className="flex-1">
                <p className="text-[10px] text-slate-600 mb-1">Refreshes in {totpTimeLeft}s</p>
                <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all duration-1000"
                    style={{ width: `${(totpTimeLeft / 30) * 100}%`, background: totpTimeLeft <= 5 ? '#ef4444' : 'linear-gradient(to right, #8b5cf6, #a78bfa)' }} />
                </div>
              </div>
              <div className="flex-shrink-0">
                {codeCopied
                  ? <Check className="w-4 h-4 text-emerald-400" />
                  : <Copy className="w-3.5 h-3.5 text-slate-600 group-hover:text-violet-400 transition-colors" />}
              </div>
            </button>
          )}
        </div>
      </GlassCard>

      {/* ── Test Connection ─────────────────────────── */}
      <GlassCard className="p-5">
        <div className="flex items-center gap-2 mb-3">
          <Globe className="w-4 h-4 text-cyan-400" />
          <span className="text-sm font-semibold text-slate-200">Test Connection</span>
        </div>
        <p className="text-xs text-slate-500 mb-3">
          Verify your API server is reachable. Save config first, then test.
        </p>
        <div className="flex items-center gap-3 flex-wrap">
          <GlassButton size="sm" variant="secondary" onClick={testConn} disabled={testStatus === "loading"}>
            <RefreshCw className={cn("w-3.5 h-3.5", testStatus === "loading" ? "animate-spin" : "")} />
            {testStatus === "loading" ? "Testing…" : "Test Now"}
          </GlassButton>
          {testStatus !== "idle" && testStatus !== "loading" && (
            <div className={cn("flex items-center gap-2 text-xs", testStatus === "ok" ? "text-emerald-400" : "text-red-400")}>
              {testStatus === "ok" ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
              {testMsg}
            </div>
          )}
        </div>
      </GlassCard>

      {/* ── Mail Provider ─────────────────────────── */}
      <GlassCard className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Mail className="w-4 h-4 text-cyan-400" />
          <span className="text-sm font-semibold text-slate-200">Mail Provider</span>
          <Badge variant={form.mailProvider ? "valid" : "locked"}>
            {form.mailProvider || "Not set"}
          </Badge>
        </div>
        <div className="space-y-3">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">Provider</label>
            <div className="space-y-2 mt-1">
              {[
                { id: "hotmail007", label: "Hotmail007", sub: "Purchased Outlook/Hotmail accounts · client key required" },
                { id: "cybertemp",  label: "CyberTemp",  sub: "Free temp emails · discord-domain · no key needed" },
                { id: "zeus",       label: "Zeus",        sub: "Bulk Outlook/Hotmail from zeus-x.ru · API key required" },
                { id: "draxono",    label: "Draxono",     sub: "DraxonMails · public API · no key needed" },
              ].map(({ id, label, sub }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => set("mailProvider")(id)}
                  className={cn(
                    "w-full text-left px-4 py-3 rounded-xl transition-all border",
                    form.mailProvider === id
                      ? "bg-cyan-600/15 border-cyan-500/40 shadow-lg shadow-cyan-500/10"
                      : "bg-white/3 border-white/8 hover:bg-white/6 hover:border-white/15"
                  )}
                >
                  <div className={cn("text-sm font-semibold", form.mailProvider === id ? "text-cyan-300" : "text-slate-300")}>{label}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>
                </button>
              ))}
            </div>
          </div>
          <Field
            label="Mail API Key"
            value={form.mailApiKey}
            onChange={set("mailApiKey")}
            placeholder="API key from your mail provider"
            masked monospace
          />
          <Field
            label="From Email"
            value={form.mailFromEmail}
            onChange={set("mailFromEmail")}
            placeholder="noreply@yourdomain.com"
          />
          <Field
            label="From Name"
            value={form.mailFromName}
            onChange={set("mailFromName")}
            placeholder="SkyHighEV"
          />
        </div>
      </GlassCard>

      {/* ── Zeus-X Integration ─────────────────────────── */}
      <GlassCard className="p-5">
        <div className="flex items-center gap-2 mb-1">
          <Zap className="w-4 h-4 text-amber-400" />
          <span className="text-sm font-semibold text-slate-200">Zeus-X Integration</span>
          <Badge variant={form.zeusEnabled ? "valid" : "locked"}>
            {form.zeusEnabled ? "Enabled" : "Disabled"}
          </Badge>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          Zeus-X provides Trusted Hotmail and Trusted Outlook checking.{" "}
          <a href="https://zeus-x.ru/docs" target="_blank" rel="noopener noreferrer" className="text-amber-400/70 hover:text-amber-400 underline">
            View docs
          </a>
        </p>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">Enable Zeus-X checking</span>
            <button
              onClick={() => set("zeusEnabled")(!form.zeusEnabled)}
              className={cn(
                "relative w-11 h-6 rounded-full transition-colors",
                form.zeusEnabled ? "bg-amber-500/40 border border-amber-500/50" : "bg-white/5 border border-white/10"
              )}
            >
              <span className={cn(
                "absolute top-0.5 left-0.5 w-5 h-5 rounded-full transition-transform",
                form.zeusEnabled ? "translate-x-5 bg-amber-400" : "bg-slate-600"
              )} />
            </button>
          </div>
          {form.zeusEnabled && (
            <Field
              label="Zeus-X API Key"
              value={form.zeusApiKey}
              onChange={set("zeusApiKey")}
              placeholder="Your Zeus-X API key from zeus-x.ru"
              masked monospace
            />
          )}
        </div>
      </GlassCard>

      {/* ── Save ─────────────────────────── */}
      <GlassButton variant={saved ? "primary" : "gold"} onClick={handleSave} className="w-full justify-center">
        {saved ? <><Check className="w-4 h-4" />All settings saved!</> : <><Save className="w-4 h-4" />Save All Settings</>}
      </GlassButton>

      {/* ── Change Access Code ─────────────────────────── */}
      {isAuthenticated && (
        <GlassCard className="p-5">
          <div className="flex items-center gap-2 mb-1">
            <KeyRound className="w-4 h-4 text-cyan-400" />
            <span className="text-sm font-semibold text-slate-200">Change Access Code</span>
          </div>
          <p className="text-xs text-slate-500 mb-4">
            Update your admin access code. Minimum 4 characters.
          </p>
          <div className="space-y-3">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">Current Code</label>
              <div className="relative">
                <GlassInput type={showAccCurrent ? "text" : "password"} value={accCurrent}
                  onChange={e => setAccCurrent(e.target.value)} placeholder="Your current access code"
                  className="pr-10 font-mono text-xs" />
                <button type="button" onClick={() => setShowAccCurrent(v => !v)} tabIndex={-1}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-400 transition-colors">
                  {showAccCurrent ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">New Code</label>
              <div className="relative">
                <GlassInput type={showAccNew ? "text" : "password"} value={accNew}
                  onChange={e => setAccNew(e.target.value)} placeholder="Min 4 characters"
                  className="pr-10 font-mono text-xs" />
                <button type="button" onClick={() => setShowAccNew(v => !v)} tabIndex={-1}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-400 transition-colors">
                  {showAccNew ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">Confirm New Code</label>
              <GlassInput type={showAccNew ? "text" : "password"} value={accConfirm}
                onChange={e => setAccConfirm(e.target.value)} placeholder="Repeat new code"
                className="font-mono text-xs" />
            </div>
            {accMsg && (
              <div className={cn("flex items-center gap-2 text-xs rounded-lg px-3 py-2",
                accMsg.type === "ok" ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400" : "bg-red-500/10 border border-red-500/20 text-red-400")}>
                {accMsg.type === "ok" ? <CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> : <XCircle className="w-3.5 h-3.5 shrink-0" />}
                {accMsg.text}
              </div>
            )}
            <GlassButton size="sm" variant="secondary" onClick={handleChangeAccessCode} disabled={accLoading}>
              {accLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Lock className="w-3.5 h-3.5" />}
              {accLoading ? "Saving…" : "Update Access Code"}
            </GlassButton>
          </div>
        </GlassCard>
      )}

      {/* ── Logout ─────────────────────────── */}
      {isAuthenticated && (
        <GlassCard className="p-5">
          <div className="flex items-center gap-2 mb-1">
            <LogOut className="w-4 h-4 text-red-400" />
            <span className="text-sm font-semibold text-slate-200">Log Out</span>
          </div>
          <p className="text-xs text-slate-500 mb-3">
            End your current session. Config settings are kept. You'll need to log in again.
          </p>
          <GlassButton size="sm" variant="danger" onClick={handleLogout}>
            <LogOut className="w-3.5 h-3.5" />
            Log Out
          </GlassButton>
        </GlassCard>
      )}
    </div>
  );
}
