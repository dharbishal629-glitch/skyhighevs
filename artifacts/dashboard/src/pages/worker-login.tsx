import React, { useState } from "react";
import { useLocation } from "wouter";
import { CONFIG } from "../lib/config";

const API_BASE = CONFIG.API_BASE_URL.replace(/\/$/, "");

export default function WorkerLogin() {
  const [key, setKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [, setLocation] = useLocation();

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/worker/me`, {
        headers: { "x-api-key": key.trim() },
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.error || "Invalid worker key");
        return;
      }
      sessionStorage.setItem("workerKey", key.trim());
      setLocation("/worker");
    } catch {
      setError("Cannot reach server — check your connection.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex items-center justify-center w-screen" style={{ minHeight: "100dvh", background: "hsl(228 30% 7%)" }}>
      <div style={{ width: "100%", maxWidth: 400, padding: "0 1.5rem" }}>
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-4"
            style={{ background: "linear-gradient(135deg, rgba(139,92,246,0.3), rgba(6,182,212,0.2))", border: "1px solid rgba(139,92,246,0.4)" }}>
            <span style={{ fontSize: 22 }}>⚡</span>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Worker Portal</h1>
          <p className="text-sm mt-1" style={{ color: "rgba(148,163,184,0.7)" }}>CTRL.PNL · Paste your Worker Key</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: "rgba(148,163,184,0.8)" }}>
              Worker Key
            </label>
            <input
              value={key}
              onChange={e => setKey(e.target.value)}
              placeholder="WK-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
              autoFocus
              className="w-full px-3 py-2.5 rounded-lg text-sm font-mono text-white placeholder-slate-600 outline-none transition-all"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: `1px solid ${error ? "rgba(239,68,68,0.5)" : "rgba(255,255,255,0.1)"}`,
              }}
              onFocus={e => (e.target.style.borderColor = "rgba(139,92,246,0.6)")}
              onBlur={e => (e.target.style.borderColor = error ? "rgba(239,68,68,0.5)" : "rgba(255,255,255,0.1)")}
            />
            {error && <p className="text-xs mt-1.5" style={{ color: "#ef4444" }}>{error}</p>}
          </div>

          <button
            type="submit"
            disabled={loading || !key.trim()}
            className="w-full py-2.5 rounded-lg text-sm font-semibold text-white transition-all"
            style={{
              background: loading || !key.trim()
                ? "rgba(139,92,246,0.3)"
                : "linear-gradient(135deg, #7c3aed, #2563eb)",
              cursor: loading || !key.trim() ? "not-allowed" : "pointer",
              border: "1px solid rgba(139,92,246,0.4)",
            }}
          >
            {loading ? "Verifying..." : "Access Portal →"}
          </button>
        </form>

        <p className="text-center text-xs mt-6" style={{ color: "rgba(100,116,139,0.6)" }}>
          Admin? <a href="/login" style={{ color: "rgba(139,92,246,0.8)" }}>Sign in here</a>
        </p>
      </div>
    </div>
  );
}
