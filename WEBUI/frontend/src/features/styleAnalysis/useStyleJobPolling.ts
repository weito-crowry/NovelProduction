import { useQuery } from "@tanstack/react-query";
import { projectQueryKeys } from "../../api/queryKeys";
import { fetchStyleJob } from "./styleAnalysisApi";

const TERMINAL_STATUSES = new Set(["succeeded", "failed", "cancelled"]);

export function useStyleJobPolling(projectId: string, jobId: number | null) {
  return useQuery({
    queryKey:
      jobId === null
        ? projectQueryKeys.styleAnalysis(projectId, "no-job")
        : projectQueryKeys.styleJob(projectId, jobId),
    queryFn: () => fetchStyleJob(projectId, jobId as number),
    enabled: jobId !== null,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status !== undefined && TERMINAL_STATUSES.has(status) ? false : 1000;
    },
  });
}

export function isTerminalStyleJob(status: string | undefined): boolean {
  return status !== undefined && TERMINAL_STATUSES.has(status);
}
