import React, { useState, useRef, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import { Fingerprint, Upload, Trash2, Plus, RefreshCw, FileText, AlertTriangle, ToggleLeft, ToggleRight } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface FpRecord {
  id: number;
  data: string;
  enabled: boolean;
  createdAt: string;
}

function ageDays(iso: string): string {
  try {
    const ms = Date.now() - new Date(iso).getTime();
    const d = Math.floor(ms / 86400000);
    if (d === 0) return "today";
    if (d === 1) return "1 day ago";
    return `${d} days ago`;
  } catch {
    return "—";
  }
}

export default function FingerprintsPage() {
  const { getHeaders, apiBaseUrl } = useAuth();
  const { toast } = useToast();

  const [records, setRecords] = useState<FpRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [singleText, setSingleText] = useState("");
  const [bulkText, setBulkText] = useState("");
  const [tab, setTab] = useState<"single" | "bulk">("single");
  const [submitting, setSubmitting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function apiFetch(path: string, opts?: RequestInit) {
    return fetch(`${apiBaseUrl}/api${path}`, {
      ...opts,
      headers: {
        ...getHeaders(),
        "Content-Type": "application/json",
        ...(opts?.headers ?? {}),
      },
    });
  }

  async function load() {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await apiFetch("/fingerprints/all");
      const json = await res.json();
      if (!res.ok) {
        const msg = json?.error ?? `Server error ${res.status}`;
        setLoadError(msg);
        return;
      }
      setRecords(Array.isArray(json.fingerprints) ? json.fingerprints : []);
    } catch (err: any) {
      setLoadError(err?.message ?? "Network error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function addSingle() {
    const data = singleText.trim();
    if (!data || submitting) return;
    setSubmitting(true);
    try {
      const res = await apiFetch("/fingerprints", {
        method: "POST",
        body: JSON.stringify({ data }),
      });
      const json = await res.json();
      if (json.success) {
        toast({ title: "Fingerprint added" });
        setSingleText("");
        load();
      } else {
        toast({ title: json.error ?? "Failed to add", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  }

  async function addBulk(lines: string[]) {
    const bulk = lines.map(l => l.trim()).filter(Boolean);
    if (!bulk.length || submitting) return;
    setSubmitting(true);
    try {
      const res = await apiFetch("/fingerprints", {
        method: "POST",
        body: JSON.stringify({ bulk }),
      });
      const json = await res.json();
      if (json.success) {
        toast({ title: `Added ${json.inserted} fingerprint(s)` });
        setBulkText("");
        load();
      } else {
        toast({ title: json.error ?? "Failed to add", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const lines = text.split("\n");
    await addBulk(lines);
    e.target.value = "";
  }

  async function toggleRecord(id: number, current: boolean) {
    try {
      await apiFetch(`/fingerprints/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !current }),
      });
      setRecords(prev => prev.map(r => r.id === id ? { ...r, enabled: !current } : r));
    } catch {
      toast({ title: "Failed to update", variant: "destructive" });
    }
  }

  async function deleteRecord(id: number) {
    try {
      await apiFetch(`/fingerprints/${id}`, { method: "DELETE" });
      setRecords(prev => prev.filter(r => r.id !== id));
      toast({ title: "Deleted" });
    } catch {
      toast({ title: "Failed to delete", variant: "destructive" });
    }
  }

  async function clearAll() {
    if (!confirm("Delete ALL fingerprints? This cannot be undone.")) return;
    try {
      await apiFetch("/fingerprints", { method: "DELETE" });
      setRecords([]);
      toast({ title: "All fingerprints cleared" });
    } catch {
      toast({ title: "Failed to clear", variant: "destructive" });
    }
  }

  const enabledCount = records.filter(r => r.enabled).length;
  const cardStyle: React.CSSProperties = {
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 12,
  };
  const inputStyle: React.CSSProperties = {
    width: "100%",
    background: "rgba(0,0,0,0.3)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 8,
    padding: "10px 12px",
    color: "#cbd5e1",
    fontSize: 12,
    fontFamily: "monospace",
    outline: "none",
    resize: "vertical" as const,
  };
  const btnBase: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "7px 14px",
    borderRadius: 8,
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    border: "1px solid rgba(139,92,246,0.4)",
    background: "rgba(139,92,246,0.15)",
    color: "#c4b5fd",
    transition: "all 0.15s",
  };
  const btnDisabled: React.CSSProperties = {
    opacity: 0.4,
    cursor: "not-allowed",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 10,
          background: "rgba(139,92,246,0.15)",
          border: "1px solid rgba(139,92,246,0.3)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <Fingerprint style={{ width: 20, height: 20, color: "#a78bfa" }} />
        </div>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9" }}>Fingerprint Manager</div>
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
            Upload browser fingerprints — workers automatically pick a random enabled one each run
          </div>
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {[
          { label: "Total", value: records.length, color: "#cbd5e1" },
          { label: "Enabled", value: enabledCount, color: "#34d399" },
          { label: "Oldest", value: records.length ? ageDays(records[0]?.createdAt) : "—", color: "#a78bfa" },
        ].map(s => (
          <div key={s.label} style={{ ...cardStyle, padding: 16, textAlign: "center" }}>
            <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "monospace", color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 10, color: "#475569", textTransform: "uppercase", letterSpacing: "0.1em", marginTop: 4 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Upload panel */}
      <div style={{ ...cardStyle, padding: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <Upload style={{ width: 16, height: 16, color: "#22d3ee" }} />
          <span style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>Add Fingerprints</span>
        </div>

        {/* Tab selector */}
        <div style={{
          display: "inline-flex", gap: 4, padding: 4,
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 10, marginBottom: 16,
        }}>
          {(["single", "bulk"] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                padding: "6px 16px",
                borderRadius: 7,
                fontSize: 12,
                fontWeight: 500,
                cursor: "pointer",
                border: tab === t ? "1px solid rgba(139,92,246,0.3)" : "1px solid transparent",
                background: tab === t ? "rgba(139,92,246,0.2)" : "transparent",
                color: tab === t ? "#c4b5fd" : "#64748b",
                transition: "all 0.15s",
              }}
            >
              {t === "single" ? "Single" : "Bulk (.txt)"}
            </button>
          ))}
        </div>

        {tab === "single" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <textarea
              value={singleText}
              onChange={e => setSingleText(e.target.value)}
              placeholder='Paste fingerprint JSON here, e.g. {"userAgent":"Mozilla/5.0...","screen":{"width":1920,"height":1080},...}'
              rows={5}
              style={inputStyle}
            />
            <button
              onClick={addSingle}
              disabled={!singleText.trim() || submitting}
              style={{ ...btnBase, ...(!singleText.trim() || submitting ? btnDisabled : {}) }}
            >
              <Plus style={{ width: 14, height: 14 }} />
              {submitting ? "Adding..." : "Add Fingerprint"}
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{
              display: "flex", alignItems: "flex-start", gap: 8, padding: 10,
              background: "rgba(245,158,11,0.06)",
              border: "1px solid rgba(245,158,11,0.2)",
              borderRadius: 8,
            }}>
              <AlertTriangle style={{ width: 14, height: 14, color: "#fbbf24", flexShrink: 0, marginTop: 1 }} />
              <span style={{ fontSize: 12, color: "rgba(253,230,138,0.8)" }}>One fingerprint JSON per line in the .txt file, or paste below.</span>
            </div>
            <textarea
              value={bulkText}
              onChange={e => setBulkText(e.target.value)}
              placeholder={"Line 1: {\"userAgent\":\"Mozilla/5.0...\"}\nLine 2: {\"userAgent\":\"Mozilla/5.0...\"}"}
              rows={6}
              style={inputStyle}
            />
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button
                onClick={() => addBulk(bulkText.split("\n"))}
                disabled={!bulkText.trim() || submitting}
                style={{ ...btnBase, ...(!bulkText.trim() || submitting ? btnDisabled : {}) }}
              >
                <Plus style={{ width: 14, height: 14 }} />
                Add from text
              </button>
              <button
                onClick={() => fileRef.current?.click()}
                disabled={submitting}
                style={{ ...btnBase, ...(submitting ? btnDisabled : {}) }}
              >
                <FileText style={{ width: 14, height: 14 }} />
                Upload .txt file
              </button>
              <input
                ref={fileRef}
                type="file"
                accept=".txt,text/plain"
                style={{ display: "none" }}
                onChange={handleFileUpload}
              />
            </div>
          </div>
        )}
      </div>

      {/* Fingerprint list */}
      <div style={{ ...cardStyle, padding: 20 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Fingerprint style={{ width: 16, height: 16, color: "#a78bfa" }} />
            <span style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>Fingerprint Pool</span>
            <span style={{ fontSize: 11, color: "#475569", fontFamily: "monospace" }}>
              {records.length} total · {enabledCount} enabled
            </span>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              onClick={load}
              style={{
                width: 30, height: 30, borderRadius: 8,
                background: "transparent", border: "none",
                display: "flex", alignItems: "center", justifyContent: "center",
                cursor: "pointer", color: "#475569",
              }}
              title="Refresh"
            >
              <RefreshCw style={{ width: 14, height: 14, animation: loading ? "spin 1s linear infinite" : "none" }} />
            </button>
            {records.length > 0 && (
              <button
                onClick={clearAll}
                style={{
                  width: 30, height: 30, borderRadius: 8,
                  background: "transparent", border: "none",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  cursor: "pointer", color: "#475569",
                }}
                title="Clear all"
              >
                <Trash2 style={{ width: 14, height: 14 }} />
              </button>
            )}
          </div>
        </div>

        {loadError ? (
          <div style={{
            display: "flex", alignItems: "flex-start", gap: 12, padding: 16,
            background: "rgba(239,68,68,0.06)",
            border: "1px solid rgba(239,68,68,0.2)",
            borderRadius: 10,
          }}>
            <AlertTriangle style={{ width: 16, height: 16, color: "#f87171", flexShrink: 0, marginTop: 2 }} />
            <div>
              <div style={{ fontSize: 14, fontWeight: 500, color: "#fca5a5" }}>Failed to load fingerprints</div>
              <div style={{ fontSize: 11, color: "rgba(252,165,165,0.7)", fontFamily: "monospace", marginTop: 4 }}>{loadError}</div>
              <button
                onClick={load}
                style={{
                  marginTop: 8, fontSize: 11, color: "#fca5a5",
                  background: "none", border: "none", cursor: "pointer",
                  textDecoration: "underline", padding: 0,
                }}
              >
                Retry
              </button>
            </div>
          </div>
        ) : records.length === 0 ? (
          <div style={{ textAlign: "center", padding: "48px 0", color: "#334155" }}>
            <Fingerprint style={{ width: 40, height: 40, margin: "0 auto 12px", opacity: 0.3 }} />
            <div style={{ fontSize: 14, marginBottom: 4 }}>No fingerprints uploaded yet</div>
            <div style={{ fontSize: 12, color: "#1e293b" }}>Workers will use local generation until you add fingerprints here</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 420, overflowY: "auto" }}>
            {records.map(fp => (
              <div
                key={fp.id}
                style={{
                  display: "flex", alignItems: "center", gap: 12, padding: 12,
                  borderRadius: 10,
                  background: fp.enabled ? "rgba(16,185,129,0.04)" : "rgba(255,255,255,0.02)",
                  border: fp.enabled ? "1px solid rgba(16,185,129,0.15)" : "1px solid rgba(255,255,255,0.06)",
                  opacity: fp.enabled ? 1 : 0.55,
                  transition: "all 0.2s",
                }}
              >
                <button
                  onClick={() => toggleRecord(fp.id, fp.enabled)}
                  style={{ background: "none", border: "none", cursor: "pointer", flexShrink: 0, padding: 0 }}
                >
                  {fp.enabled
                    ? <ToggleRight style={{ width: 22, height: 22, color: "#34d399" }} />
                    : <ToggleLeft style={{ width: 22, height: 22, color: "#334155" }} />}
                </button>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11, fontFamily: "monospace", color: "#94a3b8", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {fp.data}
                  </div>
                  <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
                    <span style={{ fontSize: 10, color: "#334155" }}>#{fp.id}</span>
                    <span style={{ fontSize: 10, color: "#334155" }}>Added {ageDays(fp.createdAt)}</span>
                    <span style={{ fontSize: 10, fontWeight: 600, color: fp.enabled ? "#34d399" : "#334155" }}>
                      {fp.enabled ? "ACTIVE" : "DISABLED"}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => deleteRecord(fp.id)}
                  style={{
                    flexShrink: 0, width: 28, height: 28, borderRadius: 6,
                    background: "none", border: "none", cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    color: "#334155",
                  }}
                >
                  <Trash2 style={{ width: 13, height: 13 }} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Info box */}
      <div style={{ ...cardStyle, padding: 16 }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
          <AlertTriangle style={{ width: 16, height: 16, color: "#a78bfa", flexShrink: 0, marginTop: 2 }} />
          <div style={{ fontSize: 12, color: "#64748b", lineHeight: 1.6 }}>
            <div style={{ color: "#e2e8f0", fontWeight: 600, marginBottom: 4 }}>How workers use fingerprints</div>
            <p>Each worker session picks a random <span style={{ color: "#34d399", fontFamily: "monospace" }}>ACTIVE</span> fingerprint and injects it into the browser before Discord loads. Discord's fraud detection sees a known fingerprint with history rather than a brand-new one.</p>
            <p style={{ marginTop: 6, color: "#a78bfa" }}>The older the fingerprint creation date, the more aged the account appears to Discord.</p>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
