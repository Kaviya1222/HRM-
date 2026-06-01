import mysql from "mysql2/promise";
import crypto from "crypto";
import { env } from "./env.js";
import { hashPassword } from "../utils/password.js";

let pool;

export async function initializeDatabase() {
  const bootstrapConnection = await mysql.createConnection({
    host: env.db.host,
    user: env.db.user,
    password: env.db.password,
    multipleStatements: true,
  });

  await bootstrapConnection.query(
    `CREATE DATABASE IF NOT EXISTS \`${env.db.database}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci`,
  );
  await bootstrapConnection.end();

  pool = mysql.createPool({
    host: env.db.host,
    user: env.db.user,
    password: env.db.password,
    database: env.db.database,
    waitForConnections: true,
    connectionLimit: 10,
    queueLimit: 0,
    namedPlaceholders: true,
  });

  await pool.query(`
    CREATE TABLE IF NOT EXISTS users (
      id INT AUTO_INCREMENT PRIMARY KEY,
      employee_id VARCHAR(50) UNIQUE,
      full_name VARCHAR(100),
      email VARCHAR(100) UNIQUE,
      password_hash VARCHAR(255),
      role ENUM('Admin','HR','Employee') NOT NULL DEFAULT 'Employee',
      status ENUM('Active','Inactive') NOT NULL DEFAULT 'Active',
      is_first_login BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `);

  await addColumnIfMissing("users", "employee_id", "VARCHAR(50) NULL");
  await addColumnIfMissing("users", "full_name", "VARCHAR(100) NULL");
  await addColumnIfMissing("users", "email", "VARCHAR(100) NULL");
  await addColumnIfMissing("users", "password_hash", "VARCHAR(255) NULL");
  await addColumnIfMissing("users", "role", "ENUM('Admin','HR','Employee') NOT NULL DEFAULT 'Employee'");
  await addColumnIfMissing("users", "status", "ENUM('Active','Inactive') NOT NULL DEFAULT 'Active'");
  await addColumnIfMissing("users", "is_first_login", "BOOLEAN NOT NULL DEFAULT TRUE");
  await addColumnIfMissing("users", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP");
  await addUniqueIndexIfMissing("users", "idx_users_employee_id_unique", "employee_id");
  await addUniqueIndexIfMissing("users", "idx_users_email_unique", "email");

  await pool.query(`
    CREATE TABLE IF NOT EXISTS user_sessions (
      id INT AUTO_INCREMENT PRIMARY KEY,
      user_id INT NOT NULL,
      refresh_token_hash VARCHAR(255) NOT NULL,
      user_agent VARCHAR(255),
      ip_address VARCHAR(64),
      expires_at DATETIME NOT NULL,
      revoked_at DATETIME NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      INDEX idx_user_sessions_user_id (user_id),
      CONSTRAINT fk_user_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `);

  await seedDefaultAdmin();
}

async function seedDefaultAdmin() {
  const [rows] = await pool.execute("SELECT id FROM users WHERE email = ? LIMIT 1", [env.defaultAdmin.email]);
  if (rows.length) {
    return;
  }

  const columns = await getTableColumns("users");
  const columnNames = new Set(columns.map((column) => column.COLUMN_NAME));
  const requiredValues = {};
  const passwordHash = await hashPassword(env.defaultAdmin.password);
  const nameParts = env.defaultAdmin.fullName.split(/\s+/);

  const idColumn = columns.find((column) => column.COLUMN_NAME === "id");
  if (columnNames.has("id") && !idColumn?.EXTRA.includes("auto_increment")) {
    const uuidValue = crypto.randomUUID();
    requiredValues.id = Number(idColumn?.CHARACTER_MAXIMUM_LENGTH) === 32 ? uuidValue.replaceAll("-", "") : uuidValue;
  }
  if (columnNames.has("employee_id")) {
    requiredValues.employee_id = env.defaultAdmin.employeeId;
  }
  if (columnNames.has("full_name")) {
    requiredValues.full_name = env.defaultAdmin.fullName;
  }
  if (columnNames.has("first_name")) {
    requiredValues.first_name = nameParts[0] || "System";
  }
  if (columnNames.has("last_name")) {
    requiredValues.last_name = nameParts.slice(1).join(" ") || "Admin";
  }
  if (columnNames.has("email")) {
    requiredValues.email = env.defaultAdmin.email;
  }
  if (columnNames.has("password_hash")) {
    requiredValues.password_hash = passwordHash;
  }
  if (columnNames.has("role")) {
    requiredValues.role = "Admin";
  }
  if (columnNames.has("role_id")) {
    const [roles] = await pool.execute(
      "SELECT id FROM roles WHERE code IN ('super_admin', 'admin', 'Admin') OR name IN ('Super Admin', 'Admin') ORDER BY hierarchy_rank ASC LIMIT 1",
    );
    if (!roles.length) {
      return;
    }
    requiredValues.role_id = roles[0].id;
  }
  if (columnNames.has("status")) {
    requiredValues.status = "Active";
  }
  if (columnNames.has("is_active")) {
    requiredValues.is_active = true;
  }
  if (columnNames.has("is_first_login")) {
    requiredValues.is_first_login = true;
  }

  const insertColumns = Object.keys(requiredValues);
  if (!insertColumns.length) {
    return;
  }

  const placeholders = insertColumns.map(() => "?").join(", ");
  const escapedColumns = insertColumns.map((column) => `\`${column}\``).join(", ");
  await pool.execute(
    `INSERT INTO users (${escapedColumns}) VALUES (${placeholders})`,
    insertColumns.map((column) => requiredValues[column]),
  );
}

async function getTableColumns(tableName) {
  const [columns] = await pool.execute(
    `SELECT COLUMN_NAME, EXTRA, CHARACTER_MAXIMUM_LENGTH
     FROM INFORMATION_SCHEMA.COLUMNS
     WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?`,
    [env.db.database, tableName],
  );
  return columns;
}

async function addColumnIfMissing(tableName, columnName, definition) {
  const [columns] = await pool.execute(
    `SELECT COLUMN_NAME
     FROM INFORMATION_SCHEMA.COLUMNS
     WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND COLUMN_NAME = ?
     LIMIT 1`,
    [env.db.database, tableName, columnName],
  );

  if (!columns.length) {
    await pool.query(`ALTER TABLE \`${tableName}\` ADD COLUMN \`${columnName}\` ${definition}`);
  }
}

async function addUniqueIndexIfMissing(tableName, indexName, columnName) {
  const [indexes] = await pool.execute(
    `SELECT INDEX_NAME
     FROM INFORMATION_SCHEMA.STATISTICS
     WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND INDEX_NAME = ?
     LIMIT 1`,
    [env.db.database, tableName, indexName],
  );

  if (!indexes.length) {
    await pool.query(`CREATE UNIQUE INDEX \`${indexName}\` ON \`${tableName}\` (\`${columnName}\`)`);
  }
}

export function getPool() {
  if (!pool) {
    throw new Error("Database has not been initialized");
  }
  return pool;
}
