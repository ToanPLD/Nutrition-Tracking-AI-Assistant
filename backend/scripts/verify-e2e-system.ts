import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import request from 'supertest';
import { AppModule } from '../src/app.module';

async function verifySystem() {
  console.log('🚀 [E2E Verification] Bootstrapping NestJS application...');
  const app = await NestFactory.create(AppModule, { logger: false });
  app.setGlobalPrefix('api/v1');
  app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));

  // Swagger setup test
  const config = new DocumentBuilder()
    .setTitle('CalAI Nutrition Tracking API')
    .setVersion('1.0')
    .addBearerAuth()
    .build();
  const document = SwaggerModule.createDocument(app, config);
  SwaggerModule.setup('api/docs', app, document);

  await app.init();
  const server = app.getHttpServer();

  try {
    console.log('\n--- 1. Health Check Test ---');
    const healthRes = await request(server).get('/api/v1/health');
    if (healthRes.status !== 200 || !healthRes.body.success) {
      throw new Error(`Health check failed: ${JSON.stringify(healthRes.body)}`);
    }
    console.log('✅ Health check: OK (200, standardized envelope)');

    console.log('\n--- 2. Admin Authentication & RBAC Test ---');
    const adminLoginRes = await request(server)
      .post('/api/v1/auth/login')
      .send({ email: 'admin@calai.local', password: 'Admin123!' });
    if (adminLoginRes.status !== 200) {
      throw new Error(`Admin login failed: ${JSON.stringify(adminLoginRes.body)}`);
    }
    const adminToken = adminLoginRes.body.data.accessToken;
    console.log('✅ Admin login: OK (JWT token received)');

    const auditRes = await request(server)
      .get('/api/v1/admin/audit-logs')
      .set('Authorization', `Bearer ${adminToken}`);
    if (auditRes.status !== 200) {
      throw new Error(`Audit log check failed: ${JSON.stringify(auditRes.body)}`);
    }
    console.log(`✅ Admin audit logs accessible (Total entries: ${auditRes.body.data.pagination.total})`);

    console.log('\n--- 3. User Registration, Profile & Goals Flow ---');
    const uniqueEmail = `user_verify_${Date.now()}@calai.local`;
    const regRes = await request(server)
      .post('/api/v1/auth/register')
      .send({
        email: uniqueEmail,
        password: 'SecurePassword123!',
        fullName: 'Le Thi B',
      });
    if (regRes.status !== 201) {
      throw new Error(`Registration failed: ${JSON.stringify(regRes.body)}`);
    }
    const userToken = regRes.body.data.accessToken;
    console.log(`✅ Registered new user: ${uniqueEmail}`);

    const profileRes = await request(server)
      .patch('/api/v1/users/profile')
      .set('Authorization', `Bearer ${userToken}`)
      .send({ height: 165, weight: 58, age: 24, gender: 'FEMALE' });
    if (profileRes.status !== 200) {
      throw new Error(`Profile update failed: ${JSON.stringify(profileRes.body)}`);
    }
    console.log('✅ User profile updated (165cm, 58kg, 24yo FEMALE)');

    const goalsRes = await request(server)
      .put('/api/v1/users/goals')
      .set('Authorization', `Bearer ${userToken}`)
      .send({
        targetCalories: 1800,
        targetProtein: 120,
        targetCarbs: 200,
        targetFat: 55,
        goalType: 'WEIGHT_LOSS',
      });
    if (goalsRes.status !== 200) {
      throw new Error(`Goals update failed: ${JSON.stringify(goalsRes.body)}`);
    }
    console.log('✅ Daily nutrition goals set (1800 kcal, 120p, 200c, 55f)');

    console.log('\n--- 4. Vietnamese Food Catalog Search & Meal Tracking ---');
    const foodSearchRes = await request(server).get('/api/v1/foods/search?q=Cơm');
    if (foodSearchRes.status !== 200 || foodSearchRes.body.data.items.length === 0) {
      throw new Error('Food search returned no results');
    }
    const targetDish = foodSearchRes.body.data.items[0];
    console.log(`✅ Food catalog search: Found "${targetDish.name}" (${targetDish.calories} kcal/serving)`);

    const todayStr = '2026-10-05';
    const logMealRes = await request(server)
      .post('/api/v1/meals')
      .set('Authorization', `Bearer ${userToken}`)
      .send({
        mealType: 'LUNCH',
        mealDate: todayStr,
        items: [
          {
            foodId: targetDish.id,
            quantity: 1.5,
          },
        ],
      });
    if (logMealRes.status !== 201) {
      throw new Error(`Log meal failed: ${JSON.stringify(logMealRes.body)}`);
    }
    console.log('✅ Meal logged: 1.5 servings of ' + targetDish.name);

    const summaryRes = await request(server)
      .get(`/api/v1/meals/daily-summary?date=${todayStr}`)
      .set('Authorization', `Bearer ${userToken}`);
    if (summaryRes.status !== 200) {
      throw new Error(`Summary fetch failed: ${JSON.stringify(summaryRes.body)}`);
    }
    const summary = summaryRes.body.data;
    console.log(`✅ Daily Nutrition Summary:
   - Target Calories: ${summary.target.calories} kcal
   - Consumed: ${summary.consumed.calories} kcal
   - Remaining: ${summary.remaining.calories} kcal
   - Progress: ${summary.progressPercentage}%`);

    console.log('\n--- 5. Swagger OpenAPI Contract Verification ---');
    const paths = Object.keys(document.paths);
    console.log(`✅ Swagger Documentation: Generated ${paths.length} endpoints:`);
    paths.forEach((p) => console.log(`   - ${p}`));

    console.log('\n🎉 ====================================================');
    console.log('🎉 ALL SYSTEM E2E VERIFICATIONS PASSED WITH 100% SUCCESS!');
    console.log('🎉 ====================================================');
  } finally {
    await app.close();
  }
}

verifySystem().catch((err) => {
  console.error('\n❌ E2E System Verification Failed:', err);
  process.exit(1);
});
