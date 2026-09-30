import bcrypt from 'bcryptjs';
import crypto from 'crypto';

const SALT_ROUNDS = 10;

/**
 * Hash password using bcrypt
 */
export const hashPassword = async (password: string): Promise<string> => {
  return bcrypt.hash(password, SALT_ROUNDS);
};

export const hashPasswordSync = (password: string): string => {
  return bcrypt.hashSync(password, SALT_ROUNDS);
};

/**
 * Verify password against bcrypt hash or legacy scrypt hash (salt:derivedKey)
 */
export const verifyPassword = async (password: string, storedHash: string | null | undefined): Promise<boolean> => {
  if (!storedHash) return false;

  // Check if legacy scrypt format (salt:hash)
  if (storedHash.includes(':')) {
    try {
      const [salt, hash] = storedHash.split(':');
      if (!salt || !hash) return false;
      const derivedKey = crypto.scryptSync(password, salt, 64).toString('hex');
      return crypto.timingSafeEqual(Buffer.from(hash, 'hex'), Buffer.from(derivedKey, 'hex'));
    } catch {
      return false;
    }
  }

  // Otherwise, bcrypt compare
  return bcrypt.compare(password, storedHash);
};
