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
    const response = await api.post<AuthTokens & { user: User }>("/auth/login", credentials, {
      skipAuthRedirect: true,
    });
    const access_token = response.data.access_token;
    const refresh_token = response.data.refresh_token;
    if (!access_token || !refresh_token) {
      throw new Error("Resposta de login incompleta do servidor");
    }
    return {
      tokens: {
        access_token,
        refresh_token,
        token_type: response.data.token_type,
        expires_in: response.data.expires_in,
      },
      user: response.data.user,
    };
  } catch (err: unknown) {
    const message = extractErrorMessage(err);
    throw new Error(message);
  }
}

export async function refreshSession(refreshToken: string): Promise<AuthTokens> {
  const response = await api.post<AuthTokens>(
    "/auth/refresh",
    { refresh_token: refreshToken },
    { skipAuthRedirect: true }
  );
  return {
    access_token: response.data.access_token,
    refresh_token: response.data.refresh_token,
    token_type: response.data.token_type,
    expires_in: response.data.expires_in,
  };
}

export async function logoutRemote(refreshToken: string | null): Promise<void> {
  if (!refreshToken) return;
  try {
    await api.post("/auth/logout", { refresh_token: refreshToken }, { skipAuthRedirect: true });
  } catch {
    // Best-effort revocation; local session is cleared regardless.
  }
}

export async function firstAccess(credentials: FirstAccessCredentials): Promise<User> {
  try {
    const response = await api.post<User>("/auth/first-access", credentials, {
      skipAuthRedirect: true,
    });
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
