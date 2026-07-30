import { create } from "zustand";
import { getCurrentUser, logoutRemote } from "@/services/auth";
import type { User } from "@/types/api";

const ACCESS_KEY = "va_access_token";
const REFRESH_KEY = "va_refresh_token";

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  setAuth: (accessToken: string, refreshToken: string, user: User) => void;
  clearSession: () => void;
  logout: () => void;
  restoreSession: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  refreshToken: null,
  user: null,
  isAuthenticated: false,

  setAuth: (accessToken, refreshToken, user) => {
    if (!accessToken || !refreshToken) {
      throw new Error("Resposta de login incompleta (access/refresh ausente)");
    }
    localStorage.setItem(ACCESS_KEY, accessToken);
    localStorage.setItem(REFRESH_KEY, refreshToken);
    set({
      token: accessToken,
      refreshToken,
      user,
      isAuthenticated: true,
    });
  },

  clearSession: () => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    set({ token: null, refreshToken: null, user: null, isAuthenticated: false });
  },

  logout: () => {
    const refresh = get().refreshToken ?? localStorage.getItem(REFRESH_KEY);
    get().clearSession();
    // Revoke after clearing local state so a slow response cannot race a new login.
    void logoutRemote(refresh);
  },

  restoreSession: async () => {
    const tokenAtStart = localStorage.getItem(ACCESS_KEY);
    const refreshAtStart = localStorage.getItem(REFRESH_KEY);
    if (!tokenAtStart && !refreshAtStart) {
      set({ token: null, refreshToken: null, user: null, isAuthenticated: false });
      return;
    }
    try {
      const user = await getCurrentUser();
      set({
        token: localStorage.getItem(ACCESS_KEY),
        refreshToken: localStorage.getItem(REFRESH_KEY),
        user,
        isAuthenticated: true,
      });
    } catch {
      // Do not wipe a session that was replaced (e.g. user logged in while restore ran).
      const tokenNow = localStorage.getItem(ACCESS_KEY);
      if (tokenNow && tokenAtStart && tokenNow !== tokenAtStart) {
        return;
      }
      localStorage.removeItem(ACCESS_KEY);
      localStorage.removeItem(REFRESH_KEY);
      set({ token: null, refreshToken: null, user: null, isAuthenticated: false });
    }
  },
}));
