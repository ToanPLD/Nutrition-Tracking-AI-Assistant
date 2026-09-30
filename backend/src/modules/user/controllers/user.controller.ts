import { Request, Response, NextFunction } from 'express';
import { profileService } from '../services/profile.service';
import { mealService } from '../services/meal.service';
import { foodAnalysisService } from '../services/food-analysis.service';
import { sendSuccess } from '../../../shared/responses/api-response';

export const getUserProfile = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await profileService.getProfile(req.user!.accountId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const updateUserProfile = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await profileService.updateProfile(req.user!.accountId, req.body);
    return sendSuccess(res, result, 'Profile updated successfully');
  } catch (error) {
    next(error);
  }
};

export const getUserGoals = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await profileService.getGoals(req.user!.accountId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const updateUserGoals = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await profileService.updateGoals(req.user!.accountId, req.body);
    return sendSuccess(res, result, 'Goals updated successfully');
  } catch (error) {
    next(error);
  }
};

export const getUserDashboard = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await profileService.getDashboard(req.user!.accountId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getUserMeals = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const date = req.query.date as string | undefined;
    const result = await mealService.getMealsByDate(req.user!.accountId, date);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getUserMealHistory = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const limit = Number(req.query.limit) || 14;
    const result = await mealService.getMealHistory(req.user!.accountId, limit);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const createMeal = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await mealService.createMeal(req.user!.accountId, req.body);
    return sendSuccess(res, result, 'Meal logged successfully', 201);
  } catch (error) {
    next(error);
  }
};

export const updateMeal = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const mealId = Number(req.params.mealId);
    const result = await mealService.updateMeal(req.user!.accountId, mealId, req.body);
    return sendSuccess(res, result, 'Meal updated successfully');
  } catch (error) {
    next(error);
  }
};

export const deleteMeal = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const mealId = Number(req.params.mealId);
    const result = await mealService.deleteMeal(req.user!.accountId, mealId);
    return sendSuccess(res, result, 'Meal deleted successfully');
  } catch (error) {
    next(error);
  }
};

export const searchFoods = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const q = (req.query.q as string) || (req.query.search as string) || '';
    const limit = Number(req.query.limit) || 50;
    const category = (req.query.category as string) || '';
    const result = await mealService.searchFoods(q, limit, category);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getFoodAnalysisHistory = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await foodAnalysisService.getHistory(req.user!.accountId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const getFoodAnalysisById = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const analysisId = Number(req.params.analysisId);
    const result = await foodAnalysisService.getById(req.user!.accountId, analysisId);
    return sendSuccess(res, result);
  } catch (error) {
    next(error);
  }
};

export const analyzeFoodImage = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await foodAnalysisService.analyzeImage(req.user!.accountId, req.body);
    return sendSuccess(res, result, 'Image analyzed successfully');
  } catch (error) {
    next(error);
  }
};

export const confirmFoodAnalysis = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const analysisId = Number(req.params.analysisId);
    const result = await foodAnalysisService.confirmAnalysis(req.user!.accountId, analysisId, req.body);
    return sendSuccess(res, result, 'Analysis confirmed');
  } catch (error) {
    next(error);
  }
};

export const saveFoodAnalysisToMealLog = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const analysisId = Number(req.params.analysisId);
    const result = await foodAnalysisService.saveToMealLog(req.user!.accountId, analysisId);
    return sendSuccess(res, result, 'Meal logged from analysis');
  } catch (error) {
    next(error);
  }
};

export const reanalyzeFoodImage = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const analysisId = Number(req.params.analysisId);
    const analysis = await foodAnalysisService.getById(req.user!.accountId, analysisId);
    const result = await foodAnalysisService.analyzeImage(req.user!.accountId, {
      imageUrl: analysis.image_url,
      source: analysis.source,
    });
    return sendSuccess(res, result, 'Image re-analyzed successfully');
  } catch (error) {
    next(error);
  }
};

export const deleteFoodAnalysis = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const analysisId = Number(req.params.analysisId);
    const result = await foodAnalysisService.deleteAnalysis(req.user!.accountId, analysisId);
    return sendSuccess(res, result, 'Analysis deleted');
  } catch (error) {
    next(error);
  }
};
