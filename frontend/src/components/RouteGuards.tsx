// AI-assisted (OpenCode + Claude): route guards for authenticated and
// admin-only routes. Client-side gating is UX only. Reviewed by authors.
import { Center, Loader } from "@mantine/core";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../lib/auth";

function FullPageLoader() {
  return (
    <Center h="60vh">
      <Loader />
    </Center>
  );
}

export function ProtectedRoute() {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();
  if (loading) return <FullPageLoader />;
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

export function AdminRoute() {
  const { isAuthenticated, isAdmin, loading } = useAuth();
  if (loading) return <FullPageLoader />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (!isAdmin) return <Navigate to="/suppliers" replace />;
  return <Outlet />;
}
