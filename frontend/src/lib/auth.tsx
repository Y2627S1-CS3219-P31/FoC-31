// AI-assisted (OpenCode + Claude): auth context storing the JWT bearer token
// and hydrating the current profile. Client-side role is UX only; the server
// remains the source of truth for authorization. Reviewed by authors.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { authApi, getToken, setToken } from "./api";
import type { ProfileResponse, Role } from "./types";

interface AuthState {
  token: string | null;
  user: ProfileResponse | null;
  role: Role | null;
  loading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<ProfileResponse>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

function decodeRole(token: string): Role | null {
  try {
    const [, payload] = token.split(".");
    const json = JSON.parse(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
    );
    return (json.role as Role) ?? null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(getToken());
  const [user, setUser] = useState<ProfileResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(getToken()));

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const profile = await authApi.me();
      setUser(profile);
    } catch {
      // Token invalid/expired — clear it.
      setToken(null);
      setTokenState(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await authApi.login(email, password);
    setToken(access_token);
    setTokenState(access_token);
    const profile = await authApi.me();
    setUser(profile);
    setLoading(false);
    return profile;
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setTokenState(null);
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(() => {
    const role = user?.role ?? (token ? decodeRole(token) : null);
    return {
      token,
      user,
      role,
      loading,
      isAuthenticated: Boolean(token),
      isAdmin: role === "admin",
      login,
      logout,
      refresh,
    };
  }, [token, user, loading, login, logout, refresh]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
