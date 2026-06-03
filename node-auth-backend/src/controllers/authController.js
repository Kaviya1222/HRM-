import { env } from "../config/env.js";
import { createSession, findActiveSession, revokeSession, revokeUserSessions, rotateSessionRefreshToken } from "../models/sessionModel.js";
import { completeFirstLoginPasswordChange, findUserByEmail, findUserById, updateUserPassword } from "../models/userModel.js";
import { hashPassword, verifyPassword } from "../utils/password.js";
import { createAccessToken, createRefreshToken, createResetToken, hashToken, verifyRefreshToken, verifyResetToken } from "../utils/jwt.js";
import { getRedirectPath, getRolePermissions } from "../utils/roleRedirect.js";

function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function addDays(days) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date;
}

function formatDateForPostgres(date) {
  return date.toISOString();
}

function serializeUser(user) {
  const nameParts = String(user.full_name || "").trim().split(/\s+/);
  const firstName = nameParts[0] || user.full_name || "";
  const lastName = nameParts.slice(1).join(" ");

  const normalizedRole = String(user.role || "").toLowerCase();
  const isAdmin = normalizedRole.includes("admin");
  return {
    id: String(user.id),
    employee_id: user.employee_id,
    email: user.email,
    first_name: firstName,
    last_name: lastName,
    full_name: user.full_name,
    role: {
      id: user.role,
      code: user.role,
      name: user.role,
      hierarchy_rank: isAdmin ? 1 : normalizedRole === "hr" ? 2 : 3,
    },
    permissions: getRolePermissions(user.role),
    is_super_admin: isAdmin,
    is_first_login: Boolean(user.is_first_login),
    last_login_at: null,
  };
}

function buildAuthResponse(user, sessionId) {
  const accessToken = createAccessToken(user, sessionId);
  const refreshToken = createRefreshToken(user, sessionId);
  return {
    access_token: accessToken,
    refresh_token: refreshToken,
    token_type: "bearer",
    expires_in: 900,
    redirect_to: getRedirectPath(user.role),
    user: serializeUser(user),
  };
}

export async function login(req, res, next) {
  try {
    const email = String(req.body.email || "").trim().toLowerCase();
    const password = String(req.body.password || "");

    if (!email || !validateEmail(email)) {
      return res.status(400).json({ message: "Invalid Email" });
    }
    if (!password) {
      return res.status(400).json({ message: "Password is required" });
    }

    const user = await findUserByEmail(email);
    if (!user) {
      return res.status(404).json({ message: "Invalid Email" });
    }
    if (user.status !== "Active") {
      return res.status(403).json({ message: "Account Inactive" });
    }

    const isPasswordValid = await verifyPassword(password, user.password_hash);
    if (!isPasswordValid) {
      return res.status(401).json({ message: "Incorrect Password" });
    }

    if (Boolean(user.is_first_login)) {
      return res.status(200).json({
        requires_password_change: true,
        message: "First login password change required",
        user: {
          id: String(user.id),
          employee_id: user.employee_id,
          email: user.email,
          full_name: user.full_name,
          role: user.role,
          is_first_login: true,
        },
      });
    }

    const temporaryRefreshToken = createRefreshToken(user, "pending");
    const sessionId = await createSession({
      userId: user.id,
      refreshTokenHash: hashToken(temporaryRefreshToken),
      userAgent: req.headers["user-agent"],
      ipAddress: req.ip,
      expiresAt: formatDateForPostgres(addDays(7)),
    });

    const response = buildAuthResponse(user, sessionId);
    await rotateSessionRefreshToken(sessionId, hashToken(response.refresh_token), formatDateForPostgres(addDays(7)));
    req.session.userId = user.id;
    req.session.role = user.role;

    return res.status(200).json(response);
  } catch (error) {
    if (error.code && String(error.code).startsWith("ER_")) {
      return res.status(503).json({ message: "Database Connection Error" });
    }
    return next(error);
  }
}

