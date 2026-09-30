import { dbQuery, dbQueryOne, dbExecute } from '../../database/query';
import { hashPassword, verifyPassword } from '../../shared/utils/hash';
import { signToken } from '../../shared/utils/jwt';
import { isMailerConfigured, sendOtpEmail } from '../../shared/utils/mailer';
import { BadRequestError, ConflictError, NotFoundError, UnauthorizedError } from '../../shared/errors/app-error';
import {
  AccountRecord,
  ForgotPasswordDto,
  LoginDto,
  RegisterOtpDto,
  ResetPasswordDto,
  VerifyRegisterOtpDto,
  VerifyResetCodeDto,
} from './auth.types';

// OTP caches
const registerOtps = new Map<string, { code: string; expiresAt: number; password: string; username: string }>();
const resetCodes = new Map<string, { code: string; expiresAt: number }>();

export class AuthService {
  /**
   * Find account by email with role & profile info
   */
  async getAccountByEmail(email: string): Promise<AccountRecord | null> {
    const sql = `
      SELECT
        a.account_id,
        a.email,
        a.password_hash,
        a.email_verified,
        a.status,
        COALESCE(r.role_name, 'user') AS role_name,
        u.user_id,
        u.full_name
      FROM accounts a
      LEFT JOIN accountroles ar ON ar.account_id = a.account_id
      LEFT JOIN roles r ON r.role_id = ar.role_id
      LEFT JOIN users u ON u.account_id = a.account_id
      WHERE LOWER(a.email) = LOWER(?)
      LIMIT 1
    `;
    return dbQueryOne<any>(sql, [email]);
  }

  /**
   * Find account by accountId
   */
  async getAccountById(accountId: number): Promise<AccountRecord | null> {
    const sql = `
      SELECT
        a.account_id,
        a.email,
        a.password_hash,
        a.email_verified,
        a.status,
        COALESCE(r.role_name, 'user') AS role_name,
        u.user_id,
        u.full_name
      FROM accounts a
      LEFT JOIN accountroles ar ON ar.account_id = a.account_id
      LEFT JOIN roles r ON r.role_id = ar.role_id
      LEFT JOIN users u ON u.account_id = a.account_id
      WHERE a.account_id = ?
      LIMIT 1
    `;
    return dbQueryOne<any>(sql, [accountId]);
  }

  /**
   * Step 1: Request OTP for register
   */
  async requestRegisterOtp({ email, password, username }: RegisterOtpDto) {
    if (!email || !password || !username) {
      throw new BadRequestError('Email, password, and username are required');
    }
    if (username.trim().length < 2) {
      throw new BadRequestError('Username must be at least 2 characters');
    }
    if (password.length < 6) {
      throw new BadRequestError('Password must be at least 6 characters');
    }

    const existing = await this.getAccountByEmail(email);
    if (existing) {
      throw new ConflictError('Email already registered', 'EMAIL_ALREADY_EXISTS');
    }

    const code = String(Math.floor(100000 + Math.random() * 900000));
    registerOtps.set(email.toLowerCase(), {
      code,
      password,
      username: username.trim(),
      expiresAt: Date.now() + 10 * 60 * 1000,
    });

    const emailSent = await sendOtpEmail(email, 'CalAI Register Verification', 'Register verification code', code);

    return {
      email,
      expiresInMinutes: 10,
      emailSent,
      previewCode: emailSent ? undefined : code,
    };
  }

  /**
   * Step 2: Verify OTP and create user
   */
  async verifyRegisterOtp({ email, code }: VerifyRegisterOtpDto) {
    const pending = registerOtps.get(email.toLowerCase());
    if (!pending || pending.expiresAt < Date.now() || pending.code !== code) {
      throw new BadRequestError('Invalid or expired registration code', 'INVALID_REGISTER_OTP');
    }

    const existing = await this.getAccountByEmail(email);
    if (existing) {
      throw new ConflictError('Email already registered', 'EMAIL_ALREADY_EXISTS');
    }

    const hashedPassword = await hashPassword(pending.password);

    // Insert account
    const accResult = await dbExecute(
      'INSERT INTO accounts (email, password_hash, email_verified, status) VALUES (?, ?, 1, ?)',
      [email.toLowerCase(), hashedPassword, 'active']
    );
    const accountId = accResult.insertId;

    // Assign 'user' role
    const [roleRows] = await dbQuery<any[]>("SELECT role_id FROM roles WHERE role_name = 'user' LIMIT 1");
    if (roleRows.length > 0) {
      await dbExecute('INSERT INTO accountroles (account_id, role_id) VALUES (?, ?)', [
        accountId,
        roleRows[0].role_id,
      ]);
    }

    // Insert user profile
    await dbExecute(
      'INSERT INTO users (account_id, full_name, has_completed_setup) VALUES (?, ?, 0)',
      [accountId, pending.username]
    );

    registerOtps.delete(email.toLowerCase());

    const token = signToken({ accountId, email, role: 'user' });

    return {
      accountId,
      email,
      role: 'user',
      token,
    };
  }

