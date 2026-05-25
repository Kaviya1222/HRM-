import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import {
  Mail,
  Lock,
  Eye,
  EyeOff,
  ArrowRight,
  AlertCircle,
  ShieldCheck,
  ClipboardCheck,
  RadioTower,
} from "lucide-react";
import useAuth from "../../hooks/useAuth";
import useBranding from "../../hooks/useBranding";

function LoginPage() {
  const { isAuthenticated, login } = useAuth();
  const { branding } = useBranding();
  const [formState, setFormState] = useState({
    email: "superadmin@hrm.com",
    password: "SuperAdmin@123",
    device_name: "Web Browser",
    device_type: "browser",
  });
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    document.title = `Sign In | ${branding.organizationName}`;
  }, [branding.organizationName]);

  if (isAuthenticated) return <Navigate replace to="/" />;

  function handleChange(e) {
    const { name, value } = e.target;
    setFormState((c) => ({ ...c, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await login(formState);
    } catch (err) {
      const detail = err.response?.data?.detail;
      let msg = "Invalid credentials. Please try again.";
      if (!err.response) {
        msg = "Backend is not running. Start the API server on port 8000 and try again.";
      } else if (typeof detail === "string") {
        msg = detail === "Invalid email or password" ? "Invalid credentials. Please try again." : detail;
      } else if (Array.isArray(detail)) {
        msg = detail.map((item) => item?.msg).filter(Boolean).join(" ") || msg;
      }
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="login-root">
      <div className="login-blob login-blob-1" />
      <div className="login-blob login-blob-2" />
      <div className="login-blob login-blob-3" />

      <div className="login-grid">
        {/* Left hero */}
        <aside className="login-hero">
          <div className="login-logo-mark">
            {branding.logoDataUrl ? (
              <img
                className="login-logo-image"
                src={branding.logoDataUrl}
                alt={`${branding.organizationName} logo`}
              />
            ) : (
              <span className="login-logo-text">{branding.logoText}</span>
            )}
          </div>

          <h1 className="login-hero-headline">
            Your workforce,<br />managed smarter.
          </h1>
          <p className="login-hero-sub">
            One unified platform for employees, attendance, leave, payroll and team insights.
          </p>

          <div className="login-feature-list">
            {[
              { Icon: ShieldCheck, title: "Secure access", desc: "Role-based permissions with session management" },
              { Icon: ClipboardCheck, title: "Complete HR suite", desc: "Attendance, leave, payroll and reports in one place" },
              { Icon: RadioTower, title: "Live monitoring", desc: "Real-time employee tracker and activity dashboard" },
            ].map((f) => (
              <div key={f.title} className="login-feature-item">
                <span className="login-feature-icon">
                  <f.Icon size={22} strokeWidth={2.2} />
                </span>
                <div>
                  <strong>{f.title}</strong>
                  <p>{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </aside>

        {/* Right form card */}
        <main className="login-card">
          <div className="login-card-inner">
            <div className="login-org-badge">{branding.organizationName}</div>
            <h2 className="login-form-title">Welcome back</h2>
            <p className="login-form-sub">Sign in to access your dashboard</p>

            <form className="login-form" onSubmit={handleSubmit} noValidate>
              <div className="lf-field">
                <label className="lf-label" htmlFor="lf-email">Email address</label>
                <div className="lf-input-wrap">
                  <span className="lf-input-icon"><Mail size={16} /></span>
                  <input
                    id="lf-email"
                    className="lf-input"
                    type="email"
                    name="email"
                    value={formState.email}
                    onChange={handleChange}
                    placeholder="you@company.com"
                    required
                    autoComplete="email"
                  />
                </div>
              </div>

              <div className="lf-field">
                <label className="lf-label" htmlFor="lf-password">Password</label>
                <div className="lf-input-wrap">
                  <span className="lf-input-icon"><Lock size={16} /></span>
                  <input
                    id="lf-password"
                    className="lf-input"
                    type={showPassword ? "text" : "password"}
                    name="password"
                    value={formState.password}
                    onChange={handleChange}
                    placeholder="Enter your password"
                    required
                    autoComplete="current-password"
                    minLength={8}
                  />
                  <button
                    type="button"
                    className="lf-toggle-pw"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              {error && (
                <div className="lf-error" role="alert">
                  <AlertCircle size={15} />
                  {error}
                </div>
              )}

              <button id="login-submit-btn" className="lf-submit" type="submit" disabled={isSubmitting}>
                {isSubmitting ? (
                  <><span className="lf-spinner" /> Signing in...</>
                ) : (
                  <>Sign in <ArrowRight size={16} /></>
                )}
              </button>
            </form>

            <p className="login-footer-note">
              Contact your administrator if you need access.
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}

export default LoginPage;
