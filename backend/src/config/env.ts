import dotenv from 'dotenv';
import path from 'path';

// Load .env from backend root or current directory
dotenv.config({ path: path.resolve(process.cwd(), '.env') });
dotenv.config();

export const ENV = {
  NODE_ENV: process.env.NODE_ENV || 'development',
  PORT: Number(process.env.PORT) || 3000,

  // Database
  DB_HOST: process.env.DB_HOST || 'localhost',
  DB_PORT: Number(process.env.DB_PORT) || 3306,
  DB_USER: process.env.DB_USER || 'root',
  DB_PASSWORD: process.env.DB_PASSWORD || '',
  DB_NAME: process.env.DB_NAME || 'calai',

  // JWT
  JWT_SECRET: process.env.JWT_SECRET || 'calai-secure-secret-key-2026',
  JWT_EXPIRES_IN: process.env.JWT_EXPIRES_IN || '7d',

  // Email (SMTP)
  SMTP_HOST: process.env.SMTP_HOST || 'smtp.gmail.com',
  SMTP_PORT: Number(process.env.SMTP_PORT) || 587,
  SMTP_USER: process.env.SMTP_USER || '',
  SMTP_PASS: process.env.SMTP_PASS || '',
  SMTP_FROM: process.env.SMTP_FROM || 'no-reply@calai.local',

  // AI & External Services
  CAL_AI_BASE_URL: process.env.CAL_AI_BASE_URL || 'http://localhost:8000',
  CAL_AI_QUERY_TIMEOUT_MS: Number(process.env.CAL_AI_QUERY_TIMEOUT_MS) || 60000,
  CAL_AI_VISION_TIMEOUT_MS: Number(process.env.CAL_AI_VISION_TIMEOUT_MS) || 120000,

  OLLAMA_BASE_URL: process.env.OLLAMA_BASE_URL || 'http://localhost:11434',
  OLLAMA_MODEL: process.env.OLLAMA_MODEL || 'llama3.2',
};
