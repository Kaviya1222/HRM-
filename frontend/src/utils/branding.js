import { API_BASE_URL } from "../api/client";

export const BRANDING_STORAGE_KEY = "hrm.branding";

export const DEFAULT_BRANDING = {
  organizationName: "HRM Suite",
  tagline: "Workforce Portal",
  logoText: "HRM",
  logoDataUrl: "",
  logoUrl: "",
};

function resolveLogoUrl(value) {
  const rawValue = safeString(value);
  if (!rawValue || rawValue.startsWith("data:") || /^https?:\/\//i.test(rawValue)) {
    return rawValue;
  }
  if (rawValue.startsWith("/")) {
    const apiRoot = API_BASE_URL.replace(/\/api\/v1\/?$/, "");
    return `${apiRoot}${rawValue}`;
  }
  return rawValue;
}

function safeString(value, fallback = "", { allowEmpty = false } = {}) {
  if (typeof value !== "string") {
    return fallback;
  }
  const trimmed = value.trim();
  if (trimmed === "" && !allowEmpty) {
    return fallback;
  }
  return trimmed;
}

export function normalizeBranding(source = {}) {
  const organizationName = safeString(
    source.organizationName ?? source.organization_name ?? source.orgName,
    DEFAULT_BRANDING.organizationName,
    { allowEmpty: true },
  );
  const tagline = safeString(source.tagline, DEFAULT_BRANDING.tagline, { allowEmpty: true });
  const logoText = safeString(
    source.logoText ?? source.logo_text,
    organizationName.slice(0, 3).toUpperCase() || DEFAULT_BRANDING.logoText,
  )
    .slice(0, 4)
    .toUpperCase();
  const logoUrl = resolveLogoUrl(source.logoUrl ?? source.logo_url ?? source.logo_path ?? source.url);
  const logoDataUrl = resolveLogoUrl(source.logoDataUrl ?? source.logo_data_url ?? logoUrl);

  return {
    organizationName,
    tagline,
    logoText,
    logoDataUrl,
    logoUrl,
  };
}

export function readStoredBranding() {
  try {
    const stored = window.localStorage.getItem(BRANDING_STORAGE_KEY);
    if (!stored) {
      return DEFAULT_BRANDING;
    }
    return normalizeBranding(JSON.parse(stored));
  } catch (_error) {
    return DEFAULT_BRANDING;
  }
}

export function persistBranding(branding) {
  const normalized = normalizeBranding(branding);
  try {
    window.localStorage.setItem(BRANDING_STORAGE_KEY, JSON.stringify(normalized));
  } catch (_error) {
    return normalized;
  }
  return normalized;
}

export function extractBrandingFromSettings(settings = []) {
  const settingMap = Object.fromEntries(settings.map((setting) => [setting.key, setting.value_json ?? {}]));

  return normalizeBranding({
    organizationName: settingMap["branding.organization_name"]?.text,
    tagline: settingMap["branding.portal_tagline"]?.text,
    logoText: settingMap["branding.logo"]?.text,
    logoDataUrl: settingMap["branding.logo"]?.data_url,
    logoUrl: settingMap["branding.logo"]?.url ?? settingMap["branding.logo"]?.path,
  });
}

export function buildBrandingSettingItems(branding) {
  const normalized = normalizeBranding(branding);

  return [
    {
      key: "branding.organization_name",
      category: "branding",
      name: "Organization Name",
      description: "Primary organization name shown across the application shell.",
      value_type: "json",
      value_json: { text: normalized.organizationName },
      is_public: true,
    },
    {
      key: "branding.portal_tagline",
      category: "branding",
      name: "Portal Tagline",
      description: "Short supporting label shown below the organization name.",
      value_type: "json",
      value_json: { text: normalized.tagline },
      is_public: true,
    },
    {
      key: "branding.logo",
      category: "branding",
      name: "Organization Logo",
      description: "Logo image and fallback text used in the application shell.",
      value_type: "json",
      value_json: {
        text: normalized.logoText,
        data_url: normalized.logoDataUrl?.startsWith("data:") ? normalized.logoDataUrl : null,
        url: normalized.logoUrl || (normalized.logoDataUrl?.startsWith("data:") ? null : normalized.logoDataUrl || null),
      },
      is_public: true,
    },
  ];
}

export function buildBrandingIconDataUrl(branding) {
  const normalized = normalizeBranding(branding);

  if (normalized.logoDataUrl) {
    return normalized.logoDataUrl;
  }

  const label = normalized.logoText || normalized.organizationName.slice(0, 3).toUpperCase();
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#d9a767" />
          <stop offset="100%" stop-color="#7cb3d5" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill="url(#g)" />
      <text x="32" y="38" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#101826">${label}</text>
    </svg>
  `;

  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}
