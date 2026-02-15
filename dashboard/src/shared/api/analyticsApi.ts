import { api } from "@/shared/api/client";
import {
  ActivityStreamItem,
  PublishingSummary,
  PublishingTimeRange,
  PublishingTimeseriesPoint,
} from "@/shared/api/types";

type AnalyticsParams = {
  projectId?: string;
};

function withProjectParam(params: AnalyticsParams): Record<string, string> | undefined {
  if (!params.projectId) {
    return undefined;
  }
  return { project_id: params.projectId };
}

export async function getPublishingSummary(params: AnalyticsParams): Promise<PublishingSummary> {
  const response = await api.get<PublishingSummary>("/analytics/publishing-summary", {
    params: withProjectParam(params),
  });
  return response.data;
}

export async function getPublishingTimeseries(
  params: AnalyticsParams & { range: PublishingTimeRange }
): Promise<PublishingTimeseriesPoint[]> {
  const response = await api.get<PublishingTimeseriesPoint[]>("/analytics/publishing-timeseries", {
    params: {
      ...withProjectParam(params),
      range: params.range,
    },
  });
  return response.data;
}

export async function getActivityStream(
  params: AnalyticsParams & { limit?: number }
): Promise<ActivityStreamItem[]> {
  const response = await api.get<ActivityStreamItem[]>("/analytics/activity-stream", {
    params: {
      ...withProjectParam(params),
      ...(params.limit ? { limit: String(params.limit) } : {}),
    },
  });
  return response.data;
}
