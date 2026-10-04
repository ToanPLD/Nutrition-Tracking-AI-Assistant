import {
  Controller,
  Get,
  Param,
  Query,
  ParseIntPipe,
  DefaultValuePipe,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiQuery, ApiResponse } from '@nestjs/swagger';
import { FoodsService } from './foods.service';

@ApiTags('Foods')
@Controller('foods')
export class FoodsController {
  constructor(private foodsService: FoodsService) {}

  @Get('search')
  @ApiOperation({ summary: 'Search Vietnamese foods catalog with pagination' })
  @ApiQuery({ name: 'q', required: false, description: 'Food name keyword' })
  @ApiQuery({ name: 'categoryId', required: false, type: Number })
  @ApiQuery({ name: 'page', required: false, type: Number, example: 1 })
  @ApiQuery({ name: 'limit', required: false, type: Number, example: 20 })
  async searchFoods(
    @Query('q') q?: string,
    @Query('categoryId') categoryId?: string,
    @Query('page', new DefaultValuePipe(1), ParseIntPipe) page: number = 1,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number = 20,
  ) {
    const catId = categoryId ? parseInt(categoryId, 10) : undefined;
    const result = await this.foodsService.searchFoods(q, catId, page, limit);
    return { data: result };
  }

  @Get('categories')
  @ApiOperation({ summary: 'Get all food categories with item counts' })
  async getCategories() {
    const categories = await this.foodsService.getCategories();
    return { data: categories };
  }

  @Get(':id')
  @ApiOperation({ summary: 'Get food item details by ID' })
  async getFoodById(@Param('id', ParseIntPipe) id: number) {
    const food = await this.foodsService.getFoodById(id);
    return { data: food };
  }
}
