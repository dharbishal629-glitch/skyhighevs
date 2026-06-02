import { useQuery, useMutation, UseQueryOptions, UseMutationOptions } from "@tanstack/react-query";

let _baseUrl = "";

export function setBaseUrl(url: string) {
  _baseUrl = url.replace(/\/$/, "");
}

function getBase() {
  return _baseUrl || "";
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getBase()}${path}`;
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

type RequestOpts = { headers?: Record<string, string> };

export interface DashboardStats {
  activeWorkers: number;
  totalWorkers: number;
  tokensToday: number;
  validToday: number;
  unlockRateToday: number;
  totalTokens: number;
  validTokens: number;
  lockedTokens: number;
  invalidTokens: number;
}

export interface Worker {
  id: string;
  discordId: string;
  discordUsername: string;
  workerKey: string;
  status: "VALID" | "LOCKED" | "EXPIRED";
  tokensGenerated: number;
  unlockRate: number;
  expiresAt: string | null;
}

export interface Token {
  id: string;
  token: string;
  email?: string;
  status: "VALID" | "LOCKED" | "INVALID";
  discordId?: string;
  discordUsername?: string;
  createdAt: string;
}

export interface LeaderboardEntry {
  rank: number;
  discordId: string;
  discordUsername: string;
  totalGenerated: number;
  totalValid: number;
  unlockRate: number;
}

export function useGetDashboardStats(opts: { request: RequestOpts }) {
  return useQuery<DashboardStats>({
    queryKey: ["/api/dashboard/stats", opts.request.headers],
    queryFn: () =>
      apiFetch<DashboardStats>("/api/dashboard/stats", {
        headers: opts.request.headers,
      }),
    retry: 1,
  });
}

export function useListWorkers(opts: { request: RequestOpts }) {
  return useQuery<{ workers: Worker[] }>({
    queryKey: ["/api/workers/list", opts.request.headers],
    queryFn: () =>
      apiFetch<{ workers: Worker[] }>("/api/workers/list", {
        headers: opts.request.headers,
      }),
    retry: 1,
  });
}

export function useFetchTokens(
  filters: { status?: string; discordId?: string },
  opts: { request: RequestOpts }
) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.discordId) params.set("discordId", filters.discordId);
  const qs = params.toString();
  return useQuery<{ tokens: Token[] }>({
    queryKey: ["/api/tokens", filters, opts.request.headers],
    queryFn: () =>
      apiFetch<{ tokens: Token[] }>(`/api/tokens${qs ? `?${qs}` : ""}`, {
        headers: opts.request.headers,
      }),
    retry: 1,
  });
}

export function useGetLeaderboard(opts: { request: RequestOpts }) {
  return useQuery<{ leaderboard: LeaderboardEntry[] }>({
    queryKey: ["/api/leaderboard", opts.request.headers],
    queryFn: () =>
      apiFetch<{ leaderboard: LeaderboardEntry[] }>("/api/leaderboard", {
        headers: opts.request.headers,
      }),
    retry: 1,
  });
}

export function useCreateWorkerKey(opts: {
  request: RequestOpts;
  mutation?: { onSuccess?: () => void };
}) {
  return useMutation<
    unknown,
    Error,
    { data: { discordId: string; discordUsername: string; durationDays?: number | null } }
  >({
    mutationFn: ({ data }) =>
      apiFetch("/api/workers/create", {
        method: "POST",
        headers: { ...opts.request.headers, "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
    onSuccess: opts.mutation?.onSuccess,
  });
}

export function useDeleteWorkerKey(opts: {
  request: RequestOpts;
  mutation?: { onSuccess?: () => void };
}) {
  return useMutation<unknown, Error, { data: { discordId: string } }>({
    mutationFn: ({ data }) =>
      apiFetch("/api/workers/revoke", {
        method: "POST",
        headers: { ...opts.request.headers, "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
    onSuccess: opts.mutation?.onSuccess,
  });
}
