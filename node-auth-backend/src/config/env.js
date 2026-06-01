import dotenv from "dotenv";

dotenv.config();

export const env = {
  nodeEnv: process.env.NODE_ENV || "development",
  port: Number(process.env.PORT || 3001),
  frontendUrl: process.env.FRONTEND_URL || "http://localhost:5173",
  db: {
    host: process.env.DB_HOST || "localhost",
    user: process.env.DB_USER || "root",
    password: process.env.DB_PASSWORD || "root",
    database: process.env.DB_NAME || "hrm_db",
  },
  jwt: {
    accessSecret: process.env.JWT_ACCESS_SECRET || "hrm_access_secret_change_me",
    refreshSecret: process.env.JWT_REFRESH_SECRET || "hrm_refresh_secret_change_me",
    resetSecret: process.env.JWT_RESET_SECRET || "hrm_reset_secret_change_me",
    accessExpiresIn: process.env.JWT_ACCESS_EXPIRES_IN || "15m",
    refreshExpiresIn: process.env.JWT_REFRESH_EXPIRES_IN || "7d",
  },
  sessionSecret: process.env.SESSION_SECRET || "hrm_session_secret_change_me",
  defaultAdmin: {
    employeeId: process.env.DEFAULT_ADMIN_EMPLOYEE_ID || "ADM001",
    fullName: process.env.DEFAULT_ADMIN_NAME || "System Admin",
    email: (process.env.DEFAULT_ADMIN_EMAIL || "admin@hrm.com").toLowerCase(),
    password: process.env.DEFAULT_ADMIN_PASSWORD || "Admin@123",
  },
};