  /**
   * Login
   */
  async login({ email, password }: LoginDto) {
    if (!email || !password) {
      throw new BadRequestError('Email and password are required');
    }

    const account = await this.getAccountByEmail(email);
    if (!account) {
      throw new UnauthorizedError('Invalid email or password', 'INVALID_CREDENTIALS');
    }

    const isMatch = await verifyPassword(password, account.password_hash);
    if (!isMatch) {
      throw new UnauthorizedError('Invalid email or password', 'INVALID_CREDENTIALS');
    }

    if (!account.email_verified) {
      throw new UnauthorizedError('Email is not verified', 'EMAIL_NOT_VERIFIED');
    }

    if (account.status === 'suspended') {
      throw new UnauthorizedError('Account is suspended. Please contact admin.', 'ACCOUNT_SUSPENDED');
    }

    const role = (account.role_name || 'user').toLowerCase();
    const token = signToken({ accountId: account.account_id, email: account.email, role });

    return {
      accountId: account.account_id,
      userId: account.user_id,
      email: account.email,
      role,
      status: account.status,
      token,
    };
  }

  /**
   * Request forgot password OTP
   */
  async forgotPassword({ email }: ForgotPasswordDto) {
    const account = await this.getAccountByEmail(email);
    if (!account) {
      throw new NotFoundError('Account with this email does not exist', 'ACCOUNT_NOT_FOUND');
    }

    const code = String(Math.floor(100000 + Math.random() * 900000));
    resetCodes.set(email.toLowerCase(), {
      code,
      expiresAt: Date.now() + 10 * 60 * 1000,
    });

    const emailSent = await sendOtpEmail(email, 'CalAI Password Reset', 'Reset password code', code);

    return {
      email,
      expiresInMinutes: 10,
      emailSent,
      previewCode: emailSent ? undefined : code,
    };
  }

  /**
   * Verify reset code
   */
  async verifyResetCode({ email, code }: VerifyResetCodeDto) {
    const stored = resetCodes.get(email.toLowerCase());
    if (!stored || stored.expiresAt < Date.now() || stored.code !== code) {
      throw new BadRequestError('Invalid or expired reset code', 'INVALID_RESET_CODE');
    }
    return { email, verified: true };
  }

  /**
   * Reset password
   */
  async resetPassword({ email, code, newPassword }: ResetPasswordDto) {
    if (!newPassword || newPassword.length < 6) {
      throw new BadRequestError('Password must be at least 6 characters');
    }

    const stored = resetCodes.get(email.toLowerCase());
    if (!stored || stored.expiresAt < Date.now() || stored.code !== code) {
      throw new BadRequestError('Invalid or expired reset code', 'INVALID_RESET_CODE');
    }

    const account = await this.getAccountByEmail(email);
    if (!account) {
      throw new NotFoundError('Account not found', 'ACCOUNT_NOT_FOUND');
    }

    const hashedPassword = await hashPassword(newPassword);
    await dbExecute('UPDATE accounts SET password_hash = ? WHERE account_id = ?', [
      hashedPassword,
      account.account_id,
    ]);

    resetCodes.delete(email.toLowerCase());

    const role = (account.role_name || 'user').toLowerCase();
    const token = signToken({ accountId: account.account_id, email: account.email, role });

    return {
      accountId: account.account_id,
      email: account.email,
      role,
      token,
    };
  }

  /**
   * Validate token and return user profile
   */
  async validateToken(accountId: number) {
    const account = await this.getAccountById(accountId);
    if (!account) {
      throw new NotFoundError('Account not found', 'ACCOUNT_NOT_FOUND');
    }

    const role = (account.role_name || 'user').toLowerCase();
    return {
      accountId: account.account_id,
      userId: account.user_id,
      email: account.email,
      role,
      status: account.status,
      fullName: account.full_name,
    };
  }

  getEmailConfigStatus() {
    return { configured: isMailerConfigured };
  }
}

export const authService = new AuthService();
