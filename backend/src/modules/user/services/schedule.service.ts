import { dbQuery, dbQueryOne, dbExecute, dbTransaction } from '../../../database/query';
import { NotFoundError } from '../../../shared/errors/app-error';
import { profileService } from './profile.service';
import { CreateScheduleDto } from '../user.types';

export class ScheduleService {
  /**
   * List schedules of user
   */
  async listSchedules(accountId: number) {
    const userId = await profileService.getUserId(accountId);
    const sql = `
      SELECT
        s.schedule_id,
        s.name,
        s.description,
        s.start_date,
        s.end_date,
        s.color,
        s.target_calories,
        s.source,
        s.is_published,
        s.published_at,
        s.achieved,
        s.plan_payload,
        s.created_at,
        s.updated_at
      FROM mealschedules s
      WHERE s.user_id = ?
      ORDER BY s.created_at DESC
    `;
    const schedules = await dbQuery<any[]>(sql, [userId]);

    for (const schedule of schedules) {
      const itemsSql = `
        SELECT item_id, day_offset, meal_type, name, serving, calories, protein, carbs, fat, notes, sort_order
        FROM mealscheduleitems
        WHERE schedule_id = ?
        ORDER BY day_offset ASC, sort_order ASC
      `;
      schedule.items = await dbQuery<any[]>(itemsSql, [schedule.schedule_id]);
    }

    return schedules;
  }

  /**
   * Create a schedule
   */
  async createSchedule(accountId: number, data: CreateScheduleDto) {
    const userId = await profileService.getUserId(accountId);

    return dbTransaction(async (conn) => {
      const [result] = await conn.execute<any>(
        `INSERT INTO mealschedules (user_id, name, description, start_date, end_date, color, target_calories, source, plan_payload)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          userId,
          data.name,
          data.description || null,
          data.startDate,
          data.endDate,
          data.color || '#FB923C',
          data.targetCalories || null,
          data.source || 'manual',
          data.planPayload ? JSON.stringify(data.planPayload) : null,
        ]
      );
      const scheduleId = result.insertId;

      if (data.items && data.items.length > 0) {
        for (const item of data.items) {
          await conn.execute<any>(
            `INSERT INTO mealscheduleitems (schedule_id, day_offset, meal_type, name, serving, calories, protein, carbs, fat, notes, sort_order)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            [
              scheduleId,
              item.dayOffset || 0,
              item.mealType,
              item.name,
              item.serving || null,
              item.calories || 0,
              item.protein || 0,
              item.carbs || 0,
              item.fat || 0,
              item.notes || null,
              item.sortOrder || 0,
            ]
          );
        }
      }

      return { scheduleId, ...data };
    });
  }

  /**
   * Update schedule
   */
  async updateSchedule(accountId: number, scheduleId: number, data: Partial<CreateScheduleDto> & { achieved?: boolean }) {
    const userId = await profileService.getUserId(accountId);
    const existing = await dbQueryOne<any>(
      'SELECT schedule_id FROM mealschedules WHERE schedule_id = ? AND user_id = ? LIMIT 1',
      [scheduleId, userId]
    );

    if (!existing) {
      throw new NotFoundError('Schedule not found');
    }

    const fields: string[] = [];
    const values: any[] = [];

    if (data.name !== undefined) {
      fields.push('name = ?');
      values.push(data.name);
    }
    if (data.description !== undefined) {
      fields.push('description = ?');
      values.push(data.description);
    }
    if (data.startDate !== undefined) {
      fields.push('start_date = ?');
      values.push(data.startDate);
    }
    if (data.endDate !== undefined) {
      fields.push('end_date = ?');
      values.push(data.endDate);
    }
    if (data.color !== undefined) {
      fields.push('color = ?');
      values.push(data.color);
    }
    if (data.targetCalories !== undefined) {
      fields.push('target_calories = ?');
      values.push(data.targetCalories);
    }
    if (data.achieved !== undefined) {
      fields.push('achieved = ?');
      values.push(data.achieved ? 1 : 0);
    }

    if (fields.length > 0) {
      values.push(scheduleId);
      await dbExecute(`UPDATE mealschedules SET ${fields.join(', ')} WHERE schedule_id = ?`, values);
    }

    return { scheduleId, updated: true };
  }

  /**
   * Delete schedule
   */
  async deleteSchedule(accountId: number, scheduleId: number) {
    const userId = await profileService.getUserId(accountId);
    const existing = await dbQueryOne<any>(
      'SELECT schedule_id FROM mealschedules WHERE schedule_id = ? AND user_id = ? LIMIT 1',
      [scheduleId, userId]
    );

    if (!existing) {
      throw new NotFoundError('Schedule not found');
    }

    await dbExecute('DELETE FROM mealschedules WHERE schedule_id = ?', [scheduleId]);
    return { success: true, message: 'Schedule deleted' };
  }

  /**
   * Publish schedule to Discover feed
   */
  async publishSchedule(accountId: number, scheduleId: number) {
    const userId = await profileService.getUserId(accountId);
    const existing = await dbQueryOne<any>(
      'SELECT schedule_id, is_published FROM mealschedules WHERE schedule_id = ? AND user_id = ? LIMIT 1',
      [scheduleId, userId]
    );

    if (!existing) {
      throw new NotFoundError('Schedule not found');
    }

    const nextState = existing.is_published ? 0 : 1;
    await dbExecute(
      'UPDATE mealschedules SET is_published = ?, published_at = IF(? = 1, NOW(), NULL) WHERE schedule_id = ?',
      [nextState, nextState, scheduleId]
    );

    return { scheduleId, isPublished: Boolean(nextState) };
  }

  /**
   * Discover published meals/schedules from the community
   */
  async listDiscoverMeals() {
    const sql = `
      SELECT
        s.schedule_id,
        s.name,
        s.description,
        s.color,
        s.target_calories,
        s.published_at,
        u.full_name AS author_name
      FROM mealschedules s
      JOIN users u ON u.user_id = s.user_id
      WHERE s.is_published = 1
      ORDER BY s.published_at DESC
      LIMIT 50
    `;
    const schedules = await dbQuery<any[]>(sql);

    for (const schedule of schedules) {
      const itemsSql = `
        SELECT item_id, day_offset, meal_type, name, serving, calories, protein, carbs, fat, notes
        FROM mealscheduleitems
        WHERE schedule_id = ?
        ORDER BY day_offset ASC, sort_order ASC
      `;
      schedule.items = await dbQuery<any[]>(itemsSql, [schedule.schedule_id]);
    }

    return schedules;
  }
}

export const scheduleService = new ScheduleService();
