import { createContext, useCallback, useEffect, useMemo, useState } from "react";
import { fetchPublicBranding } from "../api/settingsApi";
import {
  BRANDING_STORAGE_KEY,
  buildBrandingIconDataUrl,
  DEFAULT_BRANDING,
  normalizeBranding,
  persistBranding,
  readStoredBranding,
} from "../utils/branding";

export const BrandingContext = createContext(null);

function applyFavicon(branding) {
  const href = buildBrandingIconDataUrl(branding);
  let icon = document.querySelector("link[rel='icon']");

  if (!icon) {
    icon = document.createElement("link");
    icon.setAttribute("rel", "icon");
    document.head.appendChild(icon);
  }

  icon.setAttribute("href", href);
}

export function BrandingProvider({ children }) {
  const [branding, setBrandingState] = useState(() => readStoredBranding());

  const setBranding = useCallback((nextBranding) => {
    const normalized = persistBranding(nextBranding);
    setBrandingState(normalized);
    return normalized;
  }, []);

  const refreshBranding = useCallback(async () => {
    try {
      const payload = await fetchPublicBranding();
      return setBranding(payload);
    } catch (_error) {
      return readStoredBranding();
    }
  }, [setBranding]);

  useEffect(() => {
    if (!window.localStorage.getItem(BRANDING_STORAGE_KEY)) {
      persistBranding(DEFAULT_BRANDING);
    }

    refreshBranding().catch(() => undefined);

    function handleStorage(event) {
      if (event.key && event.key !== BRANDING_STORAGE_KEY) {
        return;
      }
      setBrandingState(readStoredBranding());
    }

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [refreshBranding]);

  useEffect(() => {
    const normalized = normalizeBranding(branding);
    applyFavicon(normalized);
  }, [branding]);

  const value = useMemo(
    () => ({
      branding: normalizeBranding(branding),
      setBranding,
      refreshBranding,
    }),
    [branding, refreshBranding, setBranding],
  );

  return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>;
}
