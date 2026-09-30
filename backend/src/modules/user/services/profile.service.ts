import { dbQueryOne, dbExecute, dbQuery } from '../../../database/query';
import { NotFoundError } from '../../../shared/errors/app-error';
import { UserGoalsDto, UserProfileDto } from '../user.types';

export class ProfileService {
  /**
   * Helper to get user_id from account_id, auto-creating user profile record if missing
   */
  async getUserId(accountId: number): Promise<number> {
    const row = await dbQueryOne<any>('SELECT user_id FROM users WHERE account_id = ? LIMIT 1', [
      accountId,
    ]);

    if (row) {
      return row.user_id;
    }

    // Auto-create user profile record if it doesn't exist
    const acc = await dbQueryOne<any>('SELECT email FROM accounts WHERE account_id = ? LIMIT 1', [
      accountId,
    ]);
    const defaultName = acc ? acc.email.split('@')[0] : 'User';

    const result = await dbExecute(
      'INSERT INTO users (account_id, full_name, has_completed_setup) VALUES (?, ?, 0)',
      [accountId, defaultName]
    );
    return result.insertId;
  }

  async getProfile(accountId: number) {
    const userId = await this.getUserId(accountId);
    const sql = `
      SELECT
        u.user_id,
        u.account_id,
        u.full_name AS name,
        u.gender,
        u.age,
        u.height,
        u.weight,
        u.has_completed_setup,
        a.email,
        a.status
      FROM users u
      JOIN accounts a ON a.account_id = u.account_id
      WHERE u.user_id = ?
      LIMIT 1
    `;
    const profile = await dbQueryOne<any>(sql, [userId]);
    if (!profile) {
      throw new NotFoundError('User profile not found');
    }
    return profile;
  }

  async updateProfile(accountId: number, data: UserProfileDto) {
    const userId = await this.getUserId(accountId);
    const fields: string[] = [];
    const values: any[] = [];

    if (data.name !== undefined) {
      fields.push('full_name = ?');
      values.push(data.name.trim());
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
      fields.push('has_completed_setup = 1');
      values.push(userId);
      await dbExecute(`UPDATE users SET ${fields.join(', ')} WHERE user_id = ?`, values);

      // Record weight history if weight was updated
      if (data.weight !== undefined) {
        await dbExecute('INSERT INTO weight_history (user_id, weight) VALUES (?, ?)', [
          userId,
          data.weight,
        ]);
      }
    }

    return this.getProfile(accountId);
  }

  async getGoals(accountId: number) {
    const userId = await this.getUserId(accountId);
    const sql = `
      SELECT
        goal_id,
        user_id,
        target_calories AS dailyCalories,
        target_protein AS protein,
        target_carbs AS carbs,
        target_fat AS fats,
        target_weight AS targetWeight,
        goal_type AS goal,
        activity_level AS activityLevel
      FROM usergoals
      WHERE user_id = ?
      ORDER BY goal_id DESC
      LIMIT 1
    `;
    const goal = await dbQueryOne<any>(sql, [userId]);
    return (
      goal || {
        dailyCalories: 2000,
        targetWeight: 70,
        goal: 'maintenance',
        activityLevel: 'moderate',
        protein: 150,
        carbs: 200,
        fats: 65,
      }
    );
  }

  async updateGoals(accountId: number, data: UserGoalsDto) {
    const userId = await this.getUserId(accountId);
    const existing = await dbQueryOne<any>('SELECT goal_id FROM usergoals WHERE user_id = ? LIMIT 1', [
      userId,
    ]);

    const calories = data.dailyCalories ?? 2000;
    const protein = data.protein ?? Math.round((calories * 0.3) / 4);
    const carbs = data.carbs ?? Math.round((calories * 0.4) / 4);
    const fats = data.fats ?? Math.round((calories * 0.3) / 9);
    const targetWeight = data.targetWeight ?? 70;
    const goalType = data.goal ?? 'maintenance';
    const activity = data.activityLevel ?? 'moderate';

    if (existing) {
      await dbExecute(
        `UPDATE usergoals
         SET target_calories = ?, target_protein = ?, target_carbs = ?, target_fat = ?, target_weight = ?, goal_type = ?, activity_level = ?
         WHERE goal_id = ?`,
        [calories, protein, carbs, fats, targetWeight, goalType, activity, existing.goal_id]
      );
    } else {
      await dbExecute(
        `INSERT INTO usergoals
         (user_id, target_calories, target_protein, target_carbs, target_fat, target_weight, goal_type, activity_level)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        [userId, calories, protein, carbs, fats, targetWeight, goalType, activity]
      );
    }

    return this.getGoals(accountId);
  }

  async getDashboard(accountId: number) {
    const userId = await this.getUserId(accountId);
    const today = new Date().toISOString().split('T')[0];

    // Today's nutrition
    const nutritionSql = `
      SELECT
        COALESCE(SUM(mi.calories), 0) AS calories,
        COALESCE(SUM(mi.protein), 0) AS protein,
        COALESCE(SUM(mi.carbs), 0) AS carbs,
        COALESCE(SUM(mi.fat), 0) AS fats
      FROM meals m
      JOIN mealitems mi ON mi.meal_id = m.meal_id
      WHERE m.user_id = ? AND m.meal_date = ?
    `;
    const todayNutrition = await dbQueryOne<any>(nutritionSql, [userId, today]);

    const goals = await this.getGoals(accountId);
    const profile = await this.getProfile(accountId);

    // Recent meals
    const mealsSql = `
      SELECT
        m.meal_id,
        m.meal_type,
        m.meal_date,
        mi.mealitem_id,
        COALESCE(f.food_name, 'Food Item') AS food_name,
        mi.calories,
        mi.protein,
        mi.carbs,
        mi.fat,
        mi.quantity
      FROM meals m
      JOIN mealitems mi ON mi.meal_id = m.meal_id
      LEFT JOIN foods f ON f.food_id = mi.food_id
      WHERE m.user_id = ? AND m.meal_date = ?
      ORDER BY m.created_at DESC
    `;
    const todayMeals = await dbQuery<any[]>(mealsSql, [userId, today]);

    return {
      date: today,
      profile,
      goals,
      todayNutrition: todayNutrition || { calories: 0, protein: 0, carbs: 0, fats: 0 },
      todayMeals,
    };
  }
}

export const profileService = new ProfileService();
