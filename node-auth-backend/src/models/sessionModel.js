import { getPool } from "../config/database.js";

export async function createSession({ userId, refreshTokenHash, userAgent, ipAddress, expiresAt }) {
  const { rows } = await getPool().query(
    `INSERT INTO user_sessions (user_id, refresh_token_hash, user_agent, ip_address, expires_at, access_jti, refresh_jti)
     VALUES ($1, $2, $3, $4, $5, gen_random_uuid()::text, gen_random_uuid()::text)
     RETURNING id`,
    [userId, refreshTokenHash, userAgent || null, ipAddress || null, expiresAt],
  );
  return rows[0].id;
}

export async function findActiveSession(sessionId) {
  const { rows } = await getPool().query(
    `SELECT id, user_id, refresh_token_hash, expires_at, revoked_at
     FROM user_sessions
     WHERE id = $1 AND revoked_at IS NULL AND expires_at > NOW()
     LIMIT 1`,
    [sessionId],
  );
  return rows[0] || null;
}

export async function rotateSessionRefreshToken(sessionId, refreshTokenHash, expiresAt) {
  await getPool().query(
    "UPDATE user_sessions SET refresh_token_hash = $1, expires_at = $2 WHERE id = $3 AND revoked_at IS NULL",
    [refreshTokenHash, expiresAt, sessionId],
  );
}

export async function revokeSession(sessionId) {
  await getPool().query("UPDATE user_sessions SET revoked_at = NOW() WHERE id = $1 AND revoked_at IS NULL", [sessionId]);
}

export async function revokeUserSessions(userId) {
  await getPool().query("UPDATE user_sessions SET revoked_at = NOW() WHERE user_id = $1 AND revoked_at IS NULL", [userId]);
}
