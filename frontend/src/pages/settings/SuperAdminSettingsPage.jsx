import { useEffect, useState } from "react";
import {
  Shield, ChevronDown, ChevronRight, Save, X,
  Building2, Type, Image, Clock, Users,
  Search, AlertCircle, CheckCircle2,
  Sliders, Lock,
} from "lucide-react";
import {
  fetchAppSettings, fetchPermissionCatalog,
  fetchRolePermissions, fetchRoles,
  saveAppSettings, saveRolePermissions,
} from "../../api/settingsApi";
import useAuth from "../../hooks/useAuth";
import useBranding from "../../hooks/useBranding";
import { buildBrandingSettingItems, extractBrandingFromSettings, normalizeBranding } from "../../utils/branding";

function groupPermissions(perms) {
  return perms.reduce((acc, permission) => {
    const moduleKey = permission.module || "general";
    if (!acc[moduleKey]) acc[moduleKey] = [];
    acc[moduleKey].push(permission);
    return acc;
  }, {});
}

const MODULE_ICONS = {
  auth: Lock,
  employees: Users,
  attendance: Clock,
  leave: Clock,
  payroll: Shield,
  reports: ChevronRight,
  tracker: Shield,
  settings: Sliders,
};

function AccordionSection({ title, icon: Icon, badge, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={`accordion ${open ? "accordion--open" : ""}`}>
      <button className="accordion-header" type="button" onClick={() => setOpen((current) => !current)}>
        <span className="accordion-header-left">
          {Icon ? <Icon size={16} className="accordion-icon" /> : null}
          <span className="accordion-title">{title}</span>
          {badge != null ? <span className="accordion-badge">{badge}</span> : null}
        </span>
        <ChevronDown size={16} className="accordion-chevron" />
      </button>
      {open ? <div className="accordion-body">{children}</div> : null}
    </div>
  );
}

function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      className={`perm-toggle ${checked ? "perm-toggle--on" : ""} ${disabled ? "perm-toggle--disabled" : ""}`}
      onClick={() => !disabled && onChange(!checked)}
    >
      <span className="perm-toggle-thumb" />
    </button>
  );
}

