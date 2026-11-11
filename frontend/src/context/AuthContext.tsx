import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { authApi, type MeResponse, type LoginResponse, type ChangePasswordResponse } from "@/lib/api";

interface AuthContextType {
  user: MeResponse | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  mustChangePassword: boolean;
  login: (username: string, password: string) => Promise<LoginResponse>;
  changePassword: (currentPassword: string, newPassword: string, confirmPassword: string) => Promise<ChangePasswordResponse>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  error: Error | null;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const isAuthenticated = !!user;
  const mustChangePassword = user?.must_change_password ?? false;

  const refreshUser = useCallback(async () => {
    try {
      const response = await authApi.me();
      setUser(response);
      setError(null);
    } catch (err) {
      setUser(null);
      setError(err instanceof Error ? err : new Error("Auth check failed"));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (username: string, password: string): Promise<LoginResponse> => {
    const response = await authApi.login({ username, password });
    // API sets cookies automatically
    await refreshUser();
    return response;
  };

  const changePassword = async (
    currentPassword: string,
    newPassword: string,
    confirmPassword: string
  ): Promise<ChangePasswordResponse> => {
    const response = await authApi.changePassword({
      current_password: currentPassword,
      new_password: newPassword,
      confirm_password: confirmPassword,
    });
    // Tokens rotated, user object updated
    await refreshUser();
    return response;
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } finally {
      // Clear local auth state even if the server call fails.
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated,
        mustChangePassword,
        login,
        changePassword,
        logout,
        refreshUser,
        error,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}