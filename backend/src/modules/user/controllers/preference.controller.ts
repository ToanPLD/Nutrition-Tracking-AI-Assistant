import { Request, Response, NextFunction } from 'express';
import { preferenceService } from '../services/preference.service';
import { sendSuccess } from '../../../shared/responses/api-response';

export const listFoodPreferences = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await preferenceService.listPreferences(req.user!.accountId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const upsertFoodPreference = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await preferenceService.upsertPreference(req.user!.accountId, req.body);
    return sendSuccess(res, result, 'Preference saved successfully');
  } catch (error) {
    next(error);
  }
};

export const deleteFoodPreference = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const preferenceId = Number(req.params.preferenceId);
    const result = await preferenceService.deletePreference(req.user!.accountId, preferenceId);
    return sendSuccess(res, result, 'Preference removed');
  } catch (error) {
    next(error);
  }
};
