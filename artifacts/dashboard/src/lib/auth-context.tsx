import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode, useRef } from "react";
import { generateTOTP } from "./totp";
import { CONFIG } from "./config";

export interface AppConfig {
  apiUrl: string;
  workerKey: string;
  totpSecret: string;
  mailProvider: string;
  mailApiKey: string;
  mailFromEmail: string;
  mailFromName: string;
  zeusEnabled: boolean;
  zeusApiKey: string;
}

const CONFIG_DEFAULTS: AppConfig = {
  apiUrl: CONFIG.API_BASE_URL,
  workerKey: CONFIG.API_KEY || "",
  totpSecret: CONFIG.TOTP_SECRET || "",
  mailProvider: "",
  mailApiKey: "",
  mailFromEmail: "",
  mailFromName: "",
  zeusEnabled: false,
  zeusApiKey: "",
};

const SESSION_KEY = "ctrlpnl_admin_key";

function loadConfig(): AppConfig {
  try {
    const raw = localStorage.getItem("app_config");
    if (raw) {
      const saved = JSON.parse(raw) as Partial<AppConfig>;
      if (CONFIG.API_BASE_URL) saved.apiUrl = CONFIG.API_BASE_URL;
      return { ...CONFIG_DEFAULTS, ...saved };
    }
  } catch {}
  return CONFIG_DEFAULTS;
}

function saveConfig(cfg: AppConfig) {
  localStorage.setItem("app_config", JSON.stringify(cfg));
}

interface AuthState {
  config: AppConfig;
  saveAppConfig: (cfg: AppConfig) => void;
  adminKey: string;
  totpCode: string;
  autoTotpEnabled: boolean;
  isSetup: boolean;
  isAuthenticated: boolean;
  authReady: boolean;
  adminConfigured: boolean;
  checkAdminSetup: () => Promise<void>;
  login: (accessCode: string, manualTotpCode?: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  getHeaders: () => Record<string, string>;
  apiBaseUrl: string;
  apiKey: string;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig>(loadConfig);
  const [adminKey, setAdminKey] = useState<string>(() => {
    try { return sessionStorage.getItem(SESSION_KEY) || ""; } catch { return ""; }
  });
  const [totpCode, setTotpCode] = useState("");
  const [authReady, setAuthReady] = useState(false);
  // true = DB has an access code set, false = setup mode (no code yet)
  const [adminConfigured, setAdminConfigured] = useState(true);

  const totpSecretRef = useRef(config.totpSecret);
  totpSecretRef.current = config.totpSecret;
  const adminKeyRef = useRef(adminKey);
  adminKeyRef.current = adminKey;

  const autoTotpEnabled = Boolean(config.totpSecret);
  const isSetup = Boolean(config.workerKey && config.totpSecret);
  const isAuthenticated = Boolean(adminKey);

  useEffect(() => { setAuthReady(true); }, []);

  // TOTP code — only updates state when the 30-second period changes
  useEffect(() => {
    let lastPeriod = -1;
    const tick = async () => {
      if (!totpSecretRef.current) return;
      const period = Math.floor(Date.now() / 1000 / 30);
      if (period !== lastPeriod) {
        lastPeriod = period;
        const code = await generateTOTP(totpSecretRef.current);
        if (code) setTotpCode(code);
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => clearInterval(id);
  }, [config.totpSecret]);

  const checkAdminSetup = useCallback(async () => {
    if (!config.apiUrl) return;
    try {
      const res = await fetch(`${config.apiUrl.replace(/\/$/, "")}/api/admin/status`);
      if (res.ok) {
        const data = await res.json();
        setAdminConfigured(data.configured === true);
      }
    } catch {
      // Network error — assume configured to avoid showing setup form on bad connection
      setAdminConfigured(true);
    }
  }, [config.apiUrl]);

  // Check on mount
  useEffect(() => {
    if (config.apiUrl) checkAdminSetup();
  }, [config.apiUrl]);

  const saveAppConfig = useCallback((cfg: AppConfig) => {
    saveConfig(cfg);
    setConfig(cfg);
  }, []);

  const login = useCallback(async (accessCode: string, manualTotpCode?: string) => {
    const secret = config.totpSecret;
    const code = manualTotpCode || (secret ? await generateTOTP(secret) : "");
    if (!code) return { success: false, error: "No 2FA code available. Save your TOTP Secret in Config first." };

    const baseUrl = config.apiUrl.replace(/\/$/, "");
    try {
      const res = await fetch(`${baseUrl}/api/dashboard/stats`, {
        headers: {
          "x-api-key": config.workerKey,
          "x-admin-key": accessCode,
          "x-totp-code": code,
        },
      });
      if (res.status === 401) return { success: false, error: "Wrong 2FA code. Try again." };
      if (res.status === 403) return { success: false, error: "Wrong access code. Try again." };
      if (!res.ok) return { success: false, error: `Server error (HTTP ${res.status}).` };
      setAdminKey(accessCode);
      setTotpCode(code);
      try { sessionStorage.setItem(SESSION_KEY, accessCode); } catch {}
      return { success: true };
    } catch {
      return { success: false, error: "Could not reach the API server. Check your connection." };
    }
  }, [config]);

  const logout = useCallback(() => {
    setAdminKey("");
    setTotpCode("");
    try { sessionStorage.removeItem(SESSION_KEY); } catch {}
  }, []);

  const getHeaders = useCallback(() => ({
    "x-api-key": config.workerKey,
    "x-admin-key": adminKeyRef.current,
    "x-totp-code": totpCode,
  }), [config.workerKey, totpCode]);

  return (
    <AuthContext.Provider value={{
      config, saveAppConfig,
      adminKey, totpCode,
      autoTotpEnabled, isSetup, isAuthenticated, authReady,
      adminConfigured, checkAdminSetup,
      login, logout, getHeaders,
      apiBaseUrl: config.apiUrl,
      apiKey: config.workerKey,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

// Standalone hook for the TOTP countdown — use this only in display components.
export function useTotpTimer() {
  const [timeLeft, setTimeLeft] = useState(() => 30 - (Math.floor(Date.now() / 1000) % 30));
  useEffect(() => {
    const id = setInterval(() => {
      setTimeLeft(30 - (Math.floor(Date.now() / 1000) % 30));
    }, 1000);
    return () => clearInterval(id);
  }, []);
  return timeLeft;
}
