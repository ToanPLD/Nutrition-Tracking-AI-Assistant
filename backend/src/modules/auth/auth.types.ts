export interface RegisterOtpDto {
  email: string;
  password: string;
  username: string;
}

export interface VerifyRegisterOtpDto {
  email: string;
  code: string;
}

export interface LoginDto {
  email: string;
  password: string;
}

export interface ForgotPasswordDto {
  email: string;
}

export interface VerifyResetCodeDto {
  email: string;
  code: string;
}

export interface ResetPasswordDto {
  email: string;
  code: string;
  newPassword: string;
}

export interface AccountRecord {
  account_id: number;
  email: string;
  password_hash: string | null;
  email_verified: number;
  status: string;
  role_name: string;
  user_id?: number;
  full_name?: string;
}
