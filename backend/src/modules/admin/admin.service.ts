import { dbQuery, dbQueryOne, dbExecute, dbTransaction } from '../../database/query';
import { hashPassword } from '../../shared/utils/hash';
import { BadRequestError, NotFoundError } from '../../shared/errors/app-error';
import { CreateFoodDto, CreateUserDto, UpdateFoodDto, UpdateUserDto } from './admin.types';

export class AdminService {
  async logAction(adminAccountId: number, action: string, targetType: string, targetId?: number, detail?: string) {
    try {
      await dbExecute(
        'INSERT INTO adminauditlogs (admin_account_id, action, target_type, target_id, detail) VALUES (?, ?, ?, ?, ?)',
        [adminAccountId, action, targetType, targetId || null, detail || null]
      );
    } catch {
      // Non-blocking audit log
    }
  }

  async getAdminProfile(accountId: number) {
    const sql = `
      SELECT a.account_id, a.email, a.status, r.role_name, u.full_name AS name
      FROM accounts a
      LEFT JOIN accountroles ar ON ar.account_id = a.account_id
      LEFT JOIN roles r ON r.role_id = ar.role_id
      LEFT JOIN users u ON u.account_id = a.account_id
      WHERE a.account_id = ?
      LIMIT 1
    `;
    const admin = await dbQueryOne<any>(sql, [accountId]);
    if (!admin) throw new NotFoundError('Admin profile not found');
    return admin;
  }

  async getAdminStats() {
    const totalUsers = await dbQueryOne<any>("SELECT COUNT(*) AS total FROM accounts WHERE status != 'suspended'");
    const totalMeals = await dbQueryOne<any>('SELECT COUNT(*) AS total FROM meals');
    const totalFoods = await dbQueryOne<any>('SELECT COUNT(*) AS total FROM foods');
    const activeToday = await dbQueryOne<any>('SELECT COUNT(DISTINCT user_id) AS total FROM meals WHERE meal_date = CURDATE()');

    return {
      totalUsers: totalUsers?.total || 0,
      totalMeals: totalMeals?.total || 0,
      totalFoods: totalFoods?.total || 0,
      activeToday: activeToday?.total || 0,
    };
  }

  async getAdminAnalytics() {
    // 7-day meal logging trend
    const mealTrends = await dbQuery<any[]>(`
      SELECT meal_date, COUNT(*) AS count
      FROM meals
      WHERE meal_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
      GROUP BY meal_date
      ORDER BY meal_date ASC
    `);

    // Top logged foods
    const topFoods = await dbQuery<any[]>(`
      SELECT f.food_name, COUNT(mi.mealitem_id) AS log_count
      FROM mealitems mi
      JOIN foods f ON f.food_id = mi.food_id
      GROUP BY f.food_id, f.food_name
      ORDER BY log_count DESC
      LIMIT 5
    `);

    return { mealTrends, topFoods };
  }

  async getSecurityOverview() {
    const rolesDistribution = await dbQuery<any[]>(`
      SELECT r.role_name, COUNT(ar.account_id) AS count
      FROM roles r
      LEFT JOIN accountroles ar ON ar.role_id = r.role_id
      GROUP BY r.role_id, r.role_name
    `);

    const recentAudits = await dbQuery<any[]>(`
      SELECT l.log_id, l.action, l.target_type, l.target_id, l.detail, l.created_at, a.email AS admin_email
      FROM adminauditlogs l
      LEFT JOIN accounts a ON a.account_id = l.admin_account_id
      ORDER BY l.created_at DESC
      LIMIT 10
    `);

    return { rolesDistribution, recentAudits };
  }

  async getRoleAccounts() {
    const sql = `
      SELECT a.account_id, a.email, a.status, r.role_name, u.full_name AS name, a.created_at
      FROM accounts a
      LEFT JOIN accountroles ar ON ar.account_id = a.account_id
      LEFT JOIN roles r ON r.role_id = ar.role_id
      LEFT JOIN users u ON u.account_id = a.account_id
      ORDER BY a.account_id ASC
    `;
    return dbQuery<any[]>(sql);
  }

