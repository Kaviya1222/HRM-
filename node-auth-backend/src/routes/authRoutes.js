import { Router } from "express";
import { changeFirstLoginPassword, forgotPassword, login, logout, me, refresh, resetPassword } from "../controllers/authController.js";
import { authenticate } from "../middleware/authMiddleware.js";

const router = Router();

router.post("/login", login);
router.post("/logout", authenticate, logout);
router.post("/forgot-password", forgotPassword);
router.post("/reset-password", resetPassword);
router.post("/first-login-password", changeFirstLoginPassword);
router.post("/refresh", refresh);
router.get("/me", authenticate, me);

export default router;
