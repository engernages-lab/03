import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { HealthResponse, ReadinessResponse } from "./types";

export function useHealth() {
  return useQuery({
    queryKey: ["system", "health"],
    queryFn: () => api.get<HealthResponse>("/health"),
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}

export function useReadiness() {
  return useQuery({
    queryKey: ["system", "readiness"],
    queryFn: () => api.get<ReadinessResponse>("/health/ready"),
    refetchInterval: 30_000,
  });
}