  async updateAccountRole(adminId: number, targetAccountId: number, newRole: string) {
    const [roles] = await dbQuery<any[]>('SELECT role_id FROM roles WHERE LOWER(role_name) = LOWER(?) LIMIT 1', [
      newRole,
    ]);
    if (roles.length === 0) throw new BadRequestError('Invalid role specified');

    const roleId = roles[0].role_id;
    await dbExecute('DELETE FROM accountroles WHERE account_id = ?', [targetAccountId]);
    await dbExecute('INSERT INTO accountroles (account_id, role_id) VALUES (?, ?)', [targetAccountId, roleId]);

    await this.logAction(adminId, 'UPDATE_ROLE', 'account', targetAccountId, `Role changed to ${newRole}`);
    return { accountId: targetAccountId, role: newRole };
  }

  async getAuditLogs(limit = 50) {
    const sql = `
      SELECT l.log_id, l.action, l.target_type, l.target_id, l.detail, l.created_at, a.email AS admin_email
      FROM adminauditlogs l
      LEFT JOIN accounts a ON a.account_id = l.admin_account_id
      ORDER BY l.created_at DESC
      LIMIT ?
    `;
    return dbQuery<any[]>(sql, [Number(limit)]);
  }

  // --- User Management ---
  async getAllUsers(page = 1, limit = 20, search = '') {
    const offset = (Number(page) - 1) * Number(limit);
    const params: any[] = [];
    let countSql = 'SELECT COUNT(*) AS total FROM users u JOIN accounts a ON a.account_id = u.account_id WHERE 1=1';
    let dataSql = `
      SELECT u.user_id, u.account_id, u.full_name AS name, a.email, a.status, r.role_name, u.age, u.gender, u.created_at
      FROM users u
      JOIN accounts a ON a.account_id = u.account_id
      LEFT JOIN accountroles ar ON ar.account_id = a.account_id
      LEFT JOIN roles r ON r.role_id = ar.role_id
      WHERE 1=1
    `;

    if (search.trim()) {
      const term = `%${search.trim()}%`;
      countSql += ' AND (u.full_name LIKE ? OR a.email LIKE ?)';
      dataSql += ' AND (u.full_name LIKE ? OR a.email LIKE ?)';
      params.push(term, term);
    }

    dataSql += ' ORDER BY u.user_id DESC LIMIT ? OFFSET ?';
    const totalRow = await dbQueryOne<any>(countSql, params);
    const users = await dbQuery<any[]>(dataSql, [...params, Number(limit), offset]);

    return {
      users,
      pagination: {
        total: totalRow?.total || 0,
        page: Number(page),
        limit: Number(limit),
      },
    };
  }

  async getUserById(userId: number) {
    const sql = `
      SELECT u.*, a.email, a.status, r.role_name
      FROM users u
      JOIN accounts a ON a.account_id = u.account_id
      LEFT JOIN accountroles ar ON ar.account_id = a.account_id
      LEFT JOIN roles r ON r.role_id = ar.role_id
      WHERE u.user_id = ?
      LIMIT 1
    `;
    const user = await dbQueryOne<any>(sql, [userId]);
    if (!user) throw new NotFoundError('User not found');
    return user;
  }

  async getUserStatistics(userId: number) {
    const user = await this.getUserById(userId);
    const totalMeals = await dbQueryOne<any>('SELECT COUNT(*) AS total FROM meals WHERE user_id = ?', [userId]);
    const avgCalories = await dbQueryOne<any>(
      'SELECT AVG(total_calories) AS avg_cal FROM dailynutritionlogs WHERE user_id = ?',
      [userId]
    );

    return {
      userId,
      totalMeals: totalMeals?.total || 0,
      averageCalories: Math.round(avgCalories?.avg_cal || 0),
    };
  }

