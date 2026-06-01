import bcrypt from "bcrypt";
import crypto from "crypto";

const SALT_ROUNDS = 12;

export function hashPassword(password) {
  return bcrypt.hash(password, SALT_ROUNDS);
}

export function verifyPassword(password, passwordHash) {
  return bcrypt.compare(password, passwordHash).then((isMatch) => {
    if (isMatch) {
      return true;
    }
    const preHashedPassword = crypto.createHash("sha256").update(password).digest("hex");
    return bcrypt.compare(preHashedPassword, passwordHash);
  });
}
