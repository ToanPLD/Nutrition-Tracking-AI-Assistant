import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../../database/prisma.service';
import { CreateMealDto } from './dto/create-meal.dto';
import { UsersService } from '../users/users.service';

export interface NutritionTotals {
  calories: number;
  protein: number;
  carbs: number;
  fat: number;
}

@Injectable()
export class MealsService {
  constructor(
    private prisma: PrismaService,
    private usersService: UsersService,
  ) {}

  static sumNutrition(
    items: Array<{
      calories: number;
      protein: number;
      carbs: number;
      fat: number;
      quantity?: number;
    }>,
  ): NutritionTotals {
    let calories = 0;
    let protein = 0;
    let carbs = 0;
    let fat = 0;

    for (const item of items) {
      const qty = item.quantity ?? 1;
      calories += item.calories * qty;
      protein += item.protein * qty;
      carbs += item.carbs * qty;
      fat += item.fat * qty;
    }

    return {
      calories: Math.round(calories * 10) / 10,
      protein: Math.round(protein * 10) / 10,
      carbs: Math.round(carbs * 10) / 10,
      fat: Math.round(fat * 10) / 10,
    };
  }

  async createMeal(userId: number, dto: CreateMealDto) {
    const mealDate = new Date(dto.mealDate);

    return this.prisma.$transaction(async (tx) => {
      // 1. Resolve each item's nutrition
      const resolvedItems: Array<{
        foodId: number;
        quantity: number;
        calories: number;
        protein: number;
        carbs: number;
        fat: number;
      }> = [];

      for (const it of dto.items) {
        const qty = it.quantity ?? 1.0;
        let c = it.calories;
        let p = it.protein;
        let cb = it.carbs;
        let f = it.fat;

        if (c === undefined || p === undefined || cb === undefined || f === undefined) {
          const food = await tx.food.findUnique({ where: { id: it.foodId } });
          if (!food) {
            throw new NotFoundException(`Food item with ID ${it.foodId} not found`);
          }
          c = food.calories;
          p = food.protein;
          cb = food.carbs;
          f = food.fat;
        }

        resolvedItems.push({
          foodId: it.foodId,
          quantity: qty,
          calories: Math.round(c * qty * 10) / 10,
          protein: Math.round(p * qty * 10) / 10,
          carbs: Math.round(cb * qty * 10) / 10,
          fat: Math.round(f * qty * 10) / 10,
        });
      }

      // 2. Create Meal with Items
      const meal = await tx.meal.create({
        data: {
          userId,
          mealType: dto.mealType,
          mealDate,
          items: {
            create: resolvedItems,
          },
        },
        include: {
          items: {
            include: { food: true },
          },
        },
      });

      // 3. Atomically recalculate and upsert DailyNutritionLog
      await this.recalculateDailyLog(tx, userId, mealDate);

      return meal;
    });
  }

  async getMealsByDate(userId: number, dateStr: string) {
    const mealDate = new Date(dateStr);
    return this.prisma.meal.findMany({
      where: {
        userId,
        mealDate,
      },
      include: {
        items: {
          include: { food: true },
        },
      },
      orderBy: { createdAt: 'asc' },
    });
  }

  async getDailySummary(userId: number, dateStr: string) {
    const mealDate = new Date(dateStr);

    const [dailyLog, goals, meals] = await Promise.all([
      this.prisma.dailyNutritionLog.findUnique({
        where: {
          userId_date: {
            userId,
            date: mealDate,
          },
        },
      }),
      this.usersService.getGoals(userId),
      this.getMealsByDate(userId, dateStr),
    ]);

    const consumed = {
      calories: dailyLog?.totalCalories ?? 0,
      protein: dailyLog?.totalProtein ?? 0,
      carbs: dailyLog?.totalCarbs ?? 0,
      fat: dailyLog?.totalFat ?? 0,
    };

    const target = {
      calories: goals.targetCalories,
      protein: goals.targetProtein,
      carbs: goals.targetCarbs,
      fat: goals.targetFat,
    };

    const remaining = {
      calories: Math.max(0, target.calories - consumed.calories),
      protein: Math.max(0, target.protein - consumed.protein),
      carbs: Math.max(0, target.carbs - consumed.carbs),
      fat: Math.max(0, target.fat - consumed.fat),
    };

    const progressPercentage = target.calories > 0
      ? Math.min(100, Math.round((consumed.calories / target.calories) * 100))
      : 0;

    return {
      date: dateStr,
      consumed,
      target,
      remaining,
      progressPercentage,
      mealCount: meals.length,
      meals,
    };
  }

  async deleteMeal(userId: number, mealId: number) {
    const meal = await this.prisma.meal.findFirst({
      where: { id: mealId, userId },
    });

    if (!meal) {
      throw new NotFoundException(`Meal with ID ${mealId} not found`);
    }

    return this.prisma.$transaction(async (tx) => {
      await tx.meal.delete({ where: { id: mealId } });
      await this.recalculateDailyLog(tx, userId, meal.mealDate);
      return { success: true };
    });
  }

  private async recalculateDailyLog(tx: any, userId: number, date: Date) {
    // Sum all meal items logged for this date
    const allItems = await tx.mealItem.findMany({
      where: {
        meal: {
          userId,
          mealDate: date,
        },
      },
    });

    let totalCalories = 0;
    let totalProtein = 0;
    let totalCarbs = 0;
    let totalFat = 0;

    for (const item of allItems) {
      totalCalories += item.calories;
      totalProtein += item.protein;
      totalCarbs += item.carbs;
      totalFat += item.fat;
    }

    await tx.dailyNutritionLog.upsert({
      where: {
        userId_date: {
          userId,
          date,
        },
      },
      update: {
        totalCalories: Math.round(totalCalories * 10) / 10,
        totalProtein: Math.round(totalProtein * 10) / 10,
        totalCarbs: Math.round(totalCarbs * 10) / 10,
        totalFat: Math.round(totalFat * 10) / 10,
      },
      create: {
        userId,
        date,
        totalCalories: Math.round(totalCalories * 10) / 10,
        totalProtein: Math.round(totalProtein * 10) / 10,
        totalCarbs: Math.round(totalCarbs * 10) / 10,
        totalFat: Math.round(totalFat * 10) / 10,
      },
    });
  }
}
