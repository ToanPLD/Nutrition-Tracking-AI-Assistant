import http from 'http';
import app from './app';
import { ENV } from './config/env';
import { testConnection, startDatabaseWatcher } from './database/connection';
import { initializeDatabaseSchema } from './database/init';

import { localStore } from './database/local-store';

const startServer = async () => {
  const server = http.createServer(app);

  // 1. Initial Database Connection Attempt
  console.log(`[Database] Connecting to MySQL at ${ENV.DB_HOST}:${ENV.DB_PORT}/${ENV.DB_NAME}...`);
  const isConnected = await testConnection();

  if (isConnected) {
    console.log('✅ [Database] MySQL connected successfully!');
    try {
      await initializeDatabaseSchema();
    } catch (err) {
      console.error('[Database] Schema initialization error:', err);
    }
  } else {
    console.warn(
      `⚠️  [Database] Cannot connect to MySQL at ${ENV.DB_HOST}:${ENV.DB_PORT}.`
    );
    console.log(
      '💡 [Database] Running in Standalone Embedded Mode (Zero config: no MySQL, Ollama, or Python needed)!'
    );
    localStore.init();
    startDatabaseWatcher(async () => {
      await initializeDatabaseSchema();
    });
  }

  // 2. Start HTTP Server
  server.listen(ENV.PORT, () => {
    console.log(`🚀 [CalAI Backend] Server listening on http://localhost:${ENV.PORT}`);
    console.log(`   Health Check: http://localhost:${ENV.PORT}/api/health`);
    console.log(`   Environment: ${ENV.NODE_ENV}`);
  });

  // 3. Graceful Shutdown
  const shutdown = (signal: string) => {
    console.log(`\n[Server] Received ${signal}. Shutting down gracefully...`);
    server.close(() => {
      console.log('[Server] HTTP server closed.');
      process.exit(0);
    });

    // Force exit after 5 seconds if hanging
    setTimeout(() => {
      console.error('[Server] Forced exit after timeout.');
      process.exit(1);
    }, 5000);
  };

  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
};

startServer().catch((error) => {
  console.error('[Server] Fatal startup error:', error);
  process.exit(1);
});
