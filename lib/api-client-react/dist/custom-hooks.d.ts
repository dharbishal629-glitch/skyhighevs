import type { UseQueryOptions, UseMutationOptions } from "@tanstack/react-query";
import { customFetch } from "./custom-fetch";
type RequestInit2 = Parameters<typeof customFetch>[1];
interface QueryOpts<TData> {
    request?: RequestInit2;
    query?: UseQueryOptions<TData, Error>;
}
interface MutationOpts<TData, TVariables> {
    request?: RequestInit2;
    mutation?: UseMutationOptions<TData, Error, TVariables>;
}
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
export declare function useGetDashboardStats(options?: QueryOpts<DashboardStats>): import("@tanstack/react-query").UseQueryResult<DashboardStats, Error>;
export declare function useListWorkers(options?: QueryOpts<{
    workers: Worker[];
}>): import("@tanstack/react-query").UseQueryResult<{
    workers: Worker[];
}, Error>;
export declare function useGetLeaderboard(options?: QueryOpts<{
    leaderboard: LeaderboardEntry[];
}>): import("@tanstack/react-query").UseQueryResult<{
    leaderboard: LeaderboardEntry[];
}, Error>;
export declare function useFetchTokens(params?: {
    status?: string;
    discordId?: string;
}, options?: QueryOpts<{
    tokens: Token[];
}>): import("@tanstack/react-query").UseQueryResult<{
    tokens: Token[];
}, Error>;
interface CreateWorkerPayload {
    data: {
        discordId: string;
        discordUsername: string;
        durationDays?: number;
    };
}
export declare function useCreateWorkerKey(options?: MutationOpts<{
    workerKey: string;
    discordId: string;
}, CreateWorkerPayload>): import("@tanstack/react-query").UseMutationResult<{
    workerKey: string;
    discordId: string;
}, Error, CreateWorkerPayload, unknown>;
interface DeleteWorkerPayload {
    data: {
        discordId: string;
    };
}
export declare function useDeleteWorkerKey(options?: MutationOpts<{
    success: boolean;
}, DeleteWorkerPayload>): import("@tanstack/react-query").UseMutationResult<{
    success: boolean;
}, Error, DeleteWorkerPayload, unknown>;
export {};
//# sourceMappingURL=custom-hooks.d.ts.map