import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "@/app/providers/AuthProvider";

export function ProtectedRoute(): JSX.Element {
  const { isAuthenticated, isBootstrapping } = useAuth();

  if (isBootstrapping) {
    return <div className="grid min-h-screen place-items-center text-slate-600">Loading session...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/auth" replace />;
  }

  return <Outlet />;
}
