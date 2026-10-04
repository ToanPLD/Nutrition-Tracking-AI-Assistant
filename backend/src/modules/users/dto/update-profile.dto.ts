import { IsEnum, IsNumber, IsOptional, IsString, Max, Min } from 'class-validator';
import { ApiPropertyOptional } from '@nestjs/swagger';
import { Gender } from '@prisma/client';

export class UpdateProfileDto {
  @ApiPropertyOptional({ example: 'Nguyen Van A' })
  @IsOptional()
  @IsString()
  fullName?: string;

  @ApiPropertyOptional({ enum: Gender, example: Gender.MALE })
  @IsOptional()
  @IsEnum(Gender)
  gender?: Gender;

  @ApiPropertyOptional({ example: 25 })
  @IsOptional()
  @IsNumber()
  @Min(10)
  @Max(120)
  age?: number;

  @ApiPropertyOptional({ example: 175.0, description: 'Height in cm' })
  @IsOptional()
  @IsNumber()
  @Min(50)
  @Max(250)
  height?: number;

  @ApiPropertyOptional({ example: 70.0, description: 'Weight in kg' })
  @IsOptional()
  @IsNumber()
  @Min(20)
  @Max(300)
  weight?: number;
}
