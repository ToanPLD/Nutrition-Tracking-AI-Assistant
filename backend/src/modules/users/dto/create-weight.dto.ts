import { IsNumber, IsOptional, IsString, Max, Min } from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export class CreateWeightDto {
  @ApiProperty({ example: 69.5, description: 'Weight recorded in kg' })
  @IsNumber()
  @Min(20)
  @Max(300)
  weight!: number;

  @ApiPropertyOptional({ example: 'Weighed in morning before breakfast' })
  @IsOptional()
  @IsString()
  note?: string;
}
