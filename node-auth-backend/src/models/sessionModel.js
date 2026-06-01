import { getPool } from "../config/database.js";

export async function createSession({ userId, refreshTokenHash, userAgent, ipAddress, expiresAt }) {
  const [result] = await getPool().execute(
    `INSERT INTO user_sessions (user_id, refresh_token_hash, user_agent, ip_address, expires_at)
     VALUES (?, ?, ?, ?, ?)`,
    [userId, refreshTokenHash, userAgent || null, ipAddress || null, expiresAt],
  );
  return result.insertId;
}

export async function findActiveSession(sessionId) {
  const [rows] = await getPool().execute(
    `SELECT id, user_id, refresh_token_hash, expires_at, revoked_at
     FROM user_sessions
     WHERE id = ? AND revoked_at IS NULL AND expires_at > NOW()
     LIMIT 1`,
    [sessionId],
  );
  return rows[0] || null;
}

export async function rotateSessionRefreshToken(sessionId, refreshTokenHash, expiresAt) {
  await getPool().execute(
    "UPDATE user_sessions SET refresh_token_hash = ?, expires_at = ? WHERE id = ? AND revoked_at IS NULL",
    [refreshTokenHash, expiresAt, sessionId],
  );
}

export async function revokeSession(sessionId) {
  await getPool().execute("UPDATE user_sessions SET revoked_at = NOW() WHERE id = ? AND revoked_at IS NULL", [sessionId]);
}

export async function revokeUserSessions(userId) {
  await getPool().execute("UPDATE user_sessions SET revoked_at = NOW() WHERE user_id = ? AND revoked_at IS NULL", [userId]);
}
