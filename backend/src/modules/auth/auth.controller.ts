import { Request, Response, NextFunction } from 'express';
import { authService } from './auth.service';
import { sendSuccess } from '../../shared/responses/api-response';
import { UnauthorizedError } from '../../shared/errors/app-error';
import { verifyToken } from '../../shared/utils/jwt';

export const requestRegisterOtp = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await authService.requestRegisterOtp(req.body);
    return sendSuccess(res, result, 'Verification code sent');
  } catch (error) {
    next(error);
  }
};

export const verifyRegisterOtp = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await authService.verifyRegisterOtp(req.body);
    return sendSuccess(res, result, 'Registration successful', 201);
  } catch (error) {
    next(error);
  }
};

export const login = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await authService.login(req.body);
    return sendSuccess(res, result, 'Login successful');
  } catch (error) {
    next(error);
  }
};

export const forgotPassword = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await authService.forgotPassword(req.body);
    return sendSuccess(res, result, 'Reset code sent');
  } catch (error) {
    next(error);
  }
};

export const verifyResetCode = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await authService.verifyResetCode(req.body);
    return sendSuccess(res, result, 'Code verified successfully');
  } catch (error) {
    next(error);
  }
};

export const resetPassword = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await authService.resetPassword(req.body);
    return sendSuccess(res, result, 'Password has been reset');
  } catch (error) {
    next(error);
  }
};

export const getValidateToken = async (req: Request, res: Response, next: NextFunction) => {
  try {
    // Check if authorization header is provided or token is in body
    const authHeader = req.headers.authorization;
    const token = authHeader?.startsWith('Bearer ') ? authHeader.split(' ')[1] : req.body.token;

    if (!token) {
      throw new UnauthorizedError('Token is required');
    }

    const decoded = verifyToken(token);
    const result = await authService.validateToken(decoded.accountId);
    return sendSuccess(res, result, 'Token is valid');
  } catch (error) {
    next(error);
  }
};

export const getEmailConfigStatus = (req: Request, res: Response) => {
  const result = authService.getEmailConfigStatus();
  return sendSuccess(res, result);
};
