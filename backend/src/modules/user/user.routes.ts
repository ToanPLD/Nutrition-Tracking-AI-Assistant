import { Router } from 'express';
import {
  analyzeFoodImage,
  confirmFoodAnalysis,
  createMeal,
  deleteFoodAnalysis,
  deleteMeal,
  getFoodAnalysisById,
  getFoodAnalysisHistory,
  getUserDashboard,
  getUserGoals,
  getUserMealHistory,
  getUserMeals,
  getUserProfile,
  reanalyzeFoodImage,
  saveFoodAnalysisToMealLog,
  searchFoods,
  updateMeal,
  updateUserGoals,
  updateUserProfile,
} from './controllers/user.controller';
import {
  createSchedule,
  deleteSchedule,
  listDiscoverMeals,
  listSchedules,
  publishSchedule,
  updateSchedule,
} from './controllers/schedule.controller';
import {
  deleteFoodPreference,
  listFoodPreferences,
  upsertFoodPreference,
} from './controllers/preference.controller';

const userRouter = Router();

// Profile & Goals
userRouter.get('/profile', getUserProfile);
userRouter.patch('/profile', updateUserProfile);
userRouter.get('/goals', getUserGoals);
userRouter.patch('/goals', updateUserGoals);
userRouter.get('/dashboard', getUserDashboard);

// Meals & Foods
userRouter.get('/meals', getUserMeals);
userRouter.get('/meals/history', getUserMealHistory);
userRouter.post('/meals', createMeal);
userRouter.patch('/meals/:mealId', updateMeal);
userRouter.delete('/meals/:mealId', deleteMeal);
userRouter.get('/foods/search', searchFoods);

// Food Analysis & Vision
userRouter.get('/food-analysis/history', getFoodAnalysisHistory);
userRouter.get('/food-analysis/:analysisId', getFoodAnalysisById);
userRouter.post('/food-analysis/analyze', analyzeFoodImage);
userRouter.patch('/food-analysis/:analysisId/confirm', confirmFoodAnalysis);
userRouter.post('/food-analysis/:analysisId/save', saveFoodAnalysisToMealLog);
userRouter.post('/food-analysis/:analysisId/reanalyze', reanalyzeFoodImage);
userRouter.delete('/food-analysis/:analysisId', deleteFoodAnalysis);

// Schedules & Meal Plans
userRouter.get('/schedules', listSchedules);
userRouter.post('/schedules', createSchedule);
userRouter.patch('/schedules/:scheduleId', updateSchedule);
userRouter.delete('/schedules/:scheduleId', deleteSchedule);
userRouter.post('/schedules/:scheduleId/publish', publishSchedule);
userRouter.get('/discover/meals', listDiscoverMeals);

// Food Preferences
userRouter.get('/food-preferences', listFoodPreferences);
userRouter.post('/food-preferences', upsertFoodPreference);
userRouter.delete('/food-preferences/:preferenceId', deleteFoodPreference);

export default userRouter;
