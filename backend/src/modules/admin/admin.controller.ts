import { Request, Response, NextFunction } from 'express';
import { adminService } from './admin.service';
import { sendSuccess } from '../../shared/responses/api-response';

export const getAdminProfile = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await adminService.getAdminProfile(req.user!.accountId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getAdminStats = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await adminService.getAdminStats();
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getAdminAnalytics = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await adminService.getAdminAnalytics();
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getSecurityOverview = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await adminService.getSecurityOverview();
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getRoleAccounts = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await adminService.getRoleAccounts();
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const updateAccountRole = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const targetAccountId = Number(req.params.accountId);
    const { role } = req.body;
    const result = await adminService.updateAccountRole(req.user!.accountId, targetAccountId, role);
    return sendSuccess(res, result, 'Role updated successfully');
  } catch (error) {
    next(error);
  }
};

export const getAuditLogs = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const limit = Number(req.query.limit) || 50;
    const result = await adminService.getAuditLogs(limit);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getAllUsers = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const page = Number(req.query.page) || 1;
    const limit = Number(req.query.limit) || 20;
    const search = (req.query.search as string) || '';
    const result = await adminService.getAllUsers(page, limit, search);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getUserById = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = Number(req.params.userId);
    const result = await adminService.getUserById(userId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getUserStatistics = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = Number(req.params.userId);
    const result = await adminService.getUserStatistics(userId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const createUser = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await adminService.createUser(req.user!.accountId, req.body);
    return sendSuccess(res, result, 'User created successfully', 201);
  } catch (error) {
    next(error);
  }
};

export const updateUser = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = Number(req.params.userId);
    const result = await adminService.updateUser(req.user!.accountId, userId, req.body);
    return sendSuccess(res, result, 'User updated successfully');
  } catch (error) {
    next(error);
  }
};

export const updateUserStatus = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = Number(req.params.userId);
    const { status } = req.body;
    const result = await adminService.updateUserStatus(req.user!.accountId, userId, status);
    return sendSuccess(res, result, 'User status updated');
  } catch (error) {
    next(error);
  }
};

export const deleteUser = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = Number(req.params.userId);
    const result = await adminService.deleteUser(req.user!.accountId, userId);
    return sendSuccess(res, result, 'User deleted');
  } catch (error) {
    next(error);
  }
};

export const bulkUpdateUserStatus = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { userIds, status } = req.body;
    const result = await adminService.bulkUpdateUserStatus(req.user!.accountId, userIds, status);
    return sendSuccess(res, result, 'Bulk status updated');
  } catch (error) {
    next(error);
  }
};

export const getAllFoods = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const page = Number(req.query.page) || 1;
    const limit = Number(req.query.limit) || 50;
    const search = (req.query.search as string) || '';
    const result = await adminService.getAllFoods(page, limit, search);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getFoodCategories = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await adminService.getFoodCategories();
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getFoodById = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const foodId = Number(req.params.foodId);
    const result = await adminService.getFoodById(foodId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const createFood = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await adminService.createFood(req.user!.accountId, req.body);
    return sendSuccess(res, result, 'Food item created', 201);
  } catch (error) {
    next(error);
  }
};

export const updateFood = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const foodId = Number(req.params.foodId);
    const result = await adminService.updateFood(req.user!.accountId, foodId, req.body);
    return sendSuccess(res, result, 'Food item updated');
  } catch (error) {
    next(error);
  }
};

export const deleteFood = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const foodId = Number(req.params.foodId);
    const result = await adminService.deleteFood(req.user!.accountId, foodId);
    return sendSuccess(res, result, 'Food item deleted');
  } catch (error) {
    next(error);
  }
};
