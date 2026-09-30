import jwt, { SignOptions } from 'jsonwebtoken';
import { ENV } from '../../config/env';

export interface TokenPayload {
  accountId: number;
  email: string;
  role: string;
}

export const signToken = (payload: TokenPayload, expiresIn?: SignOptions['expiresIn']): string => {
  return jwt.sign(payload, ENV.JWT_SECRET, {
    expiresIn: expiresIn || (ENV.JWT_EXPIRES_IN as SignOptions['expiresIn']),
  });
};

export const verifyToken = (token: string): TokenPayload => {
  return jwt.verify(token, ENV.JWT_SECRET) as TokenPayload;
};
