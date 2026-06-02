import { createRoot } from "react-dom/client";
import { setBaseUrl } from "@/lib/api-client";
import App from "./App";
import { CONFIG } from "./lib/config";
import "./index.css";

// Point all generated API hooks at the configured backend.
// In split deployments (dashboard on a different domain than the API)
// this is what makes /api/* calls actually reach the API server.
if (CONFIG.API_BASE_URL) {
  setBaseUrl(CONFIG.API_BASE_URL);
}

// The API authenticates admin requests via the `x-admin-key` header.
// Inject it globally so every fetch (incl. generated hooks) carries it.
const _origFetch = window.fetch.bind(window);
window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const headers = new Headers(init.headers);
  if (CONFIG.ADMIN_KEY && !headers.has("x-admin-key")) {
    headers.set("x-admin-key", CONFIG.ADMIN_KEY);
  }
  if (CONFIG.API_KEY && !headers.has("x-api-key")) {
    headers.set("x-api-key", CONFIG.API_KEY);
  }
  return _origFetch(input, { ...init, headers });
};

createRoot(document.getElementById("root")!).render(<App />);
