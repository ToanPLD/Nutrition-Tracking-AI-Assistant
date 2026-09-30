import { Router } from 'express';
import {
  bulkUpdateUserStatus,
  createFood,
  createUser,
  deleteFood,
  deleteUser,
  getAdminAnalytics,
  getAdminProfile,
  getAdminStats,
  getAllFoods,
  getAllUsers,
  getAuditLogs,
  getFoodById,
  getFoodCategories,
  getRoleAccounts,
  getSecurityOverview,
  getUserById,
  getUserStatistics,
  updateAccountRole,
  updateFood,
  updateUser,
  updateUserStatus,
} from './admin.controller';

const adminRouter = Router();

// Profile & Stats
adminRouter.get('/profile', getAdminProfile);
adminRouter.get('/stats', getAdminStats);
adminRouter.get('/analytics', getAdminAnalytics);

// Security & Roles
adminRouter.get('/security/overview', getSecurityOverview);
adminRouter.get('/security/roles', getRoleAccounts);
adminRouter.patch('/security/roles/:accountId', updateAccountRole);
adminRouter.get('/security/audit-logs', getAuditLogs);

// Foods Management
adminRouter.get('/foods', getAllFoods);
adminRouter.get('/foods/categories', getFoodCategories);
adminRouter.get('/foods/:foodId', getFoodById);
adminRouter.post('/foods', createFood);
adminRouter.put('/foods/:foodId', updateFood);
adminRouter.delete('/foods/:foodId', deleteFood);

// Users Management
adminRouter.get('/users', getAllUsers);
adminRouter.get('/users/:userId', getUserById);
adminRouter.get('/users/:userId/statistics', getUserStatistics);
adminRouter.post('/users', createUser);
adminRouter.put('/users/:userId', updateUser);
adminRouter.patch('/users/:userId/status', updateUserStatus);
adminRouter.delete('/users/:userId', deleteUser);
adminRouter.post('/users/bulk-status', bulkUpdateUserStatus);

export default adminRouter;
