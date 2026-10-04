import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../../database/prisma.service';

@Injectable()
export class FoodsService {
  constructor(private prisma: PrismaService) {}

  async searchFoods(query?: string, categoryId?: number, page = 1, limit = 20) {
    const skip = (page - 1) * limit;
    const where: any = {};

    if (query && query.trim()) {
      where.name = {
        contains: query.trim(),
        mode: 'insensitive',
      };
    }

    if (categoryId) {
      where.categoryId = categoryId;
    }

    const [items, total] = await Promise.all([
      this.prisma.food.findMany({
        where,
        include: {
          category: {
            select: { id: true, name: true },
          },
        },
        skip,
        take: limit,
        orderBy: { name: 'asc' },
      }),
      this.prisma.food.count({ where }),
    ]);

    return {
      items,
      pagination: {
        total,
        page,
        limit,
        totalPages: Math.ceil(total / limit),
      },
    };
  }

  async getCategories() {
    return this.prisma.foodCategory.findMany({
      include: {
        _count: {
          select: { foods: true },
        },
      },
      orderBy: { name: 'asc' },
    });
  }

  async getFoodById(id: number) {
    const food = await this.prisma.food.findUnique({
      where: { id },
      include: { category: true },
    });

    if (!food) {
      throw new NotFoundException(`Food item with ID ${id} not found`);
    }

    return food;
  }
}
