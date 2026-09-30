import { dbQuery, dbQueryOne, dbExecute, dbTransaction } from '../../../database/query';
import { NotFoundError } from '../../../shared/errors/app-error';
import { profileService } from './profile.service';
import { CreateMealDto, UpdateMealDto } from '../user.types';

export class MealService {
  /**
   * Get meals for a specific date (default: today)
   */
  async getMealsByDate(accountId: number, dateStr?: string) {
    const userId = await profileService.getUserId(accountId);
    const date = dateStr || new Date().toISOString().split('T')[0];

    const sql = `
      SELECT
        m.meal_id,
        m.meal_type,
        m.meal_date,
        m.created_at,
        mi.mealitem_id,
        mi.food_id,
        COALESCE(f.food_name, 'Food Item') AS food_name,
        mi.quantity,
        mi.calories,
        mi.protein,
        mi.carbs,
        mi.fat AS fats
      FROM meals m
      JOIN mealitems mi ON mi.meal_id = m.meal_id
      LEFT JOIN foods f ON f.food_id = mi.food_id
      WHERE m.user_id = ? AND m.meal_date = ?
      ORDER BY m.created_at ASC
    `;
    const items = await dbQuery<any[]>(sql, [userId, date]);

    // Group items by meal
    const mealMap = new Map<number, any>();
    for (const item of items) {
      if (!mealMap.has(item.meal_id)) {
        mealMap.set(item.meal_id, {
          mealId: item.meal_id,
          mealType: item.meal_type,
          mealDate: item.meal_date,
          createdAt: item.created_at,
          totalCalories: 0,
          totalProtein: 0,
          totalCarbs: 0,
          totalFats: 0,
          items: [],
        });
      }
      const meal = mealMap.get(item.meal_id);
      meal.totalCalories += Number(item.calories || 0);
      meal.totalProtein += Number(item.protein || 0);
      meal.totalCarbs += Number(item.carbs || 0);
      meal.totalFats += Number(item.fats || 0);
      meal.items.push({
        mealItemId: item.mealitem_id,
        foodId: item.food_id,
        foodName: item.food_name,
        quantity: item.quantity,
        calories: item.calories,
        protein: item.protein,
        carbs: item.carbs,
        fats: item.fats,
      });
    }

    return Array.from(mealMap.values());
  }

  /**
   * Get meal history with summary totals per day
   */
  async getMealHistory(accountId: number, limit = 14) {
    const userId = await profileService.getUserId(accountId);
    const sql = `
      SELECT
        m.meal_date,
        COUNT(DISTINCT m.meal_id) AS total_meals,
        COALESCE(SUM(mi.calories), 0) AS total_calories,
        COALESCE(SUM(mi.protein), 0) AS total_protein,
        COALESCE(SUM(mi.carbs), 0) AS total_carbs,
        COALESCE(SUM(mi.fat), 0) AS total_fats
      FROM meals m
      JOIN mealitems mi ON mi.meal_id = m.meal_id
      WHERE m.user_id = ?
      GROUP BY m.meal_date
      ORDER BY m.meal_date DESC
      LIMIT ?
    `;
    const history = await dbQuery<any[]>(sql, [userId, Number(limit)]);
    return history;
  }

  /**
   * Log a new meal
   */
  async createMeal(accountId: number, data: CreateMealDto) {
    const userId = await profileService.getUserId(accountId);
    const mealDate = data.mealDate || new Date().toISOString().split('T')[0];
    const mealType = data.mealType || 'lunch';

    return dbTransaction(async (conn) => {
      // 1. Resolve or create food item
      let foodId = data.foodId;
      if (!foodId && data.foodName) {
        const [existingFoods] = await conn.query<any[]>(
          'SELECT food_id FROM foods WHERE LOWER(food_name) = LOWER(?) LIMIT 1',
          [data.foodName]
        );
        if (existingFoods.length > 0) {
          foodId = existingFoods[0].food_id;
        } else {
          const [foodResult] = await conn.execute<any>(
            `INSERT INTO foods (food_name, calories, protein, carbs, fat) VALUES (?, ?, ?, ?, ?)`,
            [data.foodName, data.calories || 0, data.protein || 0, data.carbs || 0, data.fats || 0]
          );
          foodId = foodResult.insertId;
        }
      }

      // If still no foodId, create a placeholder
      if (!foodId) {
        const [foodResult] = await conn.execute<any>(
          `INSERT INTO foods (food_name, calories, protein, carbs, fat) VALUES (?, ?, ?, ?, ?)`,
          ['Custom Food', data.calories || 0, data.protein || 0, data.carbs || 0, data.fats || 0]
        );
        foodId = foodResult.insertId;
      }

      // 2. Create meal record
      const [mealResult] = await conn.execute<any>(
        'INSERT INTO meals (user_id, meal_type, meal_date) VALUES (?, ?, ?)',
        [userId, mealType, mealDate]
      );
      const mealId = mealResult.insertId;

      // 3. Create meal item
      await conn.execute<any>(
        `INSERT INTO mealitems (meal_id, food_id, quantity, calories, protein, carbs, fat)
         VALUES (?, ?, ?, ?, ?, ?, ?)`,
        [
          mealId,
          foodId,
          data.quantity || 1.0,
          data.calories || 0,
          data.protein || 0,
          data.carbs || 0,
          data.fats || 0,
        ]
      );

      // 4. Update daily nutrition logs
      await this.updateDailyNutrition(conn, userId, mealDate);

      return {
        mealId,
        userId,
        mealType,
        mealDate,
        foodName: data.foodName,
        calories: data.calories || 0,
        protein: data.protein || 0,
        carbs: data.carbs || 0,
        fats: data.fats || 0,
      };
    });
  }

