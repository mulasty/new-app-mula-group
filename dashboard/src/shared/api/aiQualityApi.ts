import { api } from "@/shared/api/client";

export type QualityEvaluation = {
  risk_score: number;
  tone_score: number;
  risk_flags: string[];
  needs_approval: boolean;
  metadata: Record<string, unknown>;
};

export async function evaluateQuality(projectId: string, title: string | undefined, body: string): Promise<QualityEvaluation> {
  const response = await api.post<QualityEvaluation>("/ai-quality/evaluate", {
    project_id: projectId,
    title,
    body,
  });
  return response.data;
}

export async function evaluateContentAndAttach(contentId: string): Promise<{ id: string; status: string; quality: Record<string, unknown> }> {
  const response = await api.post<{ id: string; status: string; quality: Record<string, unknown> }>(
    `/ai-quality/content/${contentId}/evaluate-and-attach`
  );
  return response.data;
}
