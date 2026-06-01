import { findActiveSession } from "../models/sessionModel.js";
import { findUserById } from "../models/userModel.js";
import { verifyAccessToken } from "../utils/jwt.js";

export async function authenticate(req, res, next) {
  try {
    const authHeader = req.headers.authorization || "";
    const token = authHeader.startsWith("Bearer ") ? authHeader.slice(7) : "";
    if (!token) {
      return res.status(401).json({ message: "Authentication token is required" });
    }

    const payload = verifyAccessToken(token);
    if (payload.typ !== "access") {
      return res.status(401).json({ message: "Invalid token type" });
    }

    const session = await findActiveSession(payload.sid);
    if (!session) {
      return res.status(401).json({ message: "Session expired" });
    }

    const user = await findUserById(payload.sub);
    if (!user || user.status !== "Active") {
      return res.status(403).json({ message: "Account Inactive" });
    }

    req.auth = { user, session };
    return next();
  } catch (error) {
    return res.status(401).json({ message: "Invalid token" });
  }
}

export function authorizeRoles(...roles) {
  return (req, res, next) => {
    if (!req.auth?.user || !roles.includes(req.auth.user.role)) {
      return res.status(403).json({ message: "Access denied" });
    }
    return next();
  };
}
