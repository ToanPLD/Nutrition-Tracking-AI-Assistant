import { IsEnum, IsNotEmpty, IsOptional, IsString } from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { PreferenceType } from '@prisma/client';

export class FoodPreferenceDto {
  @ApiProperty({ example: 'Hải sản', description: 'Name of preferred, disliked, or allergen food' })
  @IsString()
  @IsNotEmpty()
  foodName!: string;

  @ApiProperty({ enum: PreferenceType, example: PreferenceType.ALLERGY })
  @IsEnum(PreferenceType)
  preferenceType!: PreferenceType;

  @ApiPropertyOptional({ example: 'any', description: 'Meal slot: breakfast, lunch, dinner, snack, any' })
  @IsOptional()
  @IsString()
  mealSlot?: string;

  @ApiPropertyOptional({ example: 'Dị ứng tôm cua' })
  @IsOptional()
  @IsString()
  note?: string;
}
