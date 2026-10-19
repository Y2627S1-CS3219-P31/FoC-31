// AI-assisted: application routes with lazy-loaded pages for orders, errands and deliveries.
import React from "react";
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

const BrowseErrands = React.lazy(() => import("./pages/errands/BrowseErrands"));
const CreateOrder = React.lazy(() => import("./pages/orders/CreateOrder"));
const MyRequests = React.lazy(() => import("./pages/orders/MyRequests"));
const MyDeliveries = React.lazy(() => import("./pages/deliveries/MyDeliveries"));
const OrderDetail = React.lazy(() => import("./pages/orders/OrderDetail"));

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
            <Route path="/errands" element={<BrowseErrands />} />
            <Route path="/orders/new" element={<CreateOrder />} />
            <Route path="/orders/mine" element={<MyRequests />} />
            <Route path="/deliveries" element={<MyDeliveries />} />
            <Route path="/orders/:id" element={<OrderDetail />} />

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
