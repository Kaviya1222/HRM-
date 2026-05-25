import { createContext, useEffect, useState } from "react";
import { getCurrentUser, login as loginRequest, logout as logoutRequest, refreshTokens } from "../api/authApi";
import { isSuperAdminUser } from "../permissions/roles";
import { clearSessionTokens, getAccessToken, getRefreshToken, setSessionTokens } from "../utils/tokenStorage";

export const AuthContext = createContext(null);
const PERMISSIONS_UPDATED_AT_KEY = "hrm:permissions-updated-at";
const PERMISSIONS_UPDATED_EVENT = "hrm:permissions-updated";

function getModuleNameForPermission(permissionKey) {
  if (!permissionKey || permissionKey === "*") {
    return null;
  }
  const parts = permissionKey.split(".");
  if (parts.length < 2) {
    return null;
  }
  if (["module", "menu", "page"].includes(parts[0])) {
    return parts[1];
  }
  if (parts[0] === "users") {
    return "settings";
  }
  return parts[0];
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function bootstrapSession() {
      const accessToken = getAccessToken();
      const refreshToken = getRefreshToken();

      if (!accessToken && !refreshToken) {
        setIsBootstrapping(false);
        return;
      }

      try {
        if (!accessToken && refreshToken) {
          const refreshed = await refreshTokens(refreshToken);
          setSessionTokens(refreshed);
          if (isMounted) {
            setUser(refreshed.user);
          }
        } else {
          const currentUser = await getCurrentUser();
          if (isMounted) {
            setUser(currentUser);
          }
        }
      } catch (error) {
        clearSessionTokens();
        if (isMounted) {
          setUser(null);
        }
      } finally {
        if (isMounted) {
          setIsBootstrapping(false);
        }
      }
    }

    bootstrapSession();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!getAccessToken()) {
      return undefined;
    }

    let isDisposed = false;
    async function syncPermissions() {
      if (isDisposed || !getAccessToken()) {
        return;
      }
      try {
        const currentUser = await getCurrentUser();
        if (!isDisposed) {
          setUser(currentUser);
        }
      } catch (_error) {
        // Let normal auth flow handle expired sessions elsewhere.
      }
    }

    function handlePermissionRefresh() {
      void syncPermissions();
    }

    function handleStorage(event) {
      if (event.key === PERMISSIONS_UPDATED_AT_KEY) {
        void syncPermissions();
      }
    }

    window.addEventListener(PERMISSIONS_UPDATED_EVENT, handlePermissionRefresh);
    window.addEventListener("storage", handleStorage);
    return () => {
      isDisposed = true;
      window.removeEventListener(PERMISSIONS_UPDATED_EVENT, handlePermissionRefresh);
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  async function login(credentials) {
    const response = await loginRequest(credentials);
    setSessionTokens(response);
    setUser(response.user);
    return response;
  }

  async function logout() {
    try {
      if (getAccessToken()) {
        await logoutRequest({});
      }
    } finally {
      clearSessionTokens();
      setUser(null);
    }
  }

  async function refreshProfile() {
    const currentUser = await getCurrentUser();
    setUser(currentUser);
    return currentUser;
  }

  function hasPermission(permissionKey) {
    if (!permissionKey) {
      return true;
    }
    if (!user) {
      return false;
    }
    if (isSuperAdminUser(user) || user.permissions.includes("*")) {
      return true;
    }
    const moduleName = getModuleNameForPermission(permissionKey);
    if (moduleName && !user.permissions.includes(`module.${moduleName}.access`)) {
      return false;
    }
    return user.permissions.includes(permissionKey);
  }

  const value = {
    user,
    isBootstrapping,
    isAuthenticated: Boolean(user && getAccessToken()),
    login,
    logout,
    refreshProfile,
    hasPermission,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
