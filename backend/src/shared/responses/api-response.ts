import { Response } from 'express';

export interface StandardResponse<T = any> {
  success: boolean;
  message?: string;
  data?: T;
  error?: {
    code?: string;
    message: string;
    details?: any;
  };
}

export const sendSuccess = <T>(
  res: Response,
  data?: T,
  message?: string,
  statusCode = 200
): Response => {
  const payload: StandardResponse<T> = {
    success: true,
  };
  if (message) payload.message = message;
  if (data !== undefined) payload.data = data;
  return res.status(statusCode).json(payload);
};

export const sendCreated = <T>(res: Response, data?: T, message = 'Resource created successfully'): Response => {
  return sendSuccess(res, data, message, 201);
};

export const sendError = (
  res: Response,
  statusCode = 500,
  message = 'Internal Server Error',
  code?: string,
  details?: any
): Response => {
  return res.status(statusCode).json({
    success: false,
    message,
    error: {
      code,
      message,
      ...(details ? { details } : {}),
    },
  });
};
