import fs from 'fs';
import path from 'path';
import { pool, isDatabaseReady } from './connection';
import { hashPassword } from '../shared/utils/hash';

export const initializeDatabaseSchema = async (): Promise<void> => {
  if (!isDatabaseReady()) return;

  try {
    // Check if accounts table exists
    const [tables] = await pool.query("SHOW TABLES LIKE 'accounts'");
    const tablesList = tables as any[];

    if (tablesList.length === 0) {
      console.log('[Database] Initializing schema from schema.sql...');
      const schemaPath = path.resolve(process.cwd(), 'schema.sql');
      if (fs.existsSync(schemaPath)) {
        const schemaSql = fs.readFileSync(schemaPath, 'utf-8');
        // Split by semicolon (ignoring delimiter blocks if any)
        const statements = schemaSql
          .replace(/DELIMITER \/\/[\s\S]*?DELIMITER ;/g, '') // strip triggers/procedures for safe split
          .split(';')
          .map((s) => s.trim())
          .filter((s) => s.length > 0 && !s.startsWith('--') && !s.toLowerCase().startsWith('use '));

        for (const sql of statements) {
          try {
            await pool.query(sql);
          } catch (err: any) {
            // Ignore minor duplicate or harmless errors
            if (!err.message?.includes('already exists')) {
              // console.warn('[Database] Schema step warning:', err.message);
            }
          }
        }
        console.log('[Database] Schema created successfully!');
      }
    }

    // Ensure roles exist
    await pool.query(`
      CREATE TABLE IF NOT EXISTS roles (
        role_id INT AUTO_INCREMENT PRIMARY KEY,
        role_name VARCHAR(50) NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);
    await pool.query("INSERT IGNORE INTO roles (role_name) VALUES ('user'), ('admin')");

    // Ensure accounts table
    await pool.query(`
      CREATE TABLE IF NOT EXISTS accounts (
        account_id INT AUTO_INCREMENT PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        password_hash VARCHAR(255),
        email_verified TINYINT DEFAULT 0,
        status ENUM('active', 'inactive', 'suspended') DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_email (email)
      )
    `);

    // Ensure accountroles table
    await pool.query(`
      CREATE TABLE IF NOT EXISTS accountroles (
        account_id INT NOT NULL,
        role_id INT NOT NULL,
        PRIMARY KEY (account_id, role_id),
        FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE,
        FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE
      )
    `);

    // Ensure users table
    await pool.query(`
      CREATE TABLE IF NOT EXISTS users (
        user_id INT AUTO_INCREMENT PRIMARY KEY,
        account_id INT NOT NULL UNIQUE,
        full_name VARCHAR(255),
        gender ENUM('male', 'female', 'other') DEFAULT 'other',
        age INT,
        height DECIMAL(5,2),
        weight DECIMAL(5,2),
        has_completed_setup TINYINT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE,
        INDEX idx_account (account_id)
      )
    `);

    // Ensure default demo admin account
    const [adminRows] = await pool.query<any[]>(
      'SELECT account_id FROM accounts WHERE email = ? LIMIT 1',
      ['admin@calai.local']
    );

    if (adminRows.length === 0) {
      const hashedPassword = await hashPassword('Admin123!');
      const [accResult] = await pool.query<any>(
        'INSERT INTO accounts (email, password_hash, email_verified, status) VALUES (?, ?, 1, ?)',
        ['admin@calai.local', hashedPassword, 'active']
      );
      const adminId = accResult.insertId;

      const [roleRows] = await pool.query<any[]>(
        "SELECT role_id FROM roles WHERE role_name = 'admin' LIMIT 1"
      );
      if (roleRows.length > 0) {
        await pool.query('INSERT IGNORE INTO accountroles (account_id, role_id) VALUES (?, ?)', [
          adminId,
          roleRows[0].role_id,
        ]);
      }

      await pool.query(
        'INSERT INTO users (account_id, full_name, gender, age, height, weight, has_completed_setup) VALUES (?, ?, ?, ?, ?, ?, 1)',
        [adminId, 'System Admin', 'male', 30, 175, 70]
      );
      console.log('✅ [Database] Default admin account created: admin@calai.local / Admin123!');
    }
  } catch (error) {
    console.error('[Database] Schema initialization warning:', error);
  }
};
