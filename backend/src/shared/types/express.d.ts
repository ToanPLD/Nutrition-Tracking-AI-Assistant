import 'express';

declare global {
  namespace Express {
    interface Request {
      user?: {
        accountId: number;
        email: string;
        role: string;
      };
    }
  }
}