  async createUser(adminId: number, data: CreateUserDto) {
    const existing = await dbQueryOne<any>('SELECT account_id FROM accounts WHERE email = ? LIMIT 1', [data.email]);
    if (existing) throw new BadRequestError('Email already exists');

    const rawPassword = data.password || 'User123!';
    const hashedPassword = await hashPassword(rawPassword);

    return dbTransaction(async (conn) => {
      const [accRes] = await conn.execute<any>(
        'INSERT INTO accounts (email, password_hash, email_verified, status) VALUES (?, ?, 1, ?)',
        [data.email.toLowerCase(), hashedPassword, 'active']
      );
      const accountId = accRes.insertId;

      const targetRole = data.role || 'user';
      const [roleRows] = await conn.query<any[]>('SELECT role_id FROM roles WHERE LOWER(role_name) = ? LIMIT 1', [
        targetRole.toLowerCase(),
      ]);
      if (roleRows.length > 0) {
        await conn.execute('INSERT INTO accountroles (account_id, role_id) VALUES (?, ?)', [
          accountId,
          roleRows[0].role_id,
        ]);
      }

      const [userRes] = await conn.execute<any>(
        'INSERT INTO users (account_id, full_name, gender, age, height, weight, has_completed_setup) VALUES (?, ?, ?, ?, ?, ?, 1)',
        [accountId, data.name, data.gender || 'other', data.age || 25, data.height || 170, data.weight || 65]
      );

      await this.logAction(adminId, 'CREATE_USER', 'user', userRes.insertId, `Created user ${data.email}`);
      return { userId: userRes.insertId, accountId, email: data.email, name: data.name };
    });
  }

  async updateUser(adminId: number, userId: number, data: UpdateUserDto) {
    const user = await this.getUserById(userId);
    const fields: string[] = [];
    const values: any[] = [];

    if (data.name !== undefined) {
      fields.push('full_name = ?');
      values.push(data.name);
    }
    if (data.gender !== undefined) {
      fields.push('gender = ?');
      values.push(data.gender);
    }
    if (data.age !== undefined) {
      fields.push('age = ?');
      values.push(data.age);
    }
    if (data.height !== undefined) {
      fields.push('height = ?');
      values.push(data.height);
    }
    if (data.weight !== undefined) {
      fields.push('weight = ?');
      values.push(data.weight);
    }

    if (fields.length > 0) {
      values.push(userId);
      await dbExecute(`UPDATE users SET ${fields.join(', ')} WHERE user_id = ?`, values);
    }

    if (data.status) {
      await dbExecute('UPDATE accounts SET status = ? WHERE account_id = ?', [data.status, user.account_id]);
    }

    await this.logAction(adminId, 'UPDATE_USER', 'user', userId, 'Updated profile/status');
    return this.getUserById(userId);
  }

  async updateUserStatus(adminId: number, userId: number, status: string) {
    const user = await this.getUserById(userId);
    await dbExecute('UPDATE accounts SET status = ? WHERE account_id = ?', [status, user.account_id]);
    await this.logAction(adminId, 'UPDATE_STATUS', 'user', userId, `Status changed to ${status}`);
    return { userId, status };
  }

  async deleteUser(adminId: number, userId: number) {
    const user = await this.getUserById(userId);
    await dbExecute('DELETE FROM accounts WHERE account_id = ?', [user.account_id]);
    await this.logAction(adminId, 'DELETE_USER', 'user', userId, `Deleted user ${user.email}`);
    return { success: true, message: 'User deleted' };
  }

  async bulkUpdateUserStatus(adminId: number, userIds: number[], status: string) {
    if (!userIds || userIds.length === 0) return { updatedCount: 0 };
    for (const uid of userIds) {
      await this.updateUserStatus(adminId, uid, status);
    }
    return { updatedCount: userIds.length, status };
  }

