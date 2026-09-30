import { pool, isDatabaseReady } from './connection';
import { executeMockSql } from './mock-engine';
import { ResultSetHeader, RowDataPacket } from 'mysql2/promise';

export interface TransactionConnection {
  query<T = any>(sql: string, params?: any[]): Promise<[T, ...any[]]>;
  execute<T = any>(sql: string, params?: any[]): Promise<[T, ...any[]]>;
}

/**
 * Execute a query with parameters, returns rows
 */
export const dbQuery = async <T extends RowDataPacket[]>(
  sql: string,
  params: any[] = []
): Promise<T> => {
  if (isDatabaseReady()) {
    const [rows] = await pool.query<T>(sql, params);
    return rows;
  }
  const { rows } = executeMockSql(sql, params);
  return (rows || []) as T;
};

/**
 * Execute an INSERT, UPDATE, DELETE query, returns ResultSetHeader
 */
export const dbExecute = async (
  sql: string,
  params: any[] = []
): Promise<ResultSetHeader> => {
  if (isDatabaseReady()) {
    const [result] = await pool.execute<ResultSetHeader>(sql, params);
    return result;
  }
  const { result } = executeMockSql(sql, params);
  return result as ResultSetHeader;
};

/**
 * Execute a query and return the first row or null
 */
export const dbQueryOne = async <T extends RowDataPacket>(
  sql: string,
  params: any[] = []
): Promise<T | null> => {
  const rows = await dbQuery<T[]>(sql, params);
  return rows.length > 0 ? rows[0] : null;
};

/**
 * Run operations within a database transaction
 */
export const dbTransaction = async <T>(
  callback: (connection: TransactionConnection) => Promise<T>
): Promise<T> => {
  if (isDatabaseReady()) {
    const connection = await pool.getConnection();
    try {
      await connection.beginTransaction();
      const result = await callback(connection as unknown as TransactionConnection);
      await connection.commit();
      return result;
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  }

  // Mock transaction object in offline mode
  const mockConn: TransactionConnection = {
    query: async <R = any>(sql: string, params: any[] = []) => {
      const { rows } = executeMockSql(sql, params);
      return [(rows || []) as unknown as R];
    },
    execute: async <R = any>(sql: string, params: any[] = []) => {
      const { result } = executeMockSql(sql, params);
      return [result as unknown as R];
    },
  };

  return callback(mockConn);
};
