import mysql from 'mysql2/promise';
import { ENV } from '../config/env';

let databaseConnected = false;
let reconnectTimer: NodeJS.Timeout | null = null;

export const pool = mysql.createPool({
  host: ENV.DB_HOST,
  port: ENV.DB_PORT,
  user: ENV.DB_USER,
  password: ENV.DB_PASSWORD,
  database: ENV.DB_NAME,
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0,
  enableKeepAlive: true,
  keepAliveInitialDelay: 10000,
});

export const isDatabaseReady = (): boolean => databaseConnected;

/**
 * Ensures the target database exists before using it
 */
export const ensureDatabaseExists = async (): Promise<boolean> => {
  try {
    const adminConnection = await mysql.createConnection({
      host: ENV.DB_HOST,
      port: ENV.DB_PORT,
      user: ENV.DB_USER,
      password: ENV.DB_PASSWORD,
    });

    const safeDbName = `\`${ENV.DB_NAME.replace(/`/g, '``')}\``;
    await adminConnection.query(
      `CREATE DATABASE IF NOT EXISTS ${safeDbName} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci`
    );
    await adminConnection.end();
    return true;
  } catch (error) {
    return false;
  }
};

/**
 * Tests connection to MySQL pool
 */
export const testConnection = async (): Promise<boolean> => {
  try {
    await ensureDatabaseExists();
    const connection = await pool.getConnection();
    await connection.ping();
    connection.release();
    databaseConnected = true;
    return true;
  } catch (error) {
    databaseConnected = false;
    return false;
  }
};

/**
 * Starts background retry mechanism until DB is connected
 */
export const startDatabaseWatcher = (onConnectSuccess?: () => void) => {
  if (databaseConnected) return;

  if (reconnectTimer) clearInterval(reconnectTimer);

  reconnectTimer = setInterval(async () => {
    const ok = await testConnection();
    if (ok) {
      console.log('✅ [Database] MySQL connection established successfully!');
      if (reconnectTimer) {
        clearInterval(reconnectTimer);
        reconnectTimer = null;
      }
      if (onConnectSuccess) {
        try {
          await onConnectSuccess();
        } catch (e) {
          console.error('[Database] Post-connect initializer error:', e);
        }
      }
    } else {
      // Keep quiet or log subtle retry
      // console.log('[Database] Retrying MySQL connection...');
    }
  }, 5000);
};
