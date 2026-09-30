import cors from 'cors';
import express from 'express';
import { corsOptions } from './config/cors';
import { isDatabaseReady } from './database/connection';
import { requireAuth } from './middlewares/auth.middleware';
import { requireRole } from './middlewares/role.middleware';
import { errorHandler } from './middlewares/error.middleware';
import { notFoundHandler } from './middlewares/notFound.middleware';

// Route modules
import authRouter from './modules/auth/auth.routes';
import userRouter from './modules/user/user.routes';
import adminRouter from './modules/admin/admin.routes';
import chatRouter from './modules/chat/chat.routes';

const app = express();

// Global Middlewares
app.use(cors(corsOptions));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Health Check Endpoints
app.get('/', (req, res) => {
  res.status(200).json({
    status: 'ok',
    message: 'CalAI Backend API is running',
    database: isDatabaseReady() ? 'mysql-connected' : 'embedded-local',
    timestamp: new Date().toISOString(),
  });
});

app.get('/api/health', (req, res) => {
  res.status(200).json({
    status: 'ok',
    database: isDatabaseReady() ? 'mysql-connected' : 'embedded-local',
    uptime: Math.floor(process.uptime()),
    timestamp: new Date().toISOString(),
  });
});

// Mount Module Routes
app.use('/api/auth', authRouter);
app.use('/api/users', requireAuth, requireRole('user', 'admin'), userRouter);
app.use('/api/admin', requireAuth, requireRole('admin'), adminRouter);
app.use('/api/chat', requireAuth, requireRole('user', 'admin'), chatRouter);

// 404 & Centralized Error Handlers
app.use(notFoundHandler);
app.use(errorHandler);

export default app;
