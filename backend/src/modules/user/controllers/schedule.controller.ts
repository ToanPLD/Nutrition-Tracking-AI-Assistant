import { Request, Response, NextFunction } from 'express';
import { scheduleService } from '../services/schedule.service';
import { sendSuccess } from '../../../shared/responses/api-response';

export const listSchedules = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await scheduleService.listSchedules(req.user!.accountId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const createSchedule = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await scheduleService.createSchedule(req.user!.accountId, req.body);
    return sendSuccess(res, result, 'Schedule created successfully', 201);
  } catch (error) {
    next(error);
  }
};

export const updateSchedule = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const scheduleId = Number(req.params.scheduleId);
    const result = await scheduleService.updateSchedule(req.user!.accountId, scheduleId, req.body);
    return sendSuccess(res, result, 'Schedule updated successfully');
  } catch (error) {
    next(error);
  }
};

export const deleteSchedule = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const scheduleId = Number(req.params.scheduleId);
    const result = await scheduleService.deleteSchedule(req.user!.accountId, scheduleId);
    return sendSuccess(res, result, 'Schedule deleted successfully');
  } catch (error) {
    next(error);
  }
};

export const publishSchedule = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const scheduleId = Number(req.params.scheduleId);
    const result = await scheduleService.publishSchedule(req.user!.accountId, scheduleId);
    return sendSuccess(res, result, 'Schedule publication updated');
  } catch (error) {
    next(error);
  }
};

export const listDiscoverMeals = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await scheduleService.listDiscoverMeals();
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};
