import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

import { useToast } from "@/app/providers/ToastProvider";
import { registerClientHandlers } from "@/shared/api/client";
import { login, me, register } from "@/shared/api/authApi";
import { runtimeConfig } from "@/shared/config/runtime";
import { MeResponse } from "@/shared/api/types";
import {
  clearSessionStorage,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from "@/shared/utils/storage";

type AuthContextType = {
  user: MeResponse | null;
  isAuthenticated: boolean;
  isBootstrapping: boolean;
  loginWithPassword: (email: string, password: string) => Promise<void>;
  registerUser: (
    email: string,
    password: string,
    fullName: string,
    companyName: string,
    tenantId?: string
  ) => Promise<string>;
  logout: () => void;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const { pushToast } = useToast();
  const [user, setUser] = useState<MeResponse | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const inactivityTimer = useRef<number | null>(null);

  const logout = (): void => {
    clearSessionStorage();
    setUser(null);
    window.location.assign("/auth");
  };

  useEffect(() => {
    registerClientHandlers({
      onLogout: logout,
      onApiError: (message) => pushToast(message, "error"),
    });
  }, [pushToast]);

  useEffect(() => {
    const resetTimer = () => {
      if (inactivityTimer.current) {
        window.clearTimeout(inactivityTimer.current);
      }

      inactivityTimer.current = window.setTimeout(() => {
        if (getAccessToken()) {
          pushToast("Session expired due to inactivity", "info");
          logout();
        }
      }, runtimeConfig.sessionInactivityMs);
    };

    const events: Array<keyof WindowEventMap> = ["mousemove", "keydown", "click", "scroll"];

    for (const eventName of events) {
      window.addEventListener(eventName, resetTimer);
    }

    resetTimer();

    return () => {
      for (const eventName of events) {
        window.removeEventListener(eventName, resetTimer);
      }
      if (inactivityTimer.current) {
        window.clearTimeout(inactivityTimer.current);
      }
    };
  }, [pushToast]);

  const refreshMe = async (): Promise<void> => {
    const profile = await me();
    setUser(profile);
  };

  useEffect(() => {
    const bootstrap = async () => {
      const token = getAccessToken();
      if (!token) {
        setIsBootstrapping(false);
        return;
      }

      try {
        await refreshMe();
      } catch {
        clearSessionStorage();
      } finally {
        setIsBootstrapping(false);
      }
    };

    void bootstrap();
  }, []);

  const loginWithPassword = async (email: string, password: string): Promise<void> => {
    const response = await login({ email, password });
    setAccessToken(response.access_token);
    if (response.refresh_token) {
      setRefreshToken(response.refresh_token);
    }
    await refreshMe();
    pushToast("Logged in", "success");
  };

  const registerUser = async (
    email: string,
    password: string,
    fullName: string,
    companyName: string,
    tenantId?: string
  ): Promise<string> => {
    const result = await register({
      email,
      password,
      full_name: fullName,
      company_name: companyName,
      tenant_id: tenantId,
    });
    pushToast("Registration successful", "success");
    return result.tenant_id;
  };

  const value = useMemo<AuthContextType>(
    () => ({
      user,
      isAuthenticated: Boolean(getAccessToken() || getRefreshToken()) && !!user,
      isBootstrapping,
      loginWithPassword,
      registerUser,
      logout,
      refreshMe,
    }),
    [user, isBootstrapping]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
