import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

type UsePublishingWatcherParams = {
  postId: string | undefined;
  tenantId?: string;
  projectId?: string;
  intervalMs?: number;
};

export function usePublishingWatcher({
  postId,
  tenantId,
  projectId,
  intervalMs = 15000,
}: UsePublishingWatcherParams): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!postId) {
      return;
    }

    const postsKey = tenantId && projectId ? ["posts", tenantId, projectId] : ["posts"];
    const timelineKey = tenantId ? ["postTimeline", tenantId, postId] : ["postTimeline", postId];

    const interval = window.setInterval(() => {
      queryClient.invalidateQueries({ queryKey: postsKey });
      queryClient.invalidateQueries({ queryKey: timelineKey });
    }, intervalMs);

    return () => window.clearInterval(interval);
  }, [postId, tenantId, projectId, intervalMs, queryClient]);
}
