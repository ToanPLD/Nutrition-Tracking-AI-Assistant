import { IsEnum, IsNumber, IsOptional, IsString, Max, Min } from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { GoalType } from '@prisma/client';

export class UpdateGoalsDto {
  @ApiProperty({ example: 2100, description: 'Target daily calories' })
  @IsNumber()
  @Min(800)
  @Max(8000)
  targetCalories!: number;

  @ApiProperty({ example: 140, description: 'Target protein in grams' })
  @IsNumber()
  @Min(10)
  @Max(500)
  targetProtein!: number;

  @ApiProperty({ example: 230, description: 'Target carbs in grams' })
  @IsNumber()
  @Min(10)
  @Max(800)
  targetCarbs!: number;

  @ApiProperty({ example: 65, description: 'Target fat in grams' })
  @IsNumber()
  @Min(10)
  @Max(300)
  targetFat!: number;

  @ApiPropertyOptional({ example: 68.0, description: 'Target body weight in kg' })
  @IsOptional()
  @IsNumber()
  targetWeight?: number;

  @ApiPropertyOptional({ enum: GoalType, example: GoalType.WEIGHT_LOSS })
  @IsOptional()
  @IsEnum(GoalType)
  goalType?: GoalType;

  @ApiPropertyOptional({ example: 'moderate' })
  @IsOptional()
  @IsString()
  activityLevel?: string;
}
