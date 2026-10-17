// AI-assisted (OpenCode + Claude): application routes. Auth pages are public;
// everything else is behind the auth guard, with admin-only sections behind the
// admin guard. Reviewed by authors.
import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { AdminRoute, ProtectedRoute } from "./components/RouteGuards";
import Profile from "./pages/Profile";
import AdminClients from "./pages/admin/AdminClients";
import AdminSuppliers from "./pages/admin/AdminSuppliers";
import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import VerifyOtp from "./pages/auth/VerifyOtp";
import SupplierDetail from "./pages/suppliers/SupplierDetail";
import SupplierList from "./pages/suppliers/SupplierList";

export default function App() {
  return (
    <Routes>
      {/* Public auth routes */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/verify-otp" element={<VerifyOtp />} />

      {/* Authenticated app */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/suppliers" replace />} />
          <Route path="/suppliers" element={<SupplierList />} />
          <Route path="/suppliers/:id" element={<SupplierDetail />} />
          <Route path="/profile" element={<Profile />} />

          {/* Admin-only */}
          <Route element={<AdminRoute />}>
            <Route path="/admin/suppliers" element={<AdminSuppliers />} />
            <Route path="/admin/clients" element={<AdminClients />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/suppliers" replace />} />
    </Routes>
  );
}
