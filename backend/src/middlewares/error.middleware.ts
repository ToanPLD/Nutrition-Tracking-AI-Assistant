import { NextFunction, Request, Response } from 'express';
import { AppError } from '../shared/errors/app-error';
import { sendError } from '../shared/responses/api-response';

export const errorHandler = (
  err: any,
  req: Request,
  res: Response,
  next: NextFunction
) => {
  // If response headers already sent, delegate to Express default handler
  if (res.headersSent) {
    return next(err);
  }

  // Handle known AppError
  if (err instanceof AppError) {
    return sendError(res, err.statusCode, err.message, err.code);
  }

  // Handle MySQL errors
  if (err.code === 'ER_DUP_ENTRY') {
    return sendError(res, 409, 'Duplicate entry found. The record already exists.', 'DUPLICATE_ENTRY');
  }

  if (err.code === 'ECONNREFUSED') {
    return sendError(
      res,
      503,
      'Database connection failed. Please ensure the database service is running.',
      'DATABASE_UNAVAILABLE'
    );
  }

  if (err.code === 'ER_NO_SUCH_TABLE') {
    return sendError(
      res,
      500,
      'Database table is missing. Schema initialization may be required.',
      'SCHEMA_ERROR'
    );
  }

  // Generic unhandled internal error
  console.error('[Unhandled Error]', err);
  const message = process.env.NODE_ENV === 'production' ? 'Internal server error' : err.message || 'Internal server error';
  return sendError(res, 500, message, 'INTERNAL_SERVER_ERROR');
};
