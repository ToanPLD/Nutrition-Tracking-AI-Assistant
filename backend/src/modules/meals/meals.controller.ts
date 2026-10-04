import {
  Controller,
  Get,
  Post,
  Delete,
  Body,
  Param,
  Query,
  ParseIntPipe,
  UseGuards,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiQuery, ApiResponse, ApiBearerAuth } from '@nestjs/swagger';
import { MealsService } from './meals.service';
import { CreateMealDto } from './dto/create-meal.dto';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser, CurrentUserPayload } from '../../common/decorators/current-user.decorator';

@ApiTags('Meals')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard)
@Controller('meals')
export class MealsController {
  constructor(private mealsService: MealsService) {}

  @Post()
  @ApiOperation({ summary: 'Log a new meal with food items' })
  @ApiResponse({ status: 201, description: 'Meal created and daily nutrition log updated' })
  async createMeal(
    @CurrentUser() user: CurrentUserPayload,
    @Body() dto: CreateMealDto,
  ) {
    const meal = await this.mealsService.createMeal(user.userId, dto);
    return {
      message: 'Meal logged successfully',
      data: meal,
    };
  }

  @Get('today')
  @ApiOperation({ summary: 'Get all meals logged today' })
  async getTodayMeals(@CurrentUser() user: CurrentUserPayload) {
    const todayStr = new Date().toISOString().split('T')[0];
    const meals = await this.mealsService.getMealsByDate(user.userId, todayStr);
    return { data: meals };
  }

  @Get('by-date')
  @ApiOperation({ summary: 'Get meals logged for a specific date' })
  @ApiQuery({ name: 'date', example: '2026-10-05', description: 'YYYY-MM-DD' })
  async getMealsByDate(
    @CurrentUser() user: CurrentUserPayload,
    @Query('date') date: string,
  ) {
    const targetDate = date || new Date().toISOString().split('T')[0];
    const meals = await this.mealsService.getMealsByDate(user.userId, targetDate);
    return { data: meals };
  }

  @Get('daily-summary')
  @ApiOperation({ summary: 'Get comprehensive daily calorie/macro intake vs targets' })
  @ApiQuery({ name: 'date', required: false, example: '2026-10-05', description: 'YYYY-MM-DD' })
  async getDailySummary(
    @CurrentUser() user: CurrentUserPayload,
    @Query('date') date?: string,
  ) {
    const targetDate = date || new Date().toISOString().split('T')[0];
    const summary = await this.mealsService.getDailySummary(user.userId, targetDate);
    return { data: summary };
  }

  @Delete(':id')
  @ApiOperation({ summary: 'Delete a meal and recalculate daily summary' })
  async deleteMeal(
    @CurrentUser() user: CurrentUserPayload,
    @Param('id', ParseIntPipe) id: number,
  ) {
    const result = await this.mealsService.deleteMeal(user.userId, id);
    return {
      message: 'Meal deleted and daily summary updated',
      data: result,
    };
  }
}
