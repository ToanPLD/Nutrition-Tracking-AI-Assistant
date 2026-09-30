export interface UserProfileDto {
  name?: string;
  gender?: 'male' | 'female' | 'other';
  age?: number;
  height?: number;
  weight?: number;
}

export interface UserGoalsDto {
  dailyCalories?: number;
  targetWeight?: number;
  goal?: 'lose' | 'maintain' | 'gain' | 'weight_loss' | 'muscle_gain' | 'general';
  activityLevel?: string;
  protein?: number;
  carbs?: number;
  fats?: number;
}

export interface CreateMealDto {
  foodId?: number;
  foodName?: string;
  mealType: 'breakfast' | 'lunch' | 'dinner' | 'snack';
  calories?: number;
  quantity?: number;
  protein?: number;
  carbs?: number;
  fats?: number;
  mealDate?: string;
}

export interface UpdateMealDto {
  foodName?: string;
  mealType?: 'breakfast' | 'lunch' | 'dinner' | 'snack';
  calories?: number;
  quantity?: number;
  protein?: number;
  carbs?: number;
  fats?: number;
  mealDate?: string;
}

export interface ScheduleItemDto {
  dayOffset?: number;
  mealType: 'breakfast' | 'lunch' | 'dinner' | 'snack';
  name: string;
  serving?: string;
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  notes?: string;
  sortOrder?: number;
}

export interface CreateScheduleDto {
  name: string;
  description?: string;
  startDate: string;
  endDate: string;
  color?: string;
  targetCalories?: number;
  source?: 'manual' | 'chat' | 'shared';
  planPayload?: any;
  items?: ScheduleItemDto[];
}

export interface FoodPreferenceDto {
  foodName: string;
  preferenceType: 'favorite' | 'avoided' | 'disliked' | 'allergy';
  mealSlot?: 'breakfast' | 'lunch' | 'dinner' | 'snack' | 'beverage' | 'any';
  note?: string;
  weight?: number;
  source?: 'user' | 'inferred';
}

export interface FoodAnalysisDto {
  imageUrl: string;
  source?: 'upload' | 'camera';
}

export interface ConfirmAnalysisDto {
  name?: string;
  totalKcal?: number;
  protein?: number;
  carbs?: number;
  fats?: number;
  estimatedPortion?: string;
}