export async function changeFirstLoginPassword(req, res, next) {
  try {
    const email = String(req.body.email || "").trim().toLowerCase();
    const currentPassword = String(req.body.current_password || "");
    const newPassword = String(req.body.new_password || "");
    const confirmPassword = String(req.body.confirm_password || "");

    if (!email || !validateEmail(email)) {
      return res.status(400).json({ message: "Invalid Email" });
    }
    if (newPassword.length < 8) {
      return res.status(400).json({ message: "New Password minimum 8 characters" });
    }
    if (newPassword !== confirmPassword) {
      return res.status(400).json({ message: "Passwords Do Not Match" });
    }

    const user = await findUserByEmail(email);
    if (!user) {
      return res.status(404).json({ message: "Invalid Email" });
    }
    if (user.status !== "Active") {
      return res.status(403).json({ message: "Account Inactive" });
    }
    if (!Boolean(user.is_first_login)) {
      return res.status(400).json({ message: "First login password change is not required" });
    }

    const isCurrentPasswordValid = await verifyPassword(currentPassword, user.password_hash);
    if (!isCurrentPasswordValid) {
      return res.status(401).json({ message: "Current Password Incorrect" });
    }

    await completeFirstLoginPasswordChange(user.id, await hashPassword(newPassword));
    await revokeUserSessions(user.id);
    req.session.destroy(() => {});
    return res.status(200).json({ message: "Password updated successfully. Please login again." });
  } catch (error) {
    if (error.code && String(error.code).startsWith("ER_")) {
      return res.status(503).json({ message: "Database Error" });
    }
    return next(error);
  }
}

export async function refresh(req, res, next) {
  try {
    const refreshToken = String(req.body.refresh_token || "");
    const payload = verifyRefreshToken(refreshToken);
    if (payload.typ !== "refresh") {
      return res.status(401).json({ message: "Invalid token type" });
    }

    const session = await findActiveSession(payload.sid);
    if (!session || session.refresh_token_hash !== hashToken(refreshToken)) {
      return res.status(401).json({ message: "Session expired" });
    }

    const user = await findUserById(payload.sub);
    if (!user || user.status !== "Active") {
      return res.status(403).json({ message: "Account Inactive" });
    }

    const response = buildAuthResponse(user, session.id);
    await rotateSessionRefreshToken(session.id, hashToken(response.refresh_token), formatDateForPostgres(addDays(7)));
    return res.status(200).json(response);
  } catch (error) {
    return res.status(401).json({ message: "Invalid refresh token" });
  }
}

export async function me(req, res) {
  return res.status(200).json(serializeUser(req.auth.user));
}

export async function logout(req, res, next) {
  try {
    if (req.auth?.session?.id) {
      await revokeSession(req.auth.session.id);
    }
    req.session.destroy(() => {});
    return res.status(200).json({ message: "Logged out successfully" });
  } catch (error) {
    return next(error);
  }
}

export async function forgotPassword(req, res, next) {
  try {
    const email = String(req.body.email || "").trim().toLowerCase();
    if (!email || !validateEmail(email)) {
      return res.status(400).json({ message: "Invalid Email" });
    }

    const user = await findUserByEmail(email);
    if (!user) {
      return res.status(200).json({ message: "Password reset instructions sent if the email exists." });
    }

    const resetToken = createResetToken(user);
    const response = { message: "Password reset token generated.", reset_token_expires_in: 900 };
    if (env.nodeEnv !== "production") {
      response.reset_token = resetToken;
    }
    return res.status(200).json(response);
  } catch (error) {
    return next(error);
  }
}

export async function resetPassword(req, res, next) {
  try {
    const token = String(req.body.token || "");
    const password = String(req.body.password || "");
    if (!token) {
      return res.status(400).json({ message: "Reset token is required" });
    }
    if (password.length < 8) {
      return res.status(400).json({ message: "Password must be at least 8 characters" });
    }

    const payload = verifyResetToken(token);
    if (payload.typ !== "password_reset") {
      return res.status(400).json({ message: "Invalid reset token" });
    }

    const user = await findUserById(payload.sub);
    if (!user || user.email !== payload.email) {
      return res.status(400).json({ message: "Invalid reset token" });
    }

    await updateUserPassword(user.id, await hashPassword(password));
    await revokeUserSessions(user.id);
    return res.status(200).json({ message: "Password reset successfully" });
  } catch (error) {
    return res.status(400).json({ message: "Invalid or expired reset token" });
  }
}
