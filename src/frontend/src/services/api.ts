import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

declare module "axios" {
  export interface AxiosRequestConfig {
    /** When true, a 401 response will not trigger refresh/logout/redirect. */
    skipAuthRedirect?: boolean;
  }
}

export type VaAxiosRequestConfig = InternalAxiosRequestConfig & {
  skipAuthRedirect?: boolean;
  _retry?: boolean;
};

const api = axios.create({
  baseURL: "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

/** Bare client without interceptors — used for refresh to avoid loops. */
const bareApi = axios.create({
  baseURL: "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

const ACCESS_KEY = "va_access_token";
const REFRESH_KEY = "va_refresh_token";

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  if (!refreshToken) return null;
  try {
    const { data } = await bareApi.post<{
      access_token: string;
      refresh_token: string;
      expires_in: number;
    }>("/auth/refresh", { refresh_token: refreshToken });
    localStorage.setItem(ACCESS_KEY, data.access_token);
    localStorage.setItem(REFRESH_KEY, data.refresh_token);
    return data.access_token;
  } catch {
    return null;
  }
}

/**
 * Clear session only if the access token that failed is still current.
 * Prevents a delayed 401-handler from wiping a brand-new login.
 */
function forceLogoutRedirect(failedAccessToken: string | null): void {
  void import("@/store/authStore").then(({ useAuthStore }) => {
    const currentAccess = localStorage.getItem(ACCESS_KEY);
    if (failedAccessToken && currentAccess && currentAccess !== failedAccessToken) {
      return;
    }
    useAuthStore.getState().clearSession();
    if (window.location.pathname !== "/login" && window.location.pathname !== "/primeiro-acesso") {
      window.location.href = "/login";
    }
  });
}

// Attach access JWT to every request if available.
// FormData must NOT keep the default application/json Content-Type —
// the browser/axios need to set multipart/form-data with boundary.
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(ACCESS_KEY);
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (typeof FormData !== "undefined" && config.data instanceof FormData && config.headers) {
    const headers = config.headers as { delete?: (key: string) => void; set?: (key: string, value?: string) => void };
    if (typeof headers.delete === "function") {
      headers.delete("Content-Type");
    } else {
      delete (config.headers as Record<string, unknown>)["Content-Type"];
      delete (config.headers as Record<string, unknown>)["content-type"];
    }
  }
  return config;
});

// On 401: single-flight refresh, then retry once; otherwise logout.
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as VaAxiosRequestConfig | undefined;
    if (!config || error.response?.status !== 401 || config.skipAuthRedirect) {
      return Promise.reject(error);
    }

    const requestUrl = config.url ?? "";
    if (/\/auth\/(login|refresh|logout|first-access)\b/.test(requestUrl)) {
      return Promise.reject(error);
    }

    const failedAccessToken = localStorage.getItem(ACCESS_KEY);

    if (config._retry) {
      forceLogoutRedirect(failedAccessToken);
      return Promise.reject(error);
    }

    config._retry = true;

    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
    }

    const newToken = await refreshPromise;
    if (!newToken) {
      forceLogoutRedirect(failedAccessToken);
      return Promise.reject(error);
    }

    if (config.headers) {
      config.headers.Authorization = `Bearer ${newToken}`;
    }
    return api(config);
  }
);

export default api;
