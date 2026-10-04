import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../src/app.module';
import { PrismaService } from '../src/database/prisma.service';

describe('Meals & Foods (e2e)', () => {
  let app: INestApplication;
  let userToken: string;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    app.setGlobalPrefix('api/v1');
    app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
    await app.init();

    // Login as user
    const loginRes = await request(app.getHttpServer())
      .post('/api/v1/auth/login')
      .send({ email: 'user@calai.local', password: 'User123!' });

    userToken = loginRes.body.data.accessToken;
    const userId = loginRes.body.data.account.user.id;

    // Clean existing test meals for user
    const prisma = app.get(PrismaService);
    await prisma.meal.deleteMany({ where: { userId } });
    await prisma.dailyNutritionLog.deleteMany({ where: { userId } });
  });

  afterAll(async () => {
    await app.close();
  });

  it('searches foods catalog and retrieves categories', async () => {
    // 1. Categories
    const catRes = await request(app.getHttpServer()).get('/api/v1/foods/categories');
    expect(catRes.status).toBe(200);
    expect(Array.isArray(catRes.body.data)).toBe(true);
    expect(catRes.body.data.length).toBeGreaterThanOrEqual(1);

    // 2. Search foods
    const searchRes = await request(app.getHttpServer()).get('/api/v1/foods/search?q=Bánh');
    expect(searchRes.status).toBe(200);
    expect(searchRes.body.data.items).toBeDefined();
    expect(searchRes.body.data.items.length).toBeGreaterThanOrEqual(1);
    expect(searchRes.body.data.pagination.total).toBeGreaterThanOrEqual(1);
  });

  it('logs a meal, verifies atomic daily summary, and deletes meal cleanly', async () => {
    // Find a food item to log
    const foodsRes = await request(app.getHttpServer()).get('/api/v1/foods/search?limit=1');
    const targetFood = foodsRes.body.data.items[0];
    expect(targetFood).toBeDefined();

    const testDate = '2026-10-05';

    // 1. Create a meal
    const mealRes = await request(app.getHttpServer())
      .post('/api/v1/meals')
      .set('Authorization', `Bearer ${userToken}`)
      .send({
        mealType: 'BREAKFAST',
        mealDate: testDate,
        items: [
          {
            foodId: targetFood.id,
            quantity: 2.0,
            calories: targetFood.calories,
            protein: targetFood.protein,
            carbs: targetFood.carbs,
            fat: targetFood.fat,
          },
        ],
      });

    expect(mealRes.status).toBe(201);
    const createdMeal = mealRes.body.data;
    expect(createdMeal.id).toBeDefined();
    expect(createdMeal.items.length).toBe(1);

    // 2. Verify Daily Summary
    const summaryRes = await request(app.getHttpServer())
      .get(`/api/v1/meals/daily-summary?date=${testDate}`)
      .set('Authorization', `Bearer ${userToken}`);

    expect(summaryRes.status).toBe(200);
    expect(summaryRes.body.data.consumed.calories).toBe(targetFood.calories * 2);
    expect(summaryRes.body.data.mealCount).toBe(1);

    // 3. Delete the meal
    const deleteRes = await request(app.getHttpServer())
      .delete(`/api/v1/meals/${createdMeal.id}`)
      .set('Authorization', `Bearer ${userToken}`);

    expect(deleteRes.status).toBe(200);

    // 4. Verify Daily Summary resets back to 0
    const afterDeleteSummary = await request(app.getHttpServer())
      .get(`/api/v1/meals/daily-summary?date=${testDate}`)
      .set('Authorization', `Bearer ${userToken}`);

    expect(afterDeleteSummary.body.data.consumed.calories).toBe(0);
    expect(afterDeleteSummary.body.data.mealCount).toBe(0);
  });
});