  // --- Foods Management ---
  async getAllFoods(page = 1, limit = 50, search = '') {
    const offset = (Number(page) - 1) * Number(limit);
    const params: any[] = [];
    let countSql = 'SELECT COUNT(*) AS total FROM foods WHERE 1=1';
    let dataSql = `
      SELECT f.*, c.category_name
      FROM foods f
      LEFT JOIN foodcategories c ON c.category_id = f.category_id
      WHERE 1=1
    `;

    if (search.trim()) {
      countSql += ' AND f.food_name LIKE ?';
      dataSql += ' AND f.food_name LIKE ?';
      params.push(`%${search.trim()}%`);
    }

    dataSql += ' ORDER BY f.food_id DESC LIMIT ? OFFSET ?';
    const totalRow = await dbQueryOne<any>(countSql, params);
    const foods = await dbQuery<any[]>(dataSql, [...params, Number(limit), offset]);

    return {
      foods,
      pagination: {
        total: totalRow?.total || 0,
        page: Number(page),
        limit: Number(limit),
      },
    };
  }

  async getFoodCategories() {
    return dbQuery<any[]>('SELECT * FROM foodcategories ORDER BY category_name ASC');
  }

  async getFoodById(foodId: number) {
    const sql = `
      SELECT f.*, c.category_name
      FROM foods f
      LEFT JOIN foodcategories c ON c.category_id = f.category_id
      WHERE f.food_id = ?
      LIMIT 1
    `;
    const food = await dbQueryOne<any>(sql, [foodId]);
    if (!food) throw new NotFoundError('Food item not found');
    return food;
  }

  async createFood(adminId: number, data: CreateFoodDto) {
    const result = await dbExecute(
      `INSERT INTO foods (food_name, category_id, calories, protein, carbs, fat, fiber, sugar, sodium, serving_size)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        data.foodName,
        data.categoryId || null,
        data.calories,
        data.protein || 0,
        data.carbs || 0,
        data.fat || 0,
        data.fiber || 0,
        data.sugar || 0,
        data.sodium || 0,
        data.servingSize || '100g',
      ]
    );

    await this.logAction(adminId, 'CREATE_FOOD', 'food', result.insertId, `Created food ${data.foodName}`);
    return this.getFoodById(result.insertId);
  }

  async updateFood(adminId: number, foodId: number, data: UpdateFoodDto) {
    const food = await this.getFoodById(foodId);
    const fields: string[] = [];
    const values: any[] = [];

    if (data.foodName !== undefined) {
      fields.push('food_name = ?');
      values.push(data.foodName);
    }
    if (data.categoryId !== undefined) {
      fields.push('category_id = ?');
      values.push(data.categoryId);
    }
    if (data.calories !== undefined) {
      fields.push('calories = ?');
      values.push(data.calories);
    }
    if (data.protein !== undefined) {
      fields.push('protein = ?');
      values.push(data.protein);
    }
    if (data.carbs !== undefined) {
      fields.push('carbs = ?');
      values.push(data.carbs);
    }
    if (data.fat !== undefined) {
      fields.push('fat = ?');
      values.push(data.fat);
    }
    if (data.servingSize !== undefined) {
      fields.push('serving_size = ?');
      values.push(data.servingSize);
    }

    if (fields.length > 0) {
      values.push(foodId);
      await dbExecute(`UPDATE foods SET ${fields.join(', ')} WHERE food_id = ?`, values);
    }

    await this.logAction(adminId, 'UPDATE_FOOD', 'food', foodId, `Updated food ${data.foodName || food.food_name}`);
    return this.getFoodById(foodId);
  }

  async deleteFood(adminId: number, foodId: number) {
    await dbExecute('DELETE FROM foods WHERE food_id = ?', [foodId]);
    await this.logAction(adminId, 'DELETE_FOOD', 'food', foodId, 'Deleted food');
    return { success: true, message: 'Food item deleted' };
  }
}

export const adminService = new AdminService();
