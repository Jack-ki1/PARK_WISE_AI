"use client";

import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query-keys";
import { api } from "@/lib/api";
import type { Summary, AnalyticsPayload, ActivityItem, PublicConfig, VideoJob, StreamRow } from "@/lib/data";

export function useSummary() {
  return useQuery({
    queryKey: queryKeys.summary,
    queryFn: () => api.get<Summary>("/api/dashboard/summary"),
    refetchInterval: 10000,
    staleTime: 5000,
  });
}

export function useAnalytics() {
  return useQuery({
    queryKey: queryKeys.analytics,
    queryFn: () => api.get<AnalyticsPayload>("/api/dashboard/analytics"),
    refetchInterval: 15000,
    staleTime: 10000,
  });
}

export function useActivity(limit = 20) {
  return useQuery({
    queryKey: [...queryKeys.activity, limit],
    queryFn: () => api.get<ActivityItem[]>(`/api/activity?limit=${limit}`),
    refetchInterval: 15000,
  });
}

export function usePublicConfig() {
  return useQuery({
    queryKey: queryKeys.config,
    queryFn: () => api.get<PublicConfig>("/api/config/public"),
    staleTime: 60000,
  });
}

export function useVideos(limit = 100, offset = 0) {
  return useQuery({
    queryKey: queryKeys.videos.list(limit, offset),
    queryFn: () => api.get<VideoJob[]>(`/api/videos?limit=${limit}&offset=${offset}`),
    refetchInterval: (query) => {
      const data = query.state.data;
      const isPending = data?.some((v) => v.status === "queued" || v.status === "processing");
      return isPending ? 3000 : 30000;
    },
  });
}

export function useStreams() {
  return useQuery({
    queryKey: queryKeys.streams.all,
    queryFn: () => api.get<StreamRow[]>("/api/streams"),
    refetchInterval: 10000,
  });
}
