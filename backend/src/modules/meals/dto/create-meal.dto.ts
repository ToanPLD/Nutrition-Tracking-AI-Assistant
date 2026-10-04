import {
  IsArray,
  IsEnum,
  IsISO8601,
  IsNotEmpty,
  IsNumber,
  IsOptional,
  Min,
  ValidateNested,
} from 'class-validator';
import { Type } from 'class-transformer';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { MealType } from '@prisma/client';

export class CreateMealItemDto {
  @ApiProperty({ example: 1, description: 'ID of the food item' })
  @IsNumber()
  foodId!: number;

  @ApiPropertyOptional({ example: 1.0, description: 'Serving multiplier (default 1.0)' })
  @IsOptional()
  @IsNumber()
  @Min(0.1)
  quantity?: number;

  @ApiPropertyOptional({ example: 350.0, description: 'Override or pre-calculated calories' })
  @IsOptional()
  @IsNumber()
  calories?: number;

  @ApiPropertyOptional({ example: 25.0 })
  @IsOptional()
  @IsNumber()
  protein?: number;

  @ApiPropertyOptional({ example: 40.0 })
  @IsOptional()
  @IsNumber()
  carbs?: number;

  @ApiPropertyOptional({ example: 10.0 })
  @IsOptional()
  @IsNumber()
  fat?: number;
}

export class CreateMealDto {
  @ApiProperty({ enum: MealType, example: MealType.BREAKFAST })
  @IsEnum(MealType)
  mealType!: MealType;

  @ApiProperty({ example: '2026-10-05', description: 'Date of meal in YYYY-MM-DD format' })
  @IsISO8601({ strict: true }, { message: 'mealDate must be in valid ISO date format (YYYY-MM-DD)' })
  @IsNotEmpty()
  mealDate!: string;

  @ApiProperty({ type: [CreateMealItemDto], description: 'List of dishes in this meal' })
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => CreateMealItemDto)
  items!: CreateMealItemDto[];
}
