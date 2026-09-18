import { NavLink, Route, Routes } from "react-router-dom";
import Browse from "./pages/Browse";
import MyRequests from "./pages/MyRequests";
import NewRequest from "./pages/NewRequest";
import Deliveries from "./pages/Deliveries";
import Profile from "./pages/Profile";
import AdminDashboard from "./pages/admin/Dashboard";

export default function App() {
  return (
    <div>
      <nav className="nav">
        <strong>Campus Errands</strong>
        <NavLink to="/browse">Browse</NavLink>
        <NavLink to="/my-requests">My Requests</NavLink>
        <NavLink to="/new-request">New Request</NavLink>
        <NavLink to="/deliveries">Deliveries</NavLink>
        <NavLink to="/profile">Profile</NavLink>
        <NavLink to="/admin">Admin</NavLink>
      </nav>

      <main className="container">
        <Routes>
          <Route path="/" element={<Browse />} />
          <Route path="/browse" element={<Browse />} />
          <Route path="/my-requests" element={<MyRequests />} />
          <Route path="/new-request" element={<NewRequest />} />
          <Route path="/deliveries" element={<Deliveries />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/admin" element={<AdminDashboard />} />
        </Routes>
      </main>
    </div>
  );
}