function SuperAdminSettingsPage() {
  const { user, refreshProfile } = useAuth();
  const { branding, setBranding } = useBranding();
  const [roles, setRoles] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [selectedRoleId, setSelectedRoleId] = useState(null);
  const [roleMatrix, setRoleMatrix] = useState(null);
  const [appSettings, setAppSettings] = useState([]);
  const [settingsDraft, setSettingsDraft] = useState({});
  const [brandingDraft, setBrandingDraft] = useState(() => normalizeBranding(branding));
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingPerms, setIsSavingPerms] = useState(false);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [isSavingBranding, setIsSavingBranding] = useState(false);
  const [toast, setToast] = useState(null);
  const [permSearch, setPermSearch] = useState("");

  function showToast(type, msg) {
    setToast({ type, msg });
    window.setTimeout(() => setToast(null), 3500);
  }

  useEffect(() => {
    async function load() {
      try {
        const [rolesData, catalogData, settingsData] = await Promise.all([
          fetchRoles(),
          fetchPermissionCatalog(),
          fetchAppSettings(),
        ]);

        setRoles(rolesData);
        setCatalog(catalogData);
        setAppSettings(settingsData);
        setSettingsDraft(
          Object.fromEntries(
            settingsData
              .filter((setting) => setting.category !== "branding")
              .map((setting) => [setting.key, setting.value_json ?? {}]),
          ),
        );

        const loadedBranding = extractBrandingFromSettings(settingsData);
        setBranding(loadedBranding);
        setBrandingDraft(loadedBranding);

        if (rolesData.length > 0) {
          setSelectedRoleId(rolesData[0].id);
        }
      } catch (_error) {
        showToast("error", "Failed to load settings.");
      } finally {
        setIsLoading(false);
      }
    }

    load();
  }, [setBranding]);

  useEffect(() => {
    if (!selectedRoleId) {
      return;
    }

    setRoleMatrix(null);
    fetchRolePermissions(selectedRoleId)
      .then(setRoleMatrix)
      .catch(() => showToast("error", "Failed to load role permissions."));
  }, [selectedRoleId]);

  function togglePerm(key) {
    setRoleMatrix((matrix) => ({
      ...matrix,
      permissions: matrix.permissions.map((permission) => (
        permission.permission_key === key
          ? { ...permission, is_allowed: !permission.is_allowed }
          : permission
      )),
    }));
  }

  async function savePerms() {
    if (!roleMatrix) {
      return;
    }

    setIsSavingPerms(true);
    try {
      const updated = await saveRolePermissions(
        roleMatrix.role_id,
        roleMatrix.permissions.map((permission) => ({
          permission_key: permission.permission_key,
          is_allowed: permission.is_allowed,
        })),
      );
      setRoleMatrix(updated);
      if (user?.role?.id === roleMatrix.role_id) {
        await refreshProfile();
      }
      const updatedAt = String(Date.now());
      localStorage.setItem("hrm:permissions-updated-at", updatedAt);
      window.dispatchEvent(new CustomEvent("hrm:permissions-updated", { detail: { updatedAt } }));
      showToast("success", `Permissions updated for ${updated.role_name}.`);
    } catch (_error) {
      showToast("error", "Failed to save permissions.");
    } finally {
      setIsSavingPerms(false);
    }
  }

  function getSettingField(setting) {
    const draft = settingsDraft[setting.key] ?? {};
    const entries = Object.entries(draft);
    if (entries.length === 0) {
      return null;
    }

    return entries.map(([fieldKey, value]) => ({
      fieldKey,
      value,
      label: fieldKey.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase()),
    }));
  }

  function updateSettingField(settingKey, fieldKey, newVal) {
    setSettingsDraft((draft) => ({
      ...draft,
      [settingKey]: { ...draft[settingKey], [fieldKey]: Number(newVal) },
    }));
  }

  function syncOperationalSettings(updatedSettings) {
    setAppSettings(updatedSettings);
    setSettingsDraft(
      Object.fromEntries(
        updatedSettings
          .filter((setting) => setting.category !== "branding")
          .map((setting) => [setting.key, setting.value_json ?? {}]),
      ),
    );
  }

  async function handleSaveSettings() {
    setIsSavingSettings(true);
    try {
      const payload = operationalSettings.map((setting) => ({
        ...setting,
        value_json: settingsDraft[setting.key],
      }));
      const updated = await saveAppSettings(payload);
      syncOperationalSettings(updated);
      showToast("success", "System settings saved.");
    } catch (_error) {
      showToast("error", "Failed to save settings. Check your values.");
    } finally {
      setIsSavingSettings(false);
    }
  }

  async function handleSaveBranding() {
    setIsSavingBranding(true);
    try {
      const derivedLogoText = brandingDraft.organizationName.trim().slice(0, 4).toUpperCase() || "HRM";
      const updated = await saveAppSettings(
        buildBrandingSettingItems({ ...brandingDraft, logoText: derivedLogoText }),
      );
      const savedBranding = extractBrandingFromSettings(updated);
      syncOperationalSettings(updated);
      setBranding(savedBranding);
      setBrandingDraft(savedBranding);
      showToast("success", "Branding updated.");
    } catch (_error) {
      showToast("error", "Failed to update branding.");
    } finally {
      setIsSavingBranding(false);
    }
  }

  function handleBrandingFieldChange(field, value) {
    setBrandingDraft((current) => ({ ...current, [field]: value }));
  }

  function handleLogoUpload(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    if (!file.type.startsWith("image/")) {
      showToast("error", "Please upload a valid image file.");
      event.target.value = "";
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setBrandingDraft((current) => normalizeBranding({ ...current, logoDataUrl: reader.result }));
      } else {
        showToast("error", "Unable to read the selected image.");
      }
    };
    reader.onerror = () => showToast("error", "Unable to read the selected image.");
    reader.readAsDataURL(file);
    event.target.value = "";
  }

  const isSuperAdmin = roleMatrix?.role_code === "super_admin";
  const operationalSettings = appSettings.filter((setting) => setting.category !== "branding");
  const brandingPreviewText = brandingDraft.organizationName.trim().slice(0, 4).toUpperCase() || "HRM";
  const filteredPerms = roleMatrix?.permissions?.filter((permission) => (
    !permSearch
      || permission.permission_name?.toLowerCase().includes(permSearch.toLowerCase())
      || permission.permission_key?.toLowerCase().includes(permSearch.toLowerCase())
  )) ?? [];
  const groupedPerms = groupPermissions(filteredPerms);
  const selectedRole = roles.find((role) => role.id === selectedRoleId);

  if (isLoading) {
    return (
      <div className="page-container">
        <div className="settings-loading">
          <div className="settings-loading-spinner" />
          <p>Loading settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      {toast ? (
        <div className={`settings-toast settings-toast--${toast.type}`}>
          {toast.type === "success" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          {toast.msg}
        </div>
      ) : null}

      <div className="page-section-header">
        <Shield size={20} className="page-section-header-icon" />
        <div>
          <h2 className="page-section-header-title">System Settings</h2>
          <p className="page-section-header-sub">Manage roles, permissions and system-wide configuration</p>
        </div>
      </div>

      <div className="settings-layout">
        <div className="settings-panels">
          <AccordionSection title="Organization Branding" icon={Building2} defaultOpen>
            <div className="settings-form-grid">
              <div className="sf-branding-preview">
                <div className="sf-branding-preview-logo">
                  {brandingDraft.logoDataUrl ? (
                    <img
                      className="sf-branding-preview-image"
                      src={brandingDraft.logoDataUrl}
                      alt={`${brandingDraft.organizationName} logo`}
                    />
                  ) : (
                    <span className="sf-branding-preview-text">{brandingPreviewText}</span>
                  )}
                </div>
                <div className="sf-branding-preview-copy">
                  <strong>{brandingDraft.organizationName}</strong>
                  <span>{brandingDraft.tagline}</span>
                </div>
              </div>

              <div className="sf-field">
                <label className="sf-label">
                  <Type size={14} /> Organization Name
                </label>
                <input
                  className="sf-input"
                  value={brandingDraft.organizationName}
                  onChange={(event) => handleBrandingFieldChange("organizationName", event.target.value)}
                  placeholder="Your Company Name"
                />
              </div>

              <div className="sf-field">
                <label className="sf-label">
                  <Type size={14} /> Portal Tagline
                </label>
                <input
                  className="sf-input"
                  value={brandingDraft.tagline}
                  onChange={(event) => handleBrandingFieldChange("tagline", event.target.value)}
                  placeholder="Workforce Portal"
                />
              </div>

              <div className="sf-field">
                <label className="sf-label">
                  <Image size={14} /> Organization Logo
                </label>
                <label className="sf-upload-trigger">
                  <input
                    className="sf-upload-input"
                    type="file"
                    accept="image/*"
                    onChange={handleLogoUpload}
                  />
                  <span className="settings-btn settings-btn--subtle">
                    <Image size={15} />
                    Upload Logo
                  </span>
                </label>
                <p className="sf-hint">PNG, JPG, or SVG. The saved logo is reused in the app brand icon, browser icon, and login screen.</p>
              </div>
            </div>

            <div className="settings-action-row">
              <button className="settings-btn settings-btn--primary" onClick={handleSaveBranding} disabled={isSavingBranding}>
                {isSavingBranding ? <><span className="settings-spinner" /> Saving...</> : <><Save size={15} /> Save Branding</>}
              </button>
            </div>
          </AccordionSection>

          <AccordionSection title="Operational Settings" icon={Sliders} badge={operationalSettings.length}>
            <div className="settings-form-grid">
              {operationalSettings.map((setting) => {
                const fields = getSettingField(setting);

                return (
                  <div className="sf-group" key={setting.key}>
                    <p className="sf-group-title">{setting.name}</p>
                    <p className="sf-group-desc">{setting.description}</p>
                    {fields?.map(({ fieldKey, value, label }) => (
                      <div className="sf-field sf-field--inline" key={fieldKey}>
                        <label className="sf-label">{label}</label>
                        <input
                          className="sf-input sf-input--short"
                          type="number"
                          min={0}
                          value={value}
                          onChange={(event) => updateSettingField(setting.key, fieldKey, event.target.value)}
                        />
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>

            <div className="settings-action-row">
              <button className="settings-btn settings-btn--primary" onClick={handleSaveSettings} disabled={isSavingSettings}>
                {isSavingSettings ? <><span className="settings-spinner" /> Saving...</> : <><Save size={15} /> Save Settings</>}
              </button>
            </div>
          </AccordionSection>
        </div>

        <div className="settings-perms-panel">
          <div className="settings-perms-header">
            <Shield size={16} />
            <h3>Role Permissions</h3>
          </div>

          <div className="role-tabs">
            {roles.map((role) => (
              <button
                key={role.id}
                type="button"
                className={`role-tab ${selectedRoleId === role.id ? "role-tab--active" : ""}`}
                onClick={() => setSelectedRoleId(role.id)}
              >
                {role.name}
              </button>
            ))}
          </div>

          {isSuperAdmin ? (
            <div className="settings-info-box">
              <Lock size={14} />
              <span>Super Admin has full access and cannot be restricted.</span>
            </div>
          ) : null}

          {!isSuperAdmin ? (
            <div className="perm-search-wrap">
              <Search size={14} className="perm-search-icon" />
              <input
                className="perm-search-input"
                placeholder="Search permissions..."
                value={permSearch}
                onChange={(event) => setPermSearch(event.target.value)}
              />
              {permSearch ? (
                <button className="perm-search-clear" onClick={() => setPermSearch("")} type="button">
                  <X size={13} />
                </button>
              ) : null}
            </div>
          ) : null}

          {roleMatrix ? (
            <div className="perm-groups">
              {Object.entries(groupedPerms).map(([moduleKey, permissions]) => {
                const ModuleIcon = MODULE_ICONS[moduleKey] || Shield;
                const allowedCount = permissions.filter((permission) => permission.is_allowed).length;

                return (
                  <AccordionSection
                    key={moduleKey}
                    title={moduleKey.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase())}
                    icon={ModuleIcon}
                    badge={`${allowedCount}/${permissions.length}`}
                  >
                    <div className="perm-list">
                      {permissions.map((permission) => (
                        <div className="perm-row" key={permission.permission_key}>
                          <div className="perm-row-info">
                            <span className="perm-row-name">{permission.permission_name}</span>
                            <span className="perm-row-key">{permission.permission_key}</span>
                          </div>
                          <Toggle
                            checked={Boolean(permission.is_allowed)}
                            onChange={() => togglePerm(permission.permission_key)}
                            disabled={isSuperAdmin}
                          />
                        </div>
                      ))}
                    </div>
                  </AccordionSection>
                );
              })}
            </div>
          ) : (
            <div className="settings-loading">
              <div className="settings-loading-spinner" />
            </div>
          )}

          {!isSuperAdmin && roleMatrix ? (
            <div className="settings-action-row settings-action-row--sticky">
              <button className="settings-btn settings-btn--primary settings-btn--full" onClick={savePerms} disabled={isSavingPerms}>
                {isSavingPerms ? <><span className="settings-spinner" /> Saving...</> : <><Save size={15} /> Save {selectedRole?.name} Permissions</>}
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default SuperAdminSettingsPage;
