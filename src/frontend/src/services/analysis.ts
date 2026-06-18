import api from "./api";
import type { AnalysisJob, JobSubmitRequest, PluginInfo } from "@/types/api";

export async function listTechniques(): Promise<PluginInfo[]> {
  const response = await api.get<PluginInfo[]>("/analysis/techniques");
  return response.data;
}

export async function submitJob(request: JobSubmitRequest): Promise<AnalysisJob> {
  const response = await api.post<AnalysisJob>("/analysis/jobs", request);
  return response.data;
}

export async function getJob(jobId: string): Promise<AnalysisJob> {
  const response = await api.get<AnalysisJob>(`/analysis/jobs/${jobId}`);
  return response.data;
}
