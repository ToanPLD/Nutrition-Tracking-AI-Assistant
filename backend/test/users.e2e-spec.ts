import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../src/app.module';

describe('UsersController (e2e)', () => {
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

    // Login as seeded user to get JWT
    const loginRes = await request(app.getHttpServer())
      .post('/api/v1/auth/login')
      .send({ email: 'user@calai.local', password: 'User123!' });

    userToken = loginRes.body.data.accessToken;
  });

  afterAll(async () => {
    await app.close();
  });

  it('/api/v1/users/profile (PATCH & GET)', async () => {
    // 1. Update profile
    const patchRes = await request(app.getHttpServer())
      .patch('/api/v1/users/profile')
      .set('Authorization', `Bearer ${userToken}`)
      .send({
        fullName: 'Nguyen Van A Updated',
        height: 178,
        weight: 71.5,
        age: 27,
      });

    expect(patchRes.status).toBe(200);
    expect(patchRes.body.data.fullName).toBe('Nguyen Van A Updated');

    // 2. Fetch profile
    const getRes = await request(app.getHttpServer())
      .get('/api/v1/users/profile')
      .set('Authorization', `Bearer ${userToken}`);

    expect(getRes.status).toBe(200);
    expect(getRes.body.data.height).toBe(178);
    expect(getRes.body.data.weight).toBe(71.5);
  });

  it('/api/v1/users/goals (PUT & GET)', async () => {
    const updateRes = await request(app.getHttpServer())
      .put('/api/v1/users/goals')
      .set('Authorization', `Bearer ${userToken}`)
      .send({
        targetCalories: 2200,
        targetProtein: 150,
        targetCarbs: 240,
        targetFat: 70,
        targetWeight: 69,
        goalType: 'WEIGHT_LOSS',
      });

    expect(updateRes.status).toBe(200);
    expect(updateRes.body.data.targetCalories).toBe(2200);

    const getRes = await request(app.getHttpServer())
      .get('/api/v1/users/goals')
      .set('Authorization', `Bearer ${userToken}`);

    expect(getRes.status).toBe(200);
    expect(getRes.body.data.targetProtein).toBe(150);
  });

  it('/api/v1/users/weight-history (POST & GET)', async () => {
    const postRes = await request(app.getHttpServer())
      .post('/api/v1/users/weight-history')
      .set('Authorization', `Bearer ${userToken}`)
      .send({ weight: 71.0, note: 'Weighed morning' });

    expect(postRes.status).toBe(201);
    expect(postRes.body.data.weight).toBe(71.0);

    const getRes = await request(app.getHttpServer())
      .get('/api/v1/users/weight-history')
      .set('Authorization', `Bearer ${userToken}`);

    expect(getRes.status).toBe(200);
    expect(Array.isArray(getRes.body.data)).toBe(true);
    expect(getRes.body.data.length).toBeGreaterThanOrEqual(1);
  });

  it('/api/v1/users/preferences (POST, GET & DELETE)', async () => {
    // 1. Add preference
    const postRes = await request(app.getHttpServer())
      .post('/api/v1/users/preferences')
      .set('Authorization', `Bearer ${userToken}`)
      .send({
        foodName: 'Đậu phộng',
        preferenceType: 'ALLERGY',
        note: 'Dị ứng hạt',
      });

    expect(postRes.status).toBe(201);
    const prefId = postRes.body.data.id;
    expect(prefId).toBeDefined();

    // 2. Get preferences
    const getRes = await request(app.getHttpServer())
      .get('/api/v1/users/preferences')
      .set('Authorization', `Bearer ${userToken}`);

    expect(getRes.status).toBe(200);
    const found = getRes.body.data.find((p: any) => p.foodName === 'Đậu phộng');
    expect(found).toBeDefined();

    // 3. Delete preference
    const delRes = await request(app.getHttpServer())
      .delete(`/api/v1/users/preferences/${prefId}`)
      .set('Authorization', `Bearer ${userToken}`);

    expect(delRes.status).toBe(200);
  });
});
