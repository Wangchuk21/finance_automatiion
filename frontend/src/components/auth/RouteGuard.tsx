"use client";

import { Navigate, useLocation, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

interface RouteGuardProps {
  allowedRoles?: string[];
  requirePasswordChange?: boolean;
  children?: React.ReactNode;
}

export function RouteGuard({ allowedRoles, requirePasswordChange = true, children }: RouteGuardProps) {
  const { user, isLoading, isAuthenticated, mustChangePassword } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-neutral-light/50">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (requirePasswordChange && mustChangePassword) {
    return <Navigate to="/set-password" state={{ from: location }} replace />;
  }

  if (allowedRoles && user && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return children ?? <Outlet />;
}

export function PublicOnlyGuard({ children }: { children?: React.ReactNode }) {
  const { isLoading, isAuthenticated } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-neutral-light/50">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return children ?? <Outlet />;
}