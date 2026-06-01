import app from "./app.js";
import { env } from "./config/env.js";
import { initializeDatabase } from "./config/database.js";

async function startServer() {
  try {
    await initializeDatabase();
    app.listen(env.port, () => {
      console.log(`HRM auth server running on http://localhost:${env.port}`);
    });
  } catch (error) {
    console.error("Failed to start HRM auth server:", error.message);
    process.exit(1);
  }
}

void startServer();
