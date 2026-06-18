import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

declare module "axios" {
  export interface AxiosRequestConfig {
    /** When true, a 401 response will not trigger session logout/redirect. */
    skipAuthRedirect?: boolean;
  }
}

export type VaAxiosRequestConfig = InternalAxiosRequestConfig & {
  skipAuthRedirect?: boolean;
};

const api = axios.create({
  baseURL: "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

// Attach JWT token to every request if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("va_access_token");
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Only force logout/redirect when session validation fails (/auth/me).
// Other 401s are rejected to callers without clearing auth (avoids false "logout").
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const config = error.config as VaAxiosRequestConfig | undefined;
    if (error.response?.status === 401 && !config?.skipAuthRedirect) {
      const requestUrl = config?.url ?? "";
      const path = window.location.pathname;
      if (path !== "/login" && path !== "/primeiro-acesso" && /\/auth\/me\b/.test(requestUrl)) {
        void import("@/store/authStore").then(({ useAuthStore }) => {
          useAuthStore.getState().logout();
          window.location.href = "/login";
        });
      }
    }
    return Promise.reject(error);
  }
);

export default api;
