import { Navigate, Outlet } from "react-router-dom";
import LoadingScreen from "../components/common/LoadingScreen";
import useAuth from "../hooks/useAuth";
import { isSuperAdminUser } from "../permissions/roles";

function ProtectedRoute({ permission, superAdminOnly = false, children }) {
  const { isAuthenticated, isBootstrapping, user, hasPermission } = useAuth();

  if (isBootstrapping) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <Navigate replace to="/login" />;
  }

  if (superAdminOnly && !isSuperAdminUser(user)) {
    return <Navigate replace to="/unauthorized" />;
  }

  if (permission && !hasPermission(permission)) {
    return <Navigate replace to="/unauthorized" />;
  }

  return children || <Outlet />;
}

export default ProtectedRoute;
