/** Unified React Query cache key taxonomy for ParkWise. */

export const queryKeys = {
  summary: ["summary"] as const,
  analytics: ["analytics"] as const,
  activity: ["activity"] as const,
  config: ["config", "public"] as const,
  videos: {
    all: ["videos"] as const,
    list: (limit = 50, offset = 0) => ["videos", "list", { limit, offset }] as const,
    detail: (id: string) => ["videos", "detail", id] as const,
    spaces: (id: string) => ["videos", "spaces", id] as const,
    occupancy: (id: string) => ["videos", "occupancy", id] as const,
    detections: (id: string) => ["videos", "detections", id] as const,
  },
  streams: {
    all: ["streams"] as const,
    list: ["streams", "list"] as const,
    detail: (id: string) => ["streams", "detail", id] as const,
  },
  settings: {
    all: ["settings"] as const,
    billing: ["settings", "billing"] as const,
    users: ["settings", "users"] as const,
    system: ["settings", "system"] as const,
  },
  publicSources: ["public-sources"] as const,
};
