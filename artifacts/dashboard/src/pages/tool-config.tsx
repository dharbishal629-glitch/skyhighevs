import React, { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { GlassCard, GlassButton, GlassInput, SectionHeader, Badge } from "@/components/ui/cyber-components";
import { cn } from "@/components/ui/cyber-components";
import {
  Settings2, Save, RefreshCw, CheckCircle2, XCircle, AlertCircle,
  Loader2, Globe, Cpu, Zap, Shield, Monitor, Layers,
  Eye, EyeOff, Timer,
} from "lucide-react";

interface ToolConfig {
  emailProvider: string;
  zeusxApiKey: string;
  hotmail007ClientKey: string;
  cybertempApiKey: string;
  cybertempCustomDomains: string;
  draxonoApiKey: string;
  draxonoDomainSecret: string;
  draxonoCustomDomains: string;
  browser: string;
  threads: number;
  target: number;
  cooldownSeconds: number;
  proxyEnabled: boolean;
  proxyUrl: string;
  adbEnabled: boolean;
  adbPath: string;
  captchaSolverEnabled: boolean;
  openRouterApiKey: string;
  openRouterModel: string;
  captchaMaxAttempts: number;
  nopechaEnabled: boolean;
  nopechaApiKey: string;
  captchaTimeoutSeconds: number;
}

const DEFAULT: ToolConfig = {
  emailProvider: "cybertemp",
  zeusxApiKey: "",
  hotmail007ClientKey: "",
  cybertempApiKey: "",
  cybertempCustomDomains: "",
  draxonoApiKey: "",
  draxonoDomainSecret: "",
  draxonoCustomDomains: "",
  browser: "chrome",
  threads: 1,
  target: 0,
  cooldownSeconds: 0,
  proxyEnabled: false,
  proxyUrl: "",
  adbEnabled: false,
  adbPath: "",
  captchaSolverEnabled: false,
  openRouterApiKey: "",
  openRouterModel: "google/gemini-2.0-flash-001",
  captchaMaxAttempts: 4,
  nopechaEnabled: false,
  nopechaApiKey: "",
  captchaTimeoutSeconds: 120,
};

function Toggle({ value, onChange, label, hint }: { value: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <div className="text-sm font-medium text-slate-200">{label}</div>
        {hint && <div className="text-[11px] text-slate-500 mt-0.5">{hint}</div>}
      </div>
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={cn(
          "relative w-10 h-5.5 rounded-full transition-colors flex-shrink-0",
          value ? "bg-violet-600" : "bg-white/10"
        )}
        style={{ minWidth: 40, height: 22 }}
      >
        <span className={cn(
          "absolute top-0.5 w-4.5 h-4.5 rounded-full bg-white shadow transition-all",
          value ? "left-[calc(100%-20px)]" : "left-0.5"
        )} style={{ width: 18, height: 18 }} />
      </button>
    </div>
  );
}

function SecretField({ label, hint, value, onChange, placeholder }: { label: string; hint?: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  const [show, setShow] = useState(false);
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">{label}</label>
      {hint && <p className="text-[11px] text-slate-600 -mt-0.5">{hint}</p>}
      <div className="relative">
        <GlassInput
          type={show ? "text" : "password"}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="pr-10 font-mono text-xs"
        />
        <button type="button" onClick={() => setShow(v => !v)} tabIndex={-1}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-400 transition-colors">
          {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
        </button>
      </div>
    </div>
  );
}

function Field({ label, hint, value, onChange, placeholder, type = "text" }: {
  label: string; hint?: string; value: string | number; onChange: (v: string) => void;
  placeholder?: string; type?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">{label}</label>
      {hint && <p className="text-[11px] text-slate-600 -mt-0.5">{hint}</p>}
      <GlassInput
        type={type}
        value={String(value)}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  );
}

function ProviderCard({ id, label, sub, active, onClick }: { id: string; label: string; sub: string; active: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className={cn(
        "w-full text-left px-4 py-3 rounded-xl transition-all border",
        active
          ? "bg-violet-600/15 border-violet-500/40 shadow-lg shadow-violet-500/10"
          : "bg-white/3 border-white/8 hover:bg-white/6 hover:border-white/15"
      )}>
      <div className={cn("text-sm font-semibold", active ? "text-violet-300" : "text-slate-300")}>{label}</div>
      <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>
    </button>
  );
}

export default function ToolConfig() {
  const { getHeaders, apiBaseUrl } = useAuth();
  const [form, setForm] = useState<ToolConfig>(DEFAULT);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");
  const [msg, setMsg] = useState("");

  const set = <K extends keyof ToolConfig>(key: K) => (val: ToolConfig[K]) =>
    setForm(f => ({ ...f, [key]: val }));

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const res = await fetch(`${apiBaseUrl}/api/config/full`, { headers: getHeaders() });
        const data = await res.json() as { config?: Record<string, unknown> };
        if (data.config) setForm({ ...DEFAULT, ...data.config } as ToolConfig);
      } catch {
        setMsg("Could not load config from API.");
        setStatus("error");
      }
      setLoading(false);
    })();
  }, [apiBaseUrl]);

  const save = async () => {
    setSaving(true); setStatus("idle"); setMsg("");
    try {
      const res = await fetch(`${apiBaseUrl}/api/config`, {
        method: "PUT",
        headers: { ...getHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json() as { success?: boolean; error?: string; detail?: string };
      if (data.success) {
        setStatus("ok"); setMsg("Config saved successfully.");
      } else {
        const detail = data.detail ? ` (${data.detail})` : "";
        setStatus("error"); setMsg((data.error || "Save failed.") + detail);
      }
    } catch {
      setStatus("error"); setMsg("Network error — could not reach API.");
    }
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40 gap-3 text-slate-500 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" />Loading config…
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Tool Config"
        sub="Settings fetched by the tool at startup — no config file needed on worker machines"
        action={
          <GlassButton variant="gold" size="sm" onClick={save} disabled={saving}>
            {saving ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Saving…</> : <><Save className="w-3.5 h-3.5" />Save Config</>}
          </GlassButton>
        }
      />

      {status !== "idle" && (
        <div className={cn(
          "flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm border",
          status === "ok"
            ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
            : "bg-red-500/10 border-red-500/20 text-red-400"
        )}>
          {status === "ok" ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
          {msg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* ── Email Provider ────────────────────────────────── */}
        <GlassCard className="p-5 space-y-4">
          <div className="flex items-center gap-2 mb-1">
            <Globe className="w-4 h-4 text-cyan-400" />
            <span className="text-sm font-semibold text-slate-200">Email Provider</span>
          </div>
          <div className="space-y-2">
            <ProviderCard id="cybertemp" label="CyberTemp" sub="Temp emails · discord-domain · API key required" active={form.emailProvider === "cybertemp"} onClick={() => set("emailProvider")("cybertemp")} />
            <ProviderCard id="hotmail007" label="Hotmail007" sub="Purchased Outlook/Hotmail accounts · client key required" active={form.emailProvider === "hotmail007"} onClick={() => set("emailProvider")("hotmail007")} />
            <ProviderCard id="zeusx" label="Zeus-X" sub="Bulk Outlook/Hotmail from zeus-x.ru · API key required" active={form.emailProvider === "zeusx"} onClick={() => set("emailProvider")("zeusx")} />
            <ProviderCard id="draxono" label="Draxono" sub="DraxonMails · API key required (mail.draxono.in)" active={form.emailProvider === "draxono"} onClick={() => set("emailProvider")("draxono")} />
          </div>

          <div className="space-y-3 pt-2">
            {form.emailProvider === "zeusx" && (
              <SecretField label="Zeus-X API Key" hint="From your zeus-x.ru account" value={form.zeusxApiKey} onChange={set("zeusxApiKey")} placeholder="your-zeus-x-api-key" />
            )}
            {form.emailProvider === "hotmail007" && (
              <SecretField label="Hotmail007 Client Key" hint="From hotmail007.com" value={form.hotmail007ClientKey} onChange={set("hotmail007ClientKey")} placeholder="your-client-key" />
            )}
            {form.emailProvider === "cybertemp" && (
              <SecretField label="CyberTemp API Key" hint="Required — get your key from cybertemp.xyz" value={form.cybertempApiKey} onChange={set("cybertempApiKey")} placeholder="your-cybertemp-api-key" />
            )}
            {form.emailProvider === "draxono" && (
              <SecretField label="Draxono API Key" hint="Required — get your key from mail.draxono.in (sent as X-Api-Key header)" value={form.draxonoApiKey} onChange={set("draxonoApiKey")} placeholder="duk_…" />
            )}
            {form.emailProvider === "draxono" && (
              <SecretField label="Private Domain Secret" hint="Optional — only needed for verified private custom domains (sent as X-Draxon-Domain-Secret)" value={form.draxonoDomainSecret} onChange={set("draxonoDomainSecret")} placeholder="dx-your-private-domain-secret" />
            )}
            {form.emailProvider === "draxono" && (
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">Custom Domains</label>
                <p className="text-[11px] text-slate-600 -mt-0.5">
                  Comma-separated custom domains you've verified on DraxonMails. Leave blank to use Draxono's public domain pool.
                </p>
                <GlassInput
                  type="text"
                  value={form.draxonoCustomDomains}
                  onChange={e => set("draxonoCustomDomains")(e.target.value)}
                  placeholder="domain1.com, domain2.net"
                  className="font-mono text-xs"
                />
                {form.draxonoCustomDomains.trim() && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {form.draxonoCustomDomains.split(",").map(d => d.trim()).filter(Boolean).map(d => (
                      <span key={d} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-cyan-500/10 border border-cyan-500/20 text-[11px] font-mono text-cyan-400">
                        @{d.replace(/^@/, "")}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
            {form.emailProvider === "cybertemp" && (
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">Custom Domains</label>
                <p className="text-[11px] text-slate-600 -mt-0.5">
                  Comma-separated domains you own and have pointed to CyberTemp (e.g. <span className="font-mono text-slate-500">diddyricky.com, diddyricky.info</span>).
                  Leave blank to use CyberTemp's default domain pool.
                </p>
                <GlassInput
                  type="text"
                  value={form.cybertempCustomDomains}
                  onChange={e => set("cybertempCustomDomains")(e.target.value)}
                  placeholder="domain1.com, domain2.net, domain3.info"
                  className="font-mono text-xs"
                />
                {form.cybertempCustomDomains.trim() && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {form.cybertempCustomDomains.split(",").map(d => d.trim()).filter(Boolean).map(d => (
                      <span key={d} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-cyan-500/10 border border-cyan-500/20 text-[11px] font-mono text-cyan-400">
                        @{d.replace(/^@/, "")}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </GlassCard>

        {/* ── Browser & Threads ─────────────────────────────── */}
        <GlassCard className="p-5 space-y-4">
          <div className="flex items-center gap-2 mb-1">
            <Monitor className="w-4 h-4 text-violet-400" />
            <span className="text-sm font-semibold text-slate-200">Browser & Performance</span>
          </div>

          <div className="space-y-2">
            <p className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">Browser</p>
            <div className="grid grid-cols-2 gap-2">
              {[["chrome", "Chrome", "Default"], ["brave", "Brave", "Auto-detect"]].map(([id, label, sub]) => (
                <ProviderCard key={id} id={id} label={label} sub={sub} active={form.browser === id} onClick={() => set("browser")(id)} />
              ))}
            </div>
          </div>

          <Field
            label="Threads"
            hint="Parallel browser windows (1–10 recommended)"
            value={form.threads}
            onChange={v => set("threads")(Math.max(1, parseInt(v) || 1))}
            type="number"
            placeholder="1"
          />

          <Field
            label="Target Accounts"
            hint="Stop after this many accounts · 0 = run forever"
            value={form.target}
            onChange={v => set("target")(Math.max(0, parseInt(v) || 0))}
            type="number"
            placeholder="0"
          />

          <div className="border-t border-white/5 pt-4">
            <div className="flex items-center gap-2 mb-3">
              <Timer className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase">Cooldown</span>
            </div>
            <Field
              label="Cooldown (seconds)"
              hint="Wait this many seconds after each account is created before starting the next · 0 = no cooldown"
              value={form.cooldownSeconds}
              onChange={v => set("cooldownSeconds")(Math.max(0, parseInt(v) || 0))}
              type="number"
              placeholder="0"
            />
            {form.cooldownSeconds > 0 && (
              <div className="mt-2 flex items-center gap-2 text-[11px] text-cyan-400/80 bg-cyan-500/8 border border-cyan-500/15 rounded-lg px-3 py-2">
                <Timer className="w-3 h-3 flex-shrink-0" />
                Tool will wait {form.cooldownSeconds}s between each account creation
              </div>
            )}
          </div>
        </GlassCard>

        {/* ── Proxy ────────────────────────────────────────── */}
        <GlassCard className="p-5 space-y-4">
          <div className="flex items-center gap-2 mb-1">
            <Layers className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-semibold text-slate-200">Proxy</span>
          </div>

          <Toggle
            value={form.proxyEnabled}
            onChange={set("proxyEnabled")}
            label="Enable Proxy"
            hint="Route tool traffic through a proxy server"
          />

          {form.proxyEnabled && (
            <Field
              label="Proxy URL"
              hint="Format: http://user:pass@ip:port or socks5://..."
              value={form.proxyUrl}
              onChange={set("proxyUrl")}
              placeholder="http://user:pass@1.2.3.4:8080"
            />
          )}
        </GlassCard>

        {/* ── ADB ──────────────────────────────────────────── */}
        <GlassCard className="p-5 space-y-4">
          <div className="flex items-center gap-2 mb-1">
            <Cpu className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-semibold text-slate-200">ADB IP Rotation</span>
          </div>

          <Toggle
            value={form.adbEnabled}
            onChange={set("adbEnabled")}
            label="Enable ADB Rotation"
            hint="Rotate IP via Android phone airplane mode toggle"
          />

          {form.adbEnabled && (
            <Field
              label="ADB Path"
              hint="Leave blank to auto-detect · e.g. C:\\platform-tools\\adb.exe"
              value={form.adbPath}
              onChange={set("adbPath")}
              placeholder="auto-detect"
            />
          )}

          {form.adbEnabled && (
            <div className="flex items-start gap-2 text-[11px] text-amber-400/80 bg-amber-500/8 border border-amber-500/15 rounded-lg px-3 py-2">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              USB debugging must be enabled on the phone and device must be connected.
            </div>
          )}
        </GlassCard>
      </div>

      <GlassCard className="p-5 space-y-4">
        <SectionHeader icon={<Shield className="w-4 h-4" />} title="Captcha Solver (OpenRouter)" hint="Auto-solves Discord's accessibility text challenges via an LLM" />

        <Toggle
          value={form.captchaSolverEnabled}
          onChange={set("captchaSolverEnabled")}
          label="Enable Captcha Solver"
          hint="When a captcha appears, opens 3-dots → Accessibility Challenge, sends the question to OpenRouter, types the answer back. Loops up to N rounds."
        />

        {form.captchaSolverEnabled && (
          <>
            <SecretField
              label="OpenRouter API Key"
              hint="Get one at openrouter.ai/keys (starts with sk-or-...)"
              value={form.openRouterApiKey}
              onChange={set("openRouterApiKey")}
              placeholder="sk-or-v1-..."
            />
            <Field
              label="OpenRouter Model"
              hint="Cheap+fast default works well. Use any model id from openrouter.ai/models"
              value={form.openRouterModel}
              onChange={set("openRouterModel")}
              placeholder="google/gemini-2.0-flash-001"
            />
            <Field
              label="Max Attempts per Account"
              hint="How many captcha rounds to try before giving up (typical: 2-4)"
              type="number"
              value={String(form.captchaMaxAttempts)}
              onChange={(v) => set("captchaMaxAttempts")(Math.max(1, parseInt(v) || 4))}
              placeholder="4"
            />
          </>
        )}
      </GlassCard>

      <GlassCard className="p-5 space-y-4">
        <SectionHeader icon={<Zap className="w-4 h-4" />} title="NoPeCHA Auto-Solver" hint="Automatically solves hCaptcha challenges — no manual intervention needed" />

        <Toggle
          value={form.nopechaEnabled}
          onChange={set("nopechaEnabled")}
          label="Enable NoPeCHA"
          hint="Uses nopecha.com to auto-solve Discord's hCaptcha. Workers need no manual captcha solving when this is on."
        />

        {form.nopechaEnabled && (
          <>
            <SecretField
              label="NoPeCHA API Key"
              hint="Get one at nopecha.com — charged per solve. Recommended: plan with hCaptcha support."
              value={form.nopechaApiKey}
              onChange={set("nopechaApiKey")}
              placeholder="nopecha-api-key-here"
            />
            <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-3 py-2.5 text-[11px] text-cyan-300/90 space-y-1">
              <p>✓ When enabled, the tool calls the NoPeCHA API after the registration form is submitted.</p>
              <p>✓ hCaptcha is detected and solved automatically — no worker interaction required.</p>
              <p>✓ Make sure your NoPeCHA plan includes hCaptcha solving.</p>
            </div>
          </>
        )}

        <div className="border-t border-white/5 pt-4">
          <Field
            label="Captcha Wait Timeout (seconds)"
            hint="How long to wait for captcha to be solved before giving up. Set higher if captcha loads slowly (recommended: 120–180s). The tool will continue as soon as the captcha is solved — it won't wait the full time if done early."
            value={form.captchaTimeoutSeconds}
            onChange={v => set("captchaTimeoutSeconds")(Math.max(30, parseInt(v) || 120))}
            type="number"
            placeholder="120"
          />
          {form.captchaTimeoutSeconds < 60 && (
            <div className="mt-2 flex items-center gap-2 text-[11px] text-amber-400/80 bg-amber-500/8 border border-amber-500/15 rounded-lg px-3 py-2">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
              Under 60s may not be enough — Discord's hCaptcha can take 15–30s just to load.
            </div>
          )}
        </div>
      </GlassCard>

      <GlassCard className="p-4">
        <div className="flex items-start gap-3">
          <Shield className="w-4 h-4 text-violet-400 flex-shrink-0 mt-0.5" />
          <div className="text-[11px] text-slate-500 leading-relaxed">
            <span className="text-slate-400 font-medium">How it works:</span> When a worker runs the tool and enters their key, the tool automatically fetches this config from your API server. No <code className="font-mono bg-white/5 px-1 rounded">config.json</code> file is needed on the worker's machine — everything is pulled from here.
            API keys are transmitted securely over HTTPS and never stored locally on worker machines.
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
