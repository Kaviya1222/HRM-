import { Link } from "react-router-dom";

function UnauthorizedPage() {
  return (
    <div className="screen-center">
      <div className="loading-panel">
        <p className="eyebrow">Access Denied</p>
        <h2>Access Denied - Permission Required</h2>
        <p>This module is restricted for your account. Please contact Super Admin if you need access.</p>
        <Link className="primary-button inline-link" to="/">
          Return to Dashboard
        </Link>
      </div>
    </div>
  );
}

export default UnauthorizedPage;
