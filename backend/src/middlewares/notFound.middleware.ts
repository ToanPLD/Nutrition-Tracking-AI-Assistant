import { Request, Response } from 'express';
import { sendError } from '../shared/responses/api-response';

export const notFoundHandler = (req: Request, res: Response) => {
  return sendError(res, 404, `Route ${req.method} ${req.originalUrl} not found`, 'ROUTE_NOT_FOUND');
};
