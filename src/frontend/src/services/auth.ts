import api from "./api";
import type { AuthTokens, User } from "@/types/api";

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface FirstAccessCredentials {
  username: string;
  password: string;
  password_confirm: string;
}

export async function login(credentials: LoginCredentials): Promise<{ tokens: AuthTokens; user: User }> {
  try {
    const response = await api.post<AuthTokens & { user: User }>("/auth/login", credentials);
    return {
      tokens: {
        access_token: response.data.access_token,
        token_type: response.data.token_type,
      },
      user: response.data.user,
    };
  } catch (err: unknown) {
    const message = extractErrorMessage(err);
    throw new Error(message);
  }
}

export async function firstAccess(credentials: FirstAccessCredentials): Promise<User> {
  try {
    const response = await api.post<User>("/auth/first-access", credentials);
    return response.data;
  } catch (err: unknown) {
    const message = extractErrorMessage(err);
    throw new Error(message);
  }
}

export async function getCurrentUser(): Promise<User> {
  const response = await api.get<User>("/auth/me");
  return response.data;
}

function extractErrorMessage(err: unknown): string {
  if (err && typeof err === "object" && "response" in err) {
    const axiosErr = err as { response?: { data?: { detail?: unknown } }; message?: string };
    const detail = axiosErr.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail) return JSON.stringify(detail);
    return axiosErr.message || "Erro desconhecido";
  }
  if (err instanceof Error) return err.message;
  return "Erro desconhecido";
}
