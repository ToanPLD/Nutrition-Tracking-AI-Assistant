import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../../database/prisma.service';
import { UpdateProfileDto } from './dto/update-profile.dto';
import { UpdateGoalsDto } from './dto/update-goals.dto';
import { CreateWeightDto } from './dto/create-weight.dto';
import { FoodPreferenceDto } from './dto/food-preference.dto';
import { GoalType } from '@prisma/client';

export interface TdeeParams {
  weight: number;
  height: number;
  age: number;
  gender: string;
  activityLevel?: string;
  goalType?: string;
}

@Injectable()
export class UsersService {
  constructor(private prisma: PrismaService) {}

  static calculateTdee(params: TdeeParams): number {
    const { weight, height, age, gender, activityLevel = 'moderate', goalType = 'GENERAL' } = params;

    // Mifflin-St Jeor Equation
    let bmr = 10 * weight + 6.25 * height - 5 * age;
    bmr += gender.toUpperCase() === 'MALE' ? 5 : -161;

    let multiplier = 1.55; // moderate
    if (activityLevel === 'sedentary') multiplier = 1.2;
    else if (activityLevel === 'light') multiplier = 1.375;
    else if (activityLevel === 'active') multiplier = 1.725;

    let tdee = bmr * multiplier;

    if (goalType === 'WEIGHT_LOSS') {
      tdee -= 400;
    } else if (goalType === 'MUSCLE_GAIN') {
      tdee += 350;
    }

    return Math.round(tdee);
  }

  async getProfile(userId: number) {
    const user = await this.prisma.user.findUnique({
      where: { id: userId },
      include: {
        account: {
          select: {
            id: true,
            email: true,
            role: true,
            status: true,
          },
        },
      },
    });

    if (!user) {
      throw new NotFoundException('User profile not found');
    }

    return user;
  }

  async updateProfile(userId: number, dto: UpdateProfileDto) {
    const updated = await this.prisma.user.update({
      where: { id: userId },
      data: {
        fullName: dto.fullName,
        gender: dto.gender,
        age: dto.age,
        height: dto.height,
        weight: dto.weight,
        hasCompletedSetup: true,
      },
    });

    // Also record initial weight in weight history if weight was provided
    if (dto.weight) {
      await this.prisma.weightHistory.create({
        data: {
          userId,
          weight: dto.weight,
          note: 'Profile update',
        },
      });
    }

    return updated;
  }

  async getGoals(userId: number) {
    const goal = await this.prisma.userGoal.findFirst({
      where: { userId },
      orderBy: { createdAt: 'desc' },
    });

    if (!goal) {
      // Calculate sensible defaults from user profile
      const user = await this.getProfile(userId);
      const targetCalories = UsersService.calculateTdee({
        weight: user.weight || 70,
        height: user.height || 170,
        age: user.age || 25,
        gender: user.gender,
        goalType: 'MAINTENANCE',
      });

      return {
        targetCalories,
        targetProtein: Math.round((targetCalories * 0.25) / 4),
        targetCarbs: Math.round((targetCalories * 0.5) / 4),
        targetFat: Math.round((targetCalories * 0.25) / 9),
        goalType: GoalType.MAINTENANCE,
        activityLevel: 'moderate',
      };
    }

    return goal;
  }

  async updateGoals(userId: number, dto: UpdateGoalsDto) {
    const goal = await this.prisma.userGoal.create({
      data: {
        userId,
        targetCalories: dto.targetCalories,
        targetProtein: dto.targetProtein,
        targetCarbs: dto.targetCarbs,
        targetFat: dto.targetFat,
        targetWeight: dto.targetWeight,
        goalType: dto.goalType || GoalType.GENERAL,
        activityLevel: dto.activityLevel || 'moderate',
      },
    });

    return goal;
  }

  async recordWeight(userId: number, dto: CreateWeightDto) {
    const history = await this.prisma.weightHistory.create({
      data: {
        userId,
        weight: dto.weight,
        note: dto.note,
      },
    });

    // Sync latest weight to user profile
    await this.prisma.user.update({
      where: { id: userId },
      data: { weight: dto.weight },
    });

    return history;
  }

  async getWeightHistory(userId: number) {
    return this.prisma.weightHistory.findMany({
      where: { userId },
      orderBy: { recordedAt: 'desc' },
      take: 60,
    });
  }

  async getPreferences(userId: number) {
    return this.prisma.userFoodPreference.findMany({
      where: { userId },
      orderBy: { createdAt: 'desc' },
    });
  }

  async addPreference(userId: number, dto: FoodPreferenceDto) {
    return this.prisma.userFoodPreference.upsert({
      where: {
        userId_foodName_preferenceType: {
          userId,
          foodName: dto.foodName,
          preferenceType: dto.preferenceType,
        },
      },
      update: {
        mealSlot: dto.mealSlot,
        note: dto.note,
      },
      create: {
        userId,
        foodName: dto.foodName,
        preferenceType: dto.preferenceType,
        mealSlot: dto.mealSlot,
        note: dto.note,
      },
    });
  }

  async deletePreference(userId: number, id: number) {
    const pref = await this.prisma.userFoodPreference.findFirst({
      where: { id, userId },
    });

    if (!pref) {
      throw new NotFoundException('Preference not found');
    }

    await this.prisma.userFoodPreference.delete({
      where: { id },
    });

    return { success: true };
  }
}
