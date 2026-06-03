import crypto from "crypto";
import pg from "pg";
import { env } from "./env.js";
import { hashPassword } from "../utils/password.js";

const { Pool } = pg;

let pool;

function normalizeDatabaseUrl(databaseUrl) {
  if (databaseUrl.startsWith("postgresql+psycopg2://") || databaseUrl.startsWith("postgresql+psycopg://")) {
    return databaseUrl.replace(/^postgresql\+psycopg2?:\/\//, "postgresql://");
  }
  return databaseUrl;
}

function shouldUseSsl(databaseUrl) {
  return /sslmode=require/i.test(databaseUrl) || /neon\.tech/i.test(databaseUrl);
}

export async function initializeDatabase() {
  const connectionString = normalizeDatabaseUrl(env.databaseUrl);
  pool = new Pool({
    connectionString,
    ssl: shouldUseSsl(connectionString) ? { rejectUnauthorized: false } : undefined,
    max: 10,
  });

  await pool.query("CREATE EXTENSION IF NOT EXISTS pgcrypto");

  await pool.query(`
    CREATE TABLE IF NOT EXISTS roles (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      code VARCHAR(50) UNIQUE NOT NULL,
      name VARCHAR(100) NOT NULL,
      hierarchy_rank INTEGER NOT NULL DEFAULT 100,
      description TEXT NULL,
      is_system BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
  `);

  await pool.query(`
    CREATE TABLE IF NOT EXISTS users (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      employee_id VARCHAR(50) UNIQUE,
      full_name VARCHAR(100),
      first_name VARCHAR(100),
      last_name VARCHAR(100),
      email VARCHAR(100) UNIQUE,
      password_hash VARCHAR(255),
      role_id UUID NULL,
      role VARCHAR(30) NOT NULL DEFAULT 'Employee',
      status VARCHAR(30) NOT NULL DEFAULT 'Active',
      is_active BOOLEAN NOT NULL DEFAULT TRUE,
      is_first_login BOOLEAN NOT NULL DEFAULT TRUE,
      last_login_at TIMESTAMPTZ NULL,
      created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
  `);

  await addColumnIfMissing("users", "employee_id", "VARCHAR(50) NULL");
  await addColumnIfMissing("users", "full_name", "VARCHAR(100) NULL");
  await addColumnIfMissing("users", "first_name", "VARCHAR(100) NULL");
  await addColumnIfMissing("users", "last_name", "VARCHAR(100) NULL");
  await addColumnIfMissing("users", "email", "VARCHAR(100) NULL");
  await addColumnIfMissing("users", "password_hash", "VARCHAR(255) NULL");
  await addColumnIfMissing("users", "role_id", "UUID NULL");
  await addColumnIfMissing("users", "role", "VARCHAR(30) NULL");
  await addColumnIfMissing("users", "status", "VARCHAR(30) NULL");
  await addColumnIfMissing("users", "is_active", "BOOLEAN NOT NULL DEFAULT TRUE");
  await addColumnIfMissing("users", "is_first_login", "BOOLEAN NOT NULL DEFAULT TRUE");
  await addColumnIfMissing("users", "last_login_at", "TIMESTAMPTZ NULL");
  await addColumnIfMissing("users", "created_at", "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP");
  await addColumnIfMissing("users", "updated_at", "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP");
  await addUniqueIndexIfMissing("users", "idx_users_employee_id_unique", "employee_id");
  await addUniqueIndexIfMissing("users", "idx_users_email_unique", "email");

  await pool.query(`
    CREATE TABLE IF NOT EXISTS user_sessions (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id UUID NOT NULL,
      refresh_token_hash VARCHAR(255) NOT NULL,
      user_agent VARCHAR(255),
      ip_address VARCHAR(64),
      access_jti VARCHAR(64) NOT NULL DEFAULT gen_random_uuid()::text,
      refresh_jti VARCHAR(64) NOT NULL DEFAULT gen_random_uuid()::text,
      device_name VARCHAR(120) NULL,
      device_type VARCHAR(60) NULL,
      last_activity_at TIMESTAMPTZ NULL,
      expires_at TIMESTAMPTZ NOT NULL,
      revoked_at TIMESTAMPTZ NULL,
      created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT fk_user_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
  `);
  await addColumnIfMissing("user_sessions", "access_jti", "VARCHAR(64) NOT NULL DEFAULT gen_random_uuid()::text");
  await addColumnIfMissing("user_sessions", "refresh_jti", "VARCHAR(64) NOT NULL DEFAULT gen_random_uuid()::text");
  await addColumnIfMissing("user_sessions", "device_name", "VARCHAR(120) NULL");
  await addColumnIfMissing("user_sessions", "device_type", "VARCHAR(60) NULL");
  await addColumnIfMissing("user_sessions", "last_activity_at", "TIMESTAMPTZ NULL");
  await addColumnIfMissing("user_sessions", "updated_at", "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP");
  await addIndexIfMissing("user_sessions", "idx_user_sessions_user_id", "user_id");

  await seedDefaultRoles();
  await seedDefaultAdmin();
}

async function seedDefaultRoles() {
  const roles = [
    ["super_admin", "Super Admin", 1],
    ["admin", "Admin", 2],
    ["hr", "HR", 3],
    ["employee", "Employee", 5],
  ];

  for (const [code, name, hierarchyRank] of roles) {
    await pool.query(
      `INSERT INTO roles (code, name, hierarchy_rank)
       VALUES ($1, $2, $3)
       ON CONFLICT (code) DO NOTHING`,
      [code, name, hierarchyRank],
    );
  }
}

async function seedDefaultAdmin() {
  const { rows } = await pool.query("SELECT id FROM users WHERE email = $1 LIMIT 1", [env.defaultAdmin.email]);
  if (rows.length) {
    return;
  }

  const columns = await getTableColumns("users");
  const columnNames = new Set(columns.map((column) => column.COLUMN_NAME));
  const requiredValues = {};
  const passwordHash = await hashPassword(env.defaultAdmin.password);
  const nameParts = env.defaultAdmin.fullName.split(/\s+/);

  const idColumn = columns.find((column) => column.COLUMN_NAME === "id");
  if (columnNames.has("id") && !idColumn?.COLUMN_DEFAULT) {
    requiredValues.id = crypto.randomUUID();
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
    const { rows: roles } = await pool.query(
      "SELECT id FROM roles WHERE code IN ('super_admin', 'admin', 'Admin') OR name IN ('Super Admin', 'Admin') ORDER BY hierarchy_rank ASC LIMIT 1",
    );
    if (!roles.length) {
      return;
    }
    requiredValues.role_id = roles[0].id;
  }
  if (columnNames.has("status")) {
    requiredValues.status = columnNames.has("role_id") ? "active" : "Active";
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

  const placeholders = insertColumns.map((_, index) => `$${index + 1}`).join(", ");
  const escapedColumns = insertColumns.map((column) => `"${column}"`).join(", ");
  await pool.query(
    `INSERT INTO users (${escapedColumns}) VALUES (${placeholders})`,
    insertColumns.map((column) => requiredValues[column]),
  );
}

async function getTableColumns(tableName) {
  const { rows } = await pool.query(
    `SELECT column_name AS "COLUMN_NAME",
            column_default AS "COLUMN_DEFAULT",
            character_maximum_length AS "CHARACTER_MAXIMUM_LENGTH"
     FROM information_schema.columns
     WHERE table_schema = current_schema() AND table_name = $1`,
    [tableName],
  );
  return rows;
}

async function addColumnIfMissing(tableName, columnName, definition) {
  const { rows } = await pool.query(
    `SELECT column_name
     FROM information_schema.columns
     WHERE table_schema = current_schema() AND table_name = $1 AND column_name = $2
     LIMIT 1`,
    [tableName, columnName],
  );

  if (!rows.length) {
    await pool.query(`ALTER TABLE "${tableName}" ADD COLUMN "${columnName}" ${definition}`);
  }
}

async function addIndexIfMissing(tableName, indexName, columnName) {
  const { rows } = await pool.query("SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = $1 LIMIT 1", [indexName]);
  if (!rows.length) {
    await pool.query(`CREATE INDEX "${indexName}" ON "${tableName}" ("${columnName}")`);
  }
}

async function addUniqueIndexIfMissing(tableName, indexName, columnName) {
  const { rows } = await pool.query("SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = $1 LIMIT 1", [indexName]);
  if (!rows.length) {
    await pool.query(`CREATE UNIQUE INDEX "${indexName}" ON "${tableName}" ("${columnName}")`);
  }
}

export function getPool() {
  if (!pool) {
    throw new Error("Database has not been initialized");
  }
  return pool;
}
