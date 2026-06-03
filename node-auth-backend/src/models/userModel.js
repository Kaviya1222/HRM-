import { getPool } from "../config/database.js";

const USER_COLUMNS = `
  u.id,
  u.employee_id,
  COALESCE(NULLIF(u.full_name, ''), TRIM(CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, '')))) AS full_name,
  u.email,
  u.password_hash,
  COALESCE(NULLIF(u.role, ''), r.name, r.code, 'Employee') AS role,
  CASE
    WHEN COALESCE(u.is_active, TRUE) = FALSE THEN 'Inactive'
    WHEN LOWER(COALESCE(u.status, 'active')) = 'inactive' THEN 'Inactive'
    ELSE 'Active'
  END AS status,
  COALESCE(u.is_first_login, TRUE) AS is_first_login,
  u.created_at
`;

export async function findUserByEmail(email) {
  const { rows } = await getPool().query(
    `SELECT ${USER_COLUMNS}
     FROM users u
     LEFT JOIN roles r ON r.id = u.role_id
     WHERE u.email = $1
     LIMIT 1`,
    [email],
  );
  return rows[0] || null;
}

export async function findUserById(id) {
  const { rows } = await getPool().query(
    `SELECT ${USER_COLUMNS}
     FROM users u
     LEFT JOIN roles r ON r.id = u.role_id
     WHERE u.id = $1
     LIMIT 1`,
    [id],
  );
  return rows[0] || null;
}

export async function updateUserPassword(userId, passwordHash) {
  await getPool().query("UPDATE users SET password_hash = $1 WHERE id = $2", [passwordHash, userId]);
}

export async function completeFirstLoginPasswordChange(userId, passwordHash) {
  await getPool().query(
    "UPDATE users SET password_hash = $1, is_first_login = FALSE WHERE id = $2",
    [passwordHash, userId],
  );
}
