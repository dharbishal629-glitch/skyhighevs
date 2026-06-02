import { useQuery, useMutation } from "@tanstack/react-query";
import type { UseQueryOptions, UseMutationOptions } from "@tanstack/react-query";
import { customFetch } from "./custom-fetch";

type RequestInit2 = Parameters<typeof customFetch>[1];

// ── Shared option shapes ─────────────────────────────────────────────────────

interface QueryOpts<TData> {
  request?: RequestInit2;
  query?: UseQueryOptions<TData, Error>;
}

interface MutationOpts<TData, TVariables> {
  request?: RequestInit2;
  mutation?: UseMutationOptions<TData, Error, TVariables>;
}

// ── Types (matching api-server response shapes) ───────────────────────────────

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
  discordId: string;
  discordUsername: string;
  status: string;
  tokensGenerated: number;
  unlockRate: number;
  expiresAt: string | null;
  [key: string]: unknown;
}

export interface LeaderboardEntry {
  discordId: string;
  discordUsername: string;
  totalGenerated: number;
  validCount: number;
  unlockRate: number;
  rank: number;
}

export interface Token {
  id: number;
  token: string;
  email: string | null;
  status: string;
  discordId: string | null;
  createdAt: string;
  [key: string]: unknown;
}

// ── useGetDashboardStats ─────────────────────────────────────────────────────

export function useGetDashboardStats(options?: QueryOpts<DashboardStats>) {
  const { request, query } = options ?? {};
  return useQuery<DashboardStats, Error>({
    queryKey: ["/api/dashboard/stats", request?.headers],
    queryFn: () => customFetch<DashboardStats>("/api/dashboard/stats", { ...request, method: "GET" }),
    ...query,
  });
}

// ── useListWorkers ───────────────────────────────────────────────────────────

export function useListWorkers(options?: QueryOpts<{ workers: Worker[] }>) {
  const { request, query } = options ?? {};
  return useQuery<{ workers: Worker[] }, Error>({
    queryKey: ["/api/workers/list", request?.headers],
    queryFn: () => customFetch<{ workers: Worker[] }>("/api/workers/list", { ...request, method: "GET" }),
    ...query,
  });
}

// ── useGetLeaderboard ────────────────────────────────────────────────────────

export function useGetLeaderboard(options?: QueryOpts<{ leaderboard: LeaderboardEntry[] }>) {
  const { request, query } = options ?? {};
  return useQuery<{ leaderboard: LeaderboardEntry[] }, Error>({
    queryKey: ["/api/workers/leaderboard", request?.headers],
    queryFn: () => customFetch<{ leaderboard: LeaderboardEntry[] }>("/api/workers/leaderboard", { ...request, method: "GET" }),
    ...query,
  });
}

// ── useFetchTokens ───────────────────────────────────────────────────────────

export function useFetchTokens(
  params: { status?: string; discordId?: string } = {},
  options?: QueryOpts<{ tokens: Token[] }>
) {
  const { request, query } = options ?? {};
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.discordId) qs.set("discordId", params.discordId);
  const url = `/api/tokens/fetch${qs.toString() ? `?${qs}` : ""}`;

  return useQuery<{ tokens: Token[] }, Error>({
    queryKey: ["/api/tokens/fetch", params, request?.headers],
    queryFn: () => customFetch<{ tokens: Token[] }>(url, { ...request, method: "GET" }),
    ...query,
  });
}

// ── useCreateWorkerKey ───────────────────────────────────────────────────────

interface CreateWorkerPayload {
  data: { discordId: string; discordUsername: string; durationDays?: number };
}

export function useCreateWorkerKey(
  options?: MutationOpts<{ workerKey: string; discordId: string }, CreateWorkerPayload>
) {
  const { request, mutation } = options ?? {};
  return useMutation<{ workerKey: string; discordId: string }, Error, CreateWorkerPayload>({
    mutationFn: ({ data }) =>
      customFetch<{ workerKey: string; discordId: string }>("/api/workers/create-key", {
        ...request,
        method: "POST",
        body: JSON.stringify(data),
      }),
    ...mutation,
  });
}

// ── useDeleteWorkerKey ───────────────────────────────────────────────────────

interface DeleteWorkerPayload {
  data: { discordId: string };
}

export function useDeleteWorkerKey(
  options?: MutationOpts<{ success: boolean }, DeleteWorkerPayload>
) {
  const { request, mutation } = options ?? {};
  return useMutation<{ success: boolean }, Error, DeleteWorkerPayload>({
    mutationFn: ({ data }) =>
      customFetch<{ success: boolean }>("/api/workers/delete-key", {
        ...request,
        method: "DELETE",
        body: JSON.stringify(data),
      }),
    ...mutation,
  });
}
