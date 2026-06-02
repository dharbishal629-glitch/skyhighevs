export const CONFIG = {
  // Empty string ("") = same-origin (used in combined deployments where the
  // Express server also serves the dashboard). Falls back to the legacy
  // standalone Render URL only when the env var is undefined.
  API_BASE_URL:
    (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "",

  API_KEY: (import.meta.env.VITE_WORKER_API_KEY as string) || "",

  ADMIN_KEY: (import.meta.env.VITE_ADMIN_KEY as string) || "",

  TOTP_SECRET: (import.meta.env.VITE_TOTP_SECRET as string) || "",
};
