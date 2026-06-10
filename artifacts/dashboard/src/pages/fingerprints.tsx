import React, { useState, useRef, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import { Fingerprint, Trash2, Plus, RefreshCw, AlertTriangle, ToggleLeft, ToggleRight, Copy, Check } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface FpRecord {
  id: number;
  data: string;
  enabled: boolean;
  createdAt: string;
}

function ageDays(iso: string): string {
  try {
    const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
    if (d === 0) return "today";
    if (d === 1) return "1 day ago";
    return `${d} days ago`;
  } catch { return "—"; }
}

function isValidXfp(s: string): boolean {
  if (!s || !s.includes(".")) return false;
  const [snow, token] = s.split(".", 2);
  return /^\d{10,}$/.test(snow) && token.length >= 10;
}

function truncateXfp(s: string): string {
  if (s.length <= 40) return s;
  return s.slice(0, 22) + "…" + s.slice(-12);
}

export default function FingerprintsPage() {
  const { getHeaders, apiBaseUrl } = useAuth();
  const { toast } = useToast();

  const [records, setRecords] = useState<FpRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [inputText, setInputText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function apiFetch(path: string, opts?: RequestInit) {
    return fetch(`${apiBaseUrl}/api${path}`, {
      ...opts,
      headers: { ...getHeaders(), "Content-Type": "application/json", ...(opts?.headers ?? {}) },
    });
  }

  async function load() {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await apiFetch("/fingerprints/all");
      const json = await res.json();
      if (!res.ok) { setLoadError(json?.error ?? `HTTP ${res.status}`); return; }
      setRecords(Array.isArray(json.fingerprints) ? json.fingerprints : []);
    } catch (err: any) {
      setLoadError(err?.message ?? "Network error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function addLines(raw: string) {
    const lines = raw.split("\n").map(l => l.trim()).filter(Boolean);
    const valid = lines.filter(isValidXfp);
    const invalid = lines.length - valid.length;

    if (!valid.length) {
      toast({ title: "No valid x-fingerprints found", description: "Format: snowflakeID.base64token", variant: "destructive" });
      return;
    }
    if (invalid > 0) {
      toast({ title: `${invalid} line(s) skipped — invalid format`, variant: "destructive" });
    }

    setSubmitting(true);
    try {
      const body = valid.length === 1
        ? JSON.stringify({ data: valid[0] })
        : JSON.stringify({ bulk: valid });
      const res = await apiFetch("/fingerprints", { method: "POST", body });
      const json = await res.json();
      if (json.success) {
        toast({ title: `Added ${json.inserted ?? 1} x-fingerprint(s)` });
        setInputText("");
        load();
      } else {
        toast({ title: json.error ?? "Failed", variant: "destructive" });
      }
    } catch { toast({ title: "Network error", variant: "destructive" }); }
    finally { setSubmitting(false); }
  }

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    await addLines(await file.text());
    e.target.value = "";
  }

  async function toggleRecord(id: number, cur: boolean) {
    try {
      await apiFetch(`/fingerprints/${id}`, { method: "PATCH", body: JSON.stringify({ enabled: !cur }) });
      setRecords(p => p.map(r => r.id === id ? { ...r, enabled: !cur } : r));
    } catch { toast({ title: "Update failed", variant: "destructive" }); }
  }

  async function deleteRecord(id: number) {
    try {
      await apiFetch(`/fingerprints/${id}`, { method: "DELETE" });
      setRecords(p => p.filter(r => r.id !== id));
      toast({ title: "Deleted" });
    } catch { toast({ title: "Delete failed", variant: "destructive" }); }
  }

  async function clearAll() {
    if (!confirm("Delete ALL x-fingerprints? This cannot be undone.")) return;
    try {
      await apiFetch("/fingerprints", { method: "DELETE" });
      setRecords([]);
      toast({ title: "All fingerprints cleared" });
    } catch { toast({ title: "Failed to clear", variant: "destructive" }); }
  }

  function copyFp(fp: FpRecord) {
    navigator.clipboard.writeText(fp.data).then(() => {
      setCopiedId(fp.id);
      setTimeout(() => setCopiedId(null), 1500);
    });
  }

  const enabledCount = records.filter(r => r.enabled).length;

  const card: React.CSSProperties = {
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 12,
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 42, height: 42, borderRadius: 10, flexShrink: 0,
          background: "rgba(139,92,246,0.15)", border: "1px solid rgba(139,92,246,0.3)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <Fingerprint style={{ width: 20, height: 20, color: "#a78bfa" }} />
        </div>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9" }}>X-Fingerprint Pool</div>
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
            Discord x-fingerprints (<span style={{ fontFamily: "monospace", color: "#94a3b8" }}>snowflakeID.token</span>) — workers pick a random enabled one each run
          </div>
        </div>
      </div>

      {/* ── Stats ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
        {[
          { label: "Total",   value: records.length,  color: "#cbd5e1" },
          { label: "Enabled", value: enabledCount,    color: "#34d399" },
          { label: "Oldest",  value: records.length ? ageDays(records[0]?.createdAt) : "—", color: "#a78bfa" },
        ].map(s => (
          <div key={s.label} style={{ ...card, padding: 16, textAlign: "center" }}>
            <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "monospace", color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 10, color: "#475569", textTransform: "uppercase", letterSpacing: "0.1em", marginTop: 4 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* ── Format hint ── */}
      <div style={{
        ...card,
        padding: "12px 16px",
        background: "rgba(139,92,246,0.05)",
        border: "1px solid rgba(139,92,246,0.2)",
        display: "flex", alignItems: "flex-start", gap: 10,
      }}>
        <AlertTriangle style={{ width: 15, height: 15, color: "#a78bfa", flexShrink: 0, marginTop: 1 }} />
        <div style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.6 }}>
          <span style={{ color: "#c4b5fd", fontWeight: 600 }}>Expected format: </span>
          <code style={{ fontFamily: "monospace", color: "#a78bfa", background: "rgba(139,92,246,0.12)", padding: "1px 6px", borderRadius: 4 }}>
            1459182762186637497.SDYEKQ0S-IQ56DYu0Px65a3Kn1M
          </code>
          <br />
          Paste one per line, or upload a .txt file. Invalid lines are skipped automatically.
        </div>
      </div>

      {/* ── Input panel ── */}
      <div style={{ ...card, padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Plus style={{ width: 15, height: 15, color: "#22d3ee" }} />
          <span style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>Add X-Fingerprints</span>
        </div>

        <textarea
          value={inputText}
          onChange={e => setInputText(e.target.value)}
          placeholder={"1459182762186637497.SDYEKQ0S-IQ56DYu0Px65a3Kn1M\n1459182762186637498.AbCdEfGh-XyZ1234567890abcde\n...one per line"}
          rows={6}
          style={{
            width: "100%", boxSizing: "border-box",
            background: "rgba(0,0,0,0.35)", border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 8, padding: "10px 12px", color: "#cbd5e1",
            fontSize: 12, fontFamily: "monospace", outline: "none", resize: "vertical",
          }}
          onFocus={e => { e.currentTarget.style.borderColor = "rgba(139,92,246,0.4)"; }}
          onBlur={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)"; }}
        />

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button
            onClick={() => addLines(inputText)}
            disabled={!inputText.trim() || submitting}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "7px 16px", borderRadius: 8, fontSize: 12, fontWeight: 600,
              cursor: !inputText.trim() || submitting ? "not-allowed" : "pointer",
              border: "1px solid rgba(139,92,246,0.4)",
              background: "rgba(139,92,246,0.15)", color: "#c4b5fd",
              opacity: !inputText.trim() || submitting ? 0.4 : 1,
              transition: "all 0.15s",
            }}
          >
            <Plus style={{ width: 13, height: 13 }} />
            {submitting ? "Adding…" : "Add"}
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={submitting}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "7px 16px", borderRadius: 8, fontSize: 12, fontWeight: 600,
              cursor: submitting ? "not-allowed" : "pointer",
              border: "1px solid rgba(255,255,255,0.1)",
              background: "rgba(255,255,255,0.05)", color: "#94a3b8",
              opacity: submitting ? 0.4 : 1, transition: "all 0.15s",
            }}
          >
            Upload .txt file
          </button>
          <input ref={fileRef} type="file" accept=".txt,text/plain" style={{ display: "none" }} onChange={handleFile} />
        </div>
      </div>

      {/* ── Pool list ── */}
      <div style={{ ...card, padding: 20 }}>

        {/* List header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Fingerprint style={{ width: 15, height: 15, color: "#a78bfa" }} />
            <span style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>Pool</span>
            <span style={{ fontSize: 11, color: "#475569", fontFamily: "monospace" }}>
              {records.length} total · {enabledCount} enabled
            </span>
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            <button onClick={load} title="Refresh" style={{ width: 30, height: 30, borderRadius: 8, background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: "#475569" }}>
              <RefreshCw style={{ width: 13, height: 13, animation: loading ? "fp-spin 1s linear infinite" : "none" }} />
            </button>
            {records.length > 0 && (
              <button onClick={clearAll} title="Clear all" style={{ width: 30, height: 30, borderRadius: 8, background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: "#475569" }}>
                <Trash2 style={{ width: 13, height: 13 }} />
              </button>
            )}
          </div>
        </div>

        {/* Error */}
        {loadError ? (
          <div style={{ display: "flex", gap: 10, padding: 14, background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 10 }}>
            <AlertTriangle style={{ width: 15, height: 15, color: "#f87171", flexShrink: 0, marginTop: 1 }} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 500, color: "#fca5a5" }}>Failed to load</div>
              <div style={{ fontSize: 11, color: "rgba(252,165,165,0.7)", fontFamily: "monospace", marginTop: 3 }}>{loadError}</div>
              <button onClick={load} style={{ marginTop: 6, fontSize: 11, color: "#fca5a5", background: "none", border: "none", cursor: "pointer", textDecoration: "underline", padding: 0 }}>Retry</button>
            </div>
          </div>

        ) : records.length === 0 ? (
          <div style={{ textAlign: "center", padding: "48px 0", color: "#334155" }}>
            <Fingerprint style={{ width: 38, height: 38, margin: "0 auto 12px", opacity: 0.25 }} />
            <div style={{ fontSize: 14, marginBottom: 4 }}>No x-fingerprints uploaded yet</div>
            <div style={{ fontSize: 12, color: "#1e293b" }}>Workers will auto-fetch live fingerprints from Discord until you add some here</div>
          </div>

        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 440, overflowY: "auto", paddingRight: 2 }}>
            {records.map(fp => (
              <div
                key={fp.id}
                style={{
                  display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
                  borderRadius: 10, transition: "all 0.18s",
                  background: fp.enabled ? "rgba(16,185,129,0.04)" : "rgba(255,255,255,0.02)",
                  border: fp.enabled ? "1px solid rgba(16,185,129,0.15)" : "1px solid rgba(255,255,255,0.06)",
                  opacity: fp.enabled ? 1 : 0.5,
                }}
              >
                {/* Toggle */}
                <button onClick={() => toggleRecord(fp.id, fp.enabled)} style={{ background: "none", border: "none", cursor: "pointer", flexShrink: 0, padding: 0, lineHeight: 0 }}>
                  {fp.enabled
                    ? <ToggleRight style={{ width: 22, height: 22, color: "#34d399" }} />
                    : <ToggleLeft  style={{ width: 22, height: 22, color: "#334155" }} />}
                </button>

                {/* Fingerprint value */}
                <code style={{ flex: 1, minWidth: 0, fontSize: 11, fontFamily: "monospace", color: "#94a3b8", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {truncateXfp(fp.data)}
                </code>

                {/* Meta */}
                <div style={{ display: "flex", gap: 10, alignItems: "center", flexShrink: 0 }}>
                  <span style={{ fontSize: 10, color: "#334155", display: "none" }} className="fp-meta">#{fp.id}</span>
                  <span style={{ fontSize: 10, color: "#334155" }}>{ageDays(fp.createdAt)}</span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: fp.enabled ? "#34d399" : "#334155" }}>
                    {fp.enabled ? "ON" : "OFF"}
                  </span>
                </div>

                {/* Copy */}
                <button
                  onClick={() => copyFp(fp)}
                  title="Copy full fingerprint"
                  style={{ flexShrink: 0, width: 26, height: 26, borderRadius: 6, background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: "#475569" }}
                >
                  {copiedId === fp.id
                    ? <Check style={{ width: 12, height: 12, color: "#34d399" }} />
                    : <Copy style={{ width: 12, height: 12 }} />}
                </button>

                {/* Delete */}
                <button
                  onClick={() => deleteRecord(fp.id)}
                  style={{ flexShrink: 0, width: 26, height: 26, borderRadius: 6, background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: "#334155" }}
                >
                  <Trash2 style={{ width: 12, height: 12 }} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── How workers use these ── */}
      <div style={{ ...card, padding: "14px 16px", background: "rgba(139,92,246,0.04)", border: "1px solid rgba(139,92,246,0.15)" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
          <AlertTriangle style={{ width: 14, height: 14, color: "#a78bfa", flexShrink: 0, marginTop: 2 }} />
          <div style={{ fontSize: 12, color: "#64748b", lineHeight: 1.7 }}>
            <span style={{ color: "#e2e8f0", fontWeight: 600 }}>How workers use these: </span>
            Each run picks a random <span style={{ color: "#34d399", fontFamily: "monospace" }}>enabled</span> fingerprint and sends it as the{" "}
            <code style={{ fontFamily: "monospace", color: "#a78bfa" }}>x-fingerprint</code> header on the Discord login request.
            Fingerprints fetched days ago look more trustworthy than brand-new ones — upload a batch and they age automatically.
            <br />
            <span style={{ color: "#64748b", fontSize: 11 }}>If the pool is empty, workers auto-fetch a live one from Discord's API instead.</span>
          </div>
        </div>
      </div>

      <style>{`@keyframes fp-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