  /**
   * Update meal item
   */
  async updateMeal(accountId: number, mealId: number, data: UpdateMealDto) {
    const userId = await profileService.getUserId(accountId);

    const meal = await dbQueryOne<any>(
      'SELECT meal_id, meal_date, meal_type FROM meals WHERE meal_id = ? AND user_id = ? LIMIT 1',
      [mealId, userId]
    );

    if (!meal) {
      throw new NotFoundError('Meal not found or unauthorized');
    }

    return dbTransaction(async (conn) => {
      if (data.mealType) {
        await conn.execute('UPDATE meals SET meal_type = ? WHERE meal_id = ?', [data.mealType, mealId]);
      }

      const itemUpdates: string[] = [];
      const itemValues: any[] = [];

      if (data.calories !== undefined) {
        itemUpdates.push('calories = ?');
        itemValues.push(data.calories);
      }
      if (data.protein !== undefined) {
        itemUpdates.push('protein = ?');
        itemValues.push(data.protein);
      }
      if (data.carbs !== undefined) {
        itemUpdates.push('carbs = ?');
        itemValues.push(data.carbs);
      }
      if (data.fats !== undefined) {
        itemUpdates.push('fat = ?');
        itemValues.push(data.fats);
      }
      if (data.quantity !== undefined) {
        itemUpdates.push('quantity = ?');
        itemValues.push(data.quantity);
      }

      if (itemUpdates.length > 0) {
        itemValues.push(mealId);
        await conn.execute(`UPDATE mealitems SET ${itemUpdates.join(', ')} WHERE meal_id = ?`, itemValues);
      }

      await this.updateDailyNutrition(conn, userId, meal.meal_date);

      return { mealId, updated: true };
    });
  }

  /**
   * Delete meal
   */
  async deleteMeal(accountId: number, mealId: number) {
    const userId = await profileService.getUserId(accountId);
    const meal = await dbQueryOne<any>(
      'SELECT meal_id, meal_date FROM meals WHERE meal_id = ? AND user_id = ? LIMIT 1',
      [mealId, userId]
    );

    if (!meal) {
      throw new NotFoundError('Meal not found');
    }

    await dbTransaction(async (conn) => {
      await conn.execute('DELETE FROM meals WHERE meal_id = ?', [mealId]);
      await this.updateDailyNutrition(conn, userId, meal.meal_date);
    });

    return { success: true, message: 'Meal deleted successfully' };
  }

  /**
   * Search foods database
   */
  async searchFoods(query = '', limit = 50, category = '') {
    const params: any[] = [];
    let sql = `
      SELECT
        f.food_id,
        f.food_name,
        f.category_id,
        c.category_name,
        f.calories,
        f.protein,
        f.carbs,
        f.fat AS fats,
        f.fiber,
        f.sugar,
        f.sodium,
        f.serving_size,
        f.image_path
      FROM foods f
      LEFT JOIN foodcategories c ON c.category_id = f.category_id
      WHERE 1=1
    `;

    if (query.trim()) {
      sql += ' AND f.food_name LIKE ?';
      params.push(`%${query.trim()}%`);
    }

    if (category.trim()) {
      sql += ' AND c.category_name = ?';
      params.push(category.trim());
    }

    sql += ' ORDER BY f.food_name ASC LIMIT ?';
    params.push(Number(limit));

    const foods = await dbQuery<any[]>(sql, params);
    return foods;
  }

  private async updateDailyNutrition(conn: any, userId: number, date: string) {
    const sql = `
      INSERT INTO dailynutritionlogs (user_id, date, total_calories, total_protein, total_carbs, total_fat)
      SELECT
        m.user_id,
        m.meal_date,
        COALESCE(SUM(mi.calories), 0),
        COALESCE(SUM(mi.protein), 0),
        COALESCE(SUM(mi.carbs), 0),
        COALESCE(SUM(mi.fat), 0)
      FROM meals m
      JOIN mealitems mi ON mi.meal_id = m.meal_id
      WHERE m.user_id = ? AND m.meal_date = ?
      GROUP BY m.user_id, m.meal_date
      ON DUPLICATE KEY UPDATE
        total_calories = VALUES(total_calories),
        total_protein = VALUES(total_protein),
        total_carbs = VALUES(total_carbs),
        total_fat = VALUES(total_fat)
    `;
    await conn.execute(sql, [userId, date]);
  }
}

export const mealService = new MealService();
