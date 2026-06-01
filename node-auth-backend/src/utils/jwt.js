import jwt from "jsonwebtoken";
import crypto from "crypto";
import { env } from "../config/env.js";

export function createAccessToken(user, sessionId) {
  return jwt.sign(
    { sub: String(user.id), sid: String(sessionId), role: user.role, typ: "access" },
    env.jwt.accessSecret,
    { expiresIn: env.jwt.accessExpiresIn },
  );
}

export function createRefreshToken(user, sessionId) {
  return jwt.sign(
    { sub: String(user.id), sid: String(sessionId), role: user.role, typ: "refresh" },
    env.jwt.refreshSecret,
    { expiresIn: env.jwt.refreshExpiresIn },
  );
}

export function createResetToken(user) {
  return jwt.sign(
    { sub: String(user.id), email: user.email, typ: "password_reset" },
    env.jwt.resetSecret,
    { expiresIn: "15m" },
  );
}

export function verifyAccessToken(token) {
  return jwt.verify(token, env.jwt.accessSecret);
}

export function verifyRefreshToken(token) {
  return jwt.verify(token, env.jwt.refreshSecret);
}

export function verifyResetToken(token) {
  return jwt.verify(token, env.jwt.resetSecret);
}

export function hashToken(token) {
  return crypto.createHash("sha256").update(token).digest("hex");
}
