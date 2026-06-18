import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "./authStore";

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(globalThis, "localStorage", {
  value: localStorageMock,
});

describe("authStore", () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({
      token: null,
      user: null,
      isAuthenticated: false,
    });
  });

  it("starts unauthenticated", () => {
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
  });

  it("setAuth stores token and user", () => {
    const mockUser = {
      id: "1",
      username: "perito01",
      email: "p@pf.gov.br",
      role: "perito" as const,
      is_active: true,
      password_set: true,
    };
    useAuthStore.getState().setAuth("fake-token", mockUser);

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.token).toBe("fake-token");
    expect(state.user).toEqual(mockUser);
    expect(localStorage.getItem("va_access_token")).toBe("fake-token");
  });

  it("logout clears state and storage", () => {
    useAuthStore.getState().setAuth("token", {
      id: "1",
      username: "u",
      email: "u@pf.gov.br",
      role: "perito",
      is_active: true,
      password_set: true,
    });
    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.token).toBeNull();
    expect(localStorage.getItem("va_access_token")).toBeNull();
  });
});
