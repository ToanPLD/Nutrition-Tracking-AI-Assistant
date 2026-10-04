import {
  Controller,
  Get,
  Patch,
  Put,
  Post,
  Delete,
  Body,
  Param,
  ParseIntPipe,
  UseGuards,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse, ApiBearerAuth } from '@nestjs/swagger';
import { UsersService } from './users.service';
import { UpdateProfileDto } from './dto/update-profile.dto';
import { UpdateGoalsDto } from './dto/update-goals.dto';
import { CreateWeightDto } from './dto/create-weight.dto';
import { FoodPreferenceDto } from './dto/food-preference.dto';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser, CurrentUserPayload } from '../../common/decorators/current-user.decorator';

@ApiTags('Users')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard)
@Controller('users')
export class UsersController {
  constructor(private usersService: UsersService) {}

  @Get('profile')
  @ApiOperation({ summary: 'Get current user profile' })
  @ApiResponse({ status: 200, description: 'User profile retrieved successfully' })
  async getProfile(@CurrentUser() user: CurrentUserPayload) {
    const profile = await this.usersService.getProfile(user.userId);
    return { data: profile };
  }

  @Patch('profile')
  @ApiOperation({ summary: 'Update physical profile' })
  @ApiResponse({ status: 200, description: 'Profile updated' })
  async updateProfile(
    @CurrentUser() user: CurrentUserPayload,
    @Body() dto: UpdateProfileDto,
  ) {
    const updated = await this.usersService.updateProfile(user.userId, dto);
    return {
      message: 'Profile updated successfully',
      data: updated,
    };
  }

  @Get('goals')
  @ApiOperation({ summary: 'Get daily calorie and macronutrient goals' })
  @ApiResponse({ status: 200, description: 'Goals retrieved' })
  async getGoals(@CurrentUser() user: CurrentUserPayload) {
    const goals = await this.usersService.getGoals(user.userId);
    return { data: goals };
  }

  @Put('goals')
  @ApiOperation({ summary: 'Set or update daily goals' })
  @ApiResponse({ status: 200, description: 'Goals updated' })
  async updateGoals(
    @CurrentUser() user: CurrentUserPayload,
    @Body() dto: UpdateGoalsDto,
  ) {
    const goals = await this.usersService.updateGoals(user.userId, dto);
    return {
      message: 'Nutrition goals updated successfully',
      data: goals,
    };
  }

  @Get('weight-history')
  @ApiOperation({ summary: 'Get weight tracking history' })
  async getWeightHistory(@CurrentUser() user: CurrentUserPayload) {
    const history = await this.usersService.getWeightHistory(user.userId);
    return { data: history };
  }

  @Post('weight-history')
  @ApiOperation({ summary: 'Record a new weight entry' })
  async recordWeight(
    @CurrentUser() user: CurrentUserPayload,
    @Body() dto: CreateWeightDto,
  ) {
    const record = await this.usersService.recordWeight(user.userId, dto);
    return {
      message: 'Weight record added successfully',
      data: record,
    };
  }

  @Get('preferences')
  @ApiOperation({ summary: 'Get dietary preferences and allergies' })
  async getPreferences(@CurrentUser() user: CurrentUserPayload) {
    const preferences = await this.usersService.getPreferences(user.userId);
    return { data: preferences };
  }

  @Post('preferences')
  @ApiOperation({ summary: 'Add or update food preference or allergy' })
  async addPreference(
    @CurrentUser() user: CurrentUserPayload,
    @Body() dto: FoodPreferenceDto,
  ) {
    const pref = await this.usersService.addPreference(user.userId, dto);
    return {
      message: 'Preference saved successfully',
      data: pref,
    };
  }

  @Delete('preferences/:id')
  @ApiOperation({ summary: 'Remove food preference' })
  async deletePreference(
    @CurrentUser() user: CurrentUserPayload,
    @Param('id', ParseIntPipe) id: number,
  ) {
    await this.usersService.deletePreference(user.userId, id);
    return { message: 'Preference deleted successfully' };
  }
}
