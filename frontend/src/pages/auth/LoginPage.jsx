import { useEffect, useMemo, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  Lock,
  Mail,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { changeFirstLoginPassword, forgotPassword } from "../../api/authApi";
import useAuth from "../../hooks/useAuth";
import useBranding from "../../hooks/useBranding";

function getRoleRedirect(userOrResponse) {
  const roleValue = userOrResponse?.user?.role || userOrResponse?.role;
  const roleName = typeof roleValue === "string" ? roleValue : roleValue?.name || roleValue?.code;
  const normalizedRole = String(roleName || "").toLowerCase();

  if (normalizedRole.includes("admin") || normalizedRole.includes("super_admin")) {
    return "/admin-dashboard";
  }
  if (normalizedRole === "hr" || normalizedRole.includes("human")) {
    return "/hr-dashboard";
  }
  if (normalizedRole.includes("employee")) {
    return "/employee-dashboard";
  }
  return "/";
}

function LoginPage() {
  const { isAuthenticated, login, user } = useAuth();
  const { branding } = useBranding();
  const [formState, setFormState] = useState({
    email: "",
    password: "",
    remember: true,
    device_name: "Web Browser",
    device_type: "browser",
  });
  const [passwordState, setPasswordState] = useState({
    current_password: "",
    new_password: "",
    confirm_password: "",
  });
  const [fieldErrors, setFieldErrors] = useState({});
  const [toast, setToast] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [flowStep, setFlowStep] = useState("intro");
  const [redirectPath, setRedirectPath] = useState("");

  const fallbackRedirect = useMemo(() => getRoleRedirect(user), [user]);

  useEffect(() => {
    document.title = `Login | ${branding.organizationName}`;
  }, [branding.organizationName]);

  useEffect(() => {
    if (!toast) {
      return undefined;
    }
    const timer = window.setTimeout(() => setToast(null), 4200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  if (isAuthenticated) {
    return <Navigate replace to={redirectPath || fallbackRedirect || "/"} />;
  }

  function handleChange(e) {
    const { name, type, checked, value } = e.target;
    setFormState((current) => ({ ...current, [name]: type === "checkbox" ? checked : value }));
    setFieldErrors((current) => ({ ...current, [name]: "" }));
  }

  function handlePasswordChange(e) {
    const { name, value } = e.target;
    setPasswordState((current) => ({ ...current, [name]: value }));
    setFieldErrors((current) => ({ ...current, [name]: "" }));
  }

  function validateForm() {
    const nextErrors = {};
    const email = formState.email.trim();

    if (!email) {
      nextErrors.email = "Email address is required.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      nextErrors.email = "Invalid Email";
    }

    if (!formState.password) {
      nextErrors.password = "Password is required.";
    } else if (formState.password.length < 8) {
      nextErrors.password = "Password must be at least 8 characters.";
    }

    setFieldErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  function resolveErrorMessage(err) {
    const detail = err.response?.data?.detail || err.response?.data?.message;
    if (!err.response) {
      return "Database Connection Error";
    }
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail.map((item) => item?.msg || item?.message).filter(Boolean).join(" ") || "Server Error";
    }
    return "Server Error";
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setToast(null);
    setFlowStep("login");

    if (!validateForm()) {
      setToast({ type: "error", message: "Please fix the highlighted fields." });
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await login({
        email: formState.email.trim().toLowerCase(),
        password: formState.password,
        remember: formState.remember,
        device_name: formState.device_name,
        device_type: formState.device_type,
      });
      if (response.requires_password_change) {
        setPasswordState({ current_password: "", new_password: "", confirm_password: "" });
        setFlowStep("first-password");
        setToast({ type: "success", message: "Set a new password to continue." });
        return;
      }
      setRedirectPath(response.redirect_to || getRoleRedirect(response));
      setToast({ type: "success", message: "Login successful. Redirecting..." });
    } catch (err) {
      setToast({ type: "error", message: resolveErrorMessage(err) });
    } finally {
      setIsSubmitting(false);
    }
  }

  function validatePasswordChangeForm() {
    const nextErrors = {};
    if (!passwordState.current_password) {
      nextErrors.current_password = "Current password is required.";
    }
    if (!passwordState.new_password || passwordState.new_password.length < 8) {
      nextErrors.new_password = "New Password minimum 8 characters.";
    }
    if (passwordState.confirm_password !== passwordState.new_password) {
      nextErrors.confirm_password = "Passwords Do Not Match";
    }
    setFieldErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  async function handleFirstLoginPasswordSubmit(e) {
    e.preventDefault();
    setToast(null);
    if (!validatePasswordChangeForm()) {
      setToast({ type: "error", message: "Please fix the highlighted fields." });
      return;
    }

    setIsSubmitting(true);
    try {
      await changeFirstLoginPassword({
        email: formState.email.trim().toLowerCase(),
        current_password: passwordState.current_password,
        new_password: passwordState.new_password,
        confirm_password: passwordState.confirm_password,
      });
      setFormState((current) => ({ ...current, password: "" }));
      setPasswordState({ current_password: "", new_password: "", confirm_password: "" });
      setFlowStep("login");
      setToast({ type: "success", message: "Password updated. Please login again." });
    } catch (err) {
      setToast({ type: "error", message: resolveErrorMessage(err) });
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleForgotPassword(e) {
    e.preventDefault();
    if (!formState.email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formState.email.trim())) {
      setFieldErrors((current) => ({ ...current, email: "Enter a valid email before requesting a reset." }));
      setToast({ type: "error", message: "Invalid Email" });
      return;
    }

    try {
      await forgotPassword(formState.email.trim().toLowerCase());
      setToast({ type: "success", message: "Password reset instructions sent if the email exists." });
    } catch (err) {
      setToast({ type: "error", message: resolveErrorMessage(err) });
    }
  }

  return (
    <div className={`login-root login-root--modern ${flowStep !== "intro" ? "login-root--focused" : ""}`}>
      {toast ? (
        <div className={`login-toast login-toast--${toast.type}`} role="status">
          {toast.type === "success" ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
          <span>{toast.message}</span>
        </div>
      ) : null}

      <section className={`login-shell ${flowStep === "intro" ? "login-shell--intro" : ""}`} aria-label="HRM login">
        <aside className="login-welcome-panel">
          <div className="login-logo-mark">
            {branding.logoDataUrl ? (
              <img className="login-logo-image" src={branding.logoDataUrl} alt={`${branding.organizationName} logo`} />
            ) : (
              <span className="login-logo-text">{branding.logoText}</span>
            )}
          </div>

          <div className="login-welcome-copy">
            <span className="login-eyebrow"><Sparkles size={15} /> HRMS Portal</span>
            <h1>Hello, Welcome!</h1>
            <p>Secure access for attendance, payroll, leave, reports and workforce operations.</p>
          </div>

          <button type="button" className="login-panel-button" onClick={() => setFlowStep("login")}>
            Login
            <ArrowRight size={16} />
          </button>
        </aside>

        <main className="login-form-panel" aria-hidden={flowStep === "intro"}>
          <div className="login-card-inner">
            <div className="login-org-badge">
              <ShieldCheck size={14} />
              {branding.organizationName}
            </div>
            <h2 className="login-form-title">{flowStep === "first-password" ? "Set New Password" : "Sign In"}</h2>
            <p className="login-form-sub">
              {flowStep === "first-password" ? "Create a new password before entering the HRMS portal" : "Sign in with your employee credentials"}
            </p>

            {flowStep === "first-password" ? (
              <form className="login-form" onSubmit={handleFirstLoginPasswordSubmit} noValidate>
                <div className="lf-field">
                  <label className="lf-label" htmlFor="lf-current-password">Current Password</label>
                  <div className={`lf-input-wrap ${fieldErrors.current_password ? "lf-input-wrap--error" : ""}`}>
                    <span className="lf-input-icon"><Lock size={16} /></span>
                    <input
                      id="lf-current-password"
                      className="lf-input"
                      type={showPassword ? "text" : "password"}
                      name="current_password"
                      value={passwordState.current_password}
                      onChange={handlePasswordChange}
                      placeholder="Current password"
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      className="lf-toggle-pw"
                      onClick={() => setShowPassword((value) => !value)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {fieldErrors.current_password ? <span className="lf-field-error">{fieldErrors.current_password}</span> : null}
                </div>

                <div className="lf-field">
                  <label className="lf-label" htmlFor="lf-new-password">New Password</label>
                  <div className={`lf-input-wrap ${fieldErrors.new_password ? "lf-input-wrap--error" : ""}`}>
                    <span className="lf-input-icon"><Lock size={16} /></span>
                    <input
                      id="lf-new-password"
                      className="lf-input"
                      type={showNewPassword ? "text" : "password"}
                      name="new_password"
                      value={passwordState.new_password}
                      onChange={handlePasswordChange}
                      placeholder="Minimum 8 characters"
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      className="lf-toggle-pw"
                      onClick={() => setShowNewPassword((value) => !value)}
                      aria-label={showNewPassword ? "Hide password" : "Show password"}
                    >
                      {showNewPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {fieldErrors.new_password ? <span className="lf-field-error">{fieldErrors.new_password}</span> : null}
                </div>

                <div className="lf-field">
                  <label className="lf-label" htmlFor="lf-confirm-password">Confirm New Password</label>
                  <div className={`lf-input-wrap ${fieldErrors.confirm_password ? "lf-input-wrap--error" : ""}`}>
                    <span className="lf-input-icon"><Lock size={16} /></span>
                    <input
                      id="lf-confirm-password"
                      className="lf-input"
                      type={showConfirmPassword ? "text" : "password"}
                      name="confirm_password"
                      value={passwordState.confirm_password}
                      onChange={handlePasswordChange}
                      placeholder="Confirm new password"
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      className="lf-toggle-pw"
                      onClick={() => setShowConfirmPassword((value) => !value)}
                      aria-label={showConfirmPassword ? "Hide password" : "Show password"}
                    >
                      {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {fieldErrors.confirm_password ? <span className="lf-field-error">{fieldErrors.confirm_password}</span> : null}
                </div>

                <button className="lf-submit" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? (
                    <>
                      <span className="lf-spinner" />
                      Updating...
                    </>
                  ) : (
                    <>
                      Update Password
                      <ArrowRight size={16} />
                    </>
                  )}
                </button>
              </form>
            ) : (
              <form className="login-form" onSubmit={handleSubmit} noValidate>
              <div className="lf-field">
                <label className="lf-label" htmlFor="lf-email">Email Address</label>
                <div className={`lf-input-wrap ${fieldErrors.email ? "lf-input-wrap--error" : ""}`}>
                  <span className="lf-input-icon"><Mail size={16} /></span>
                  <input
                    id="lf-email"
                    className="lf-input"
                    type="email"
                    name="email"
                    value={formState.email}
                    onChange={handleChange}
                    placeholder="name@company.com"
                    autoComplete="email"
                  />
                </div>
                {fieldErrors.email ? <span className="lf-field-error">{fieldErrors.email}</span> : null}
              </div>

              <div className="lf-field">
                <label className="lf-label" htmlFor="lf-password">Password</label>
                <div className={`lf-input-wrap ${fieldErrors.password ? "lf-input-wrap--error" : ""}`}>
                  <span className="lf-input-icon"><Lock size={16} /></span>
                  <input
                    id="lf-password"
                    className="lf-input"
                    type={showPassword ? "text" : "password"}
                    name="password"
                    value={formState.password}
                    onChange={handleChange}
                    placeholder="Enter password"
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    className="lf-toggle-pw"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                {fieldErrors.password ? <span className="lf-field-error">{fieldErrors.password}</span> : null}
              </div>

              <div className="login-form-options">
                <label className="login-remember">
                  <input
                    type="checkbox"
                    name="remember"
                    checked={formState.remember}
                    onChange={handleChange}
                  />
                  <span>Remember Me</span>
                </label>
                <Link to="/login" onClick={handleForgotPassword}>Forgot Password?</Link>
              </div>

              <button id="login-submit-btn" className="lf-submit" type="submit" disabled={isSubmitting}>
                {isSubmitting ? (
                  <>
                    <span className="lf-spinner" />
                    Signing In...
                  </>
                ) : (
                  <>
                    Sign In
                    <ArrowRight size={16} />
                  </>
                )}
              </button>
            </form>
            )}
          </div>
        </main>
      </section>
    </div>
  );
}

export default LoginPage;
