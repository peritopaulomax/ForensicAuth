import { create } from "zustand";
import { getCurrentUser } from "@/services/auth";
import type { User } from "@/types/api";

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  setAuth: (token: string, user: User) => void;
  logout: () => void;
  restoreSession: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isAuthenticated: false,

  setAuth: (token, user) => {
    localStorage.setItem("va_access_token", token);
    set({ token, user, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem("va_access_token");
    set({ token: null, user: null, isAuthenticated: false });
  },

  restoreSession: async () => {
    const token = localStorage.getItem("va_access_token");
    if (!token) {
      set({ token: null, user: null, isAuthenticated: false });
      return;
    }
    try {
      const user = await getCurrentUser();
      set({ token, user, isAuthenticated: true });
    } catch {
      localStorage.removeItem("va_access_token");
      set({ token: null, user: null, isAuthenticated: false });
    }
  },
}));
