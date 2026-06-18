import api from "@/services/api";
import type { CaseDetail } from "@/types/api";

export interface CaseShare {
  id: string;
  case_id: string;
  shared_with_user_id: string;
  shared_with_username?: string;
  role: "viewer" | "editor";
  shared_by: string;
  created_at: string;
}

export interface ShareableUser {
  id: string;
  username: string;
  email: string;
  role: string;
}

export async function listCaseShares(caseId: string): Promise<CaseShare[]> {
  const { data } = await api.get<CaseShare[]>(`/cases/${caseId}/shares`);
  return data;
}

export async function createCaseShare(
  caseId: string,
  userId: string,
  role: "viewer" | "editor"
): Promise<CaseShare> {
  const { data } = await api.post<CaseShare>(`/cases/${caseId}/shares`, {
    user_id: userId,
    role,
  });
  return data;
}

export async function revokeCaseShare(caseId: string, shareId: string): Promise<void> {
  await api.delete(`/cases/${caseId}/shares/${shareId}`);
}

export async function listSharedWithMe(): Promise<CaseDetail[]> {
  const { data } = await api.get("/cases/shared-with-me");
  return data;
}

export async function listUsersForSharing(): Promise<ShareableUser[]> {
  const { data } = await api.get<ShareableUser[]>("/users/for-sharing");
  return data;
}
