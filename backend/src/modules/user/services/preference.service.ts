import { dbQuery, dbQueryOne, dbExecute } from '../../../database/query';
import { NotFoundError } from '../../../shared/errors/app-error';
import { profileService } from './profile.service';
import { FoodPreferenceDto } from '../user.types';

export class PreferenceService {
  async listPreferences(accountId: number) {
    const userId = await profileService.getUserId(accountId);
    const sql = `
      SELECT
        preference_id,
        user_id,
        food_name,
        preference_type,
        meal_slot,
        note,
        weight,
        source,
        created_at
      FROM userfoodpreferences
      WHERE user_id = ?
      ORDER BY created_at DESC
    `;
    return dbQuery<any[]>(sql, [userId]);
  }

  async upsertPreference(accountId: number, data: FoodPreferenceDto) {
    const userId = await profileService.getUserId(accountId);
    const sql = `
      INSERT INTO userfoodpreferences (user_id, food_name, preference_type, meal_slot, note, weight, source)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      ON DUPLICATE KEY UPDATE
        meal_slot = VALUES(meal_slot),
        note = VALUES(note),
        weight = VALUES(weight),
        source = VALUES(source),
        updated_at = NOW()
    `;
    await dbExecute(sql, [
      userId,
      data.foodName.trim(),
      data.preferenceType,
      data.mealSlot || 'any',
      data.note || null,
      data.weight ?? 1.0,
      data.source || 'user',
    ]);

    return { success: true, ...data };
  }

  async deletePreference(accountId: number, preferenceId: number) {
    const userId = await profileService.getUserId(accountId);
    const existing = await dbQueryOne<any>(
      'SELECT preference_id FROM userfoodpreferences WHERE preference_id = ? AND user_id = ? LIMIT 1',
      [preferenceId, userId]
    );

    if (!existing) {
      throw new NotFoundError('Preference not found');
    }

    await dbExecute('DELETE FROM userfoodpreferences WHERE preference_id = ?', [preferenceId]);
    return { success: true, message: 'Preference deleted' };
  }
}

export const preferenceService = new PreferenceService();
