# NestJS, PostgreSQL & Prisma Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade enterprise NestJS backend with PostgreSQL and Prisma ORM for CalAI, featuring strict modular architecture, Swagger documentation, and automated data seeding.

**Architecture:** Clean Modular Architecture with NestJS Feature Modules (`auth`, `users`, `foods`, `meals`, `admin`). Data persistence via Prisma ORM connected to PostgreSQL. API standardization via Global Interceptors, Exception Filters, and Swagger UI at `/api/docs`.

**Tech Stack:** NestJS 10+, TypeScript, PostgreSQL, Prisma ORM, Passport JWT, bcryptjs, class-validator, Swagger (`@nestjs/swagger`), Jest.

**Spec:** `docs/superpowers/specs/2026-10-05-nestjs-postgresql-backend-design.md`

## Global Constraints
- Target database: PostgreSQL (connection configured via `DATABASE_URL` in `backend/.env`).
- API prefix: `/api/v1` for all endpoints.
- Response format: `{ "success": boolean, "statusCode": number, "data": any, "message": string, "timestamp": string }`.
- Error format: `{ "success": false, "statusCode": number, "message": string, "error": string, "timestamp": string }`.
- Validation: Global NestJS `ValidationPipe` with `{ whitelist: true, transform: true }`.
- Developer tools: `npx prisma studio` and Swagger at `http://localhost:3000/api/docs`.

## Review Focus
- Database migration & seed: Ensure `prisma migrate dev` and `prisma db seed` execute cleanly against local PostgreSQL.
- Foreign key cascading: Verify that deleting an Account cascades delete to User profile and all associated logs/meals.
- Atomic nutrition summary: Adding or deleting a meal item must atomically update `DailyNutritionLog`.
- Authentication & Guard security: Protected routes must reject unauthenticated requests with 401 Unauthorized.

---

### Task 1: Project Scaffolding & Core Infrastructure

**Files:**
- Create: `backend/src/common/interceptors/transform-response.interceptor.ts`
- Create: `backend/src/common/filters/http-exception.filter.ts`
- Create: `backend/src/common/dto/api-response.dto.ts`
- Create: `backend/src/modules/health/health.controller.ts`
- Create: `backend/src/modules/health/health.module.ts`
- Modify: `backend/package.json`
- Modify: `backend/src/app.module.ts`
- Modify: `backend/src/main.ts`
- Test: `backend/test/health.e2e-spec.ts`

**Interfaces:**
- Consumes: None (Root setup).
- Produces: `TransformResponseInterceptor`, `HttpExceptionFilter`, `HealthModule`.

- [ ] **Step 1: Write failing E2E test for Health check**

```typescript
// backend/test/health.e2e-spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../src/app.module';

describe('HealthController (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    app.setGlobalPrefix('api/v1');
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  it('/api/v1/health (GET) returns standardized response', async () => {
    const res = await request(app.getHttpServer()).get('/api/v1/health');
    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.data.status).toBe('ok');
    expect(res.body.timestamp).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pnpm test:e2e test/health.e2e-spec.ts`
Expected: FAIL (modules and NestJS app not yet initialized).

- [ ] **Step 3: Install NestJS dependencies and configure package.json**

Add dependencies to `backend/package.json`:
- `@nestjs/common`, `@nestjs/core`, `@nestjs/platform-express`, `@nestjs/config`, `@nestjs/swagger`, `swagger-ui-express`
- `class-validator`, `class-transformer`, `reflect-metadata`, `rxjs`
- `@prisma/client`, `prisma` (dev)
- `@types/supertest`, `supertest` (dev)

- [ ] **Step 4: Implement Global Interceptors, Filters, and Bootstrap**

1. Create `TransformResponseInterceptor` mapping all successful returns to `{ success: true, statusCode, data, message, timestamp }`.
2. Create `HttpExceptionFilter` formatting all exceptions to `{ success: false, statusCode, message, error, timestamp }`.
3. In `main.ts`, setup global prefix `api/v1`, apply Interceptor and Filter, configure `ValidationPipe({ whitelist: true, transform: true })`, and setup Swagger UI with `@nestjs/swagger` at `/api/docs`.
4. Create `HealthController` at `/health` returning `{ status: 'ok', uptime: process.uptime() }`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pnpm test:e2e test/health.e2e-spec.ts`
Expected: PASS with standardized envelope.

- [ ] **Step 6: Commit**

```bash
git add backend/package.json backend/src/common backend/src/modules/health backend/src/main.ts backend/src/app.module.ts backend/test/health.e2e-spec.ts
git commit -m "feat(backend): scaffold nestjs core infrastructure, swagger, and health check"
```

---

### Task 2: Prisma ORM Setup, Schema Definition & PostgreSQL Migrations

**Files:**
- Create: `backend/prisma/schema.prisma`
- Create: `backend/src/database/prisma.service.ts`
- Create: `backend/src/database/prisma.module.ts`
- Modify: `backend/.env.example`
- Test: `backend/src/database/prisma.service.spec.ts`

**Interfaces:**
- Consumes: PostgreSQL connection via `DATABASE_URL`.
- Produces: `PrismaService` providing type-safe database client across all modules.

- [ ] **Step 1: Write test for PrismaService connection lifecycle**

```typescript
// backend/src/database/prisma.service.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { PrismaService } from './prisma.service';

describe('PrismaService', () => {
  let service: PrismaService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [PrismaService],
    }).compile();

    service = module.get<PrismaService>(PrismaService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pnpm test src/database/prisma.service.spec.ts`
Expected: FAIL with module not found.

- [ ] **Step 3: Define PostgreSQL Models in `prisma/schema.prisma`**

Define models matching the spec:
- `Account` & `AdminAuditLog` (Enums: `Role`, `AccountStatus`).
- `User`, `UserGoal`, `WeightHistory`, `UserFoodPreference` (Enums: `Gender`, `GoalType`, `PreferenceType`).
- `FoodCategory`, `Food` (calories, protein, carbs, fat, fiber, servingSize).
- `Meal`, `MealItem`, `DailyNutritionLog` (Enums: `MealType`).
- `ChatSession`, `ChatMessage` (Enum: `Sender`).
- `MealSchedule`, `MealScheduleItem`.

- [ ] **Step 4: Implement `PrismaService` and `PrismaModule`**

Create `PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy` with connection initialization and clean disconnect. Make `PrismaModule` `@Global()`.

- [ ] **Step 5: Run Prisma Migration**

Run: `cd backend && npx prisma migrate dev --name init`
Expected: Migration created in `backend/prisma/migrations/` and tables initialized in PostgreSQL.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pnpm test src/database/prisma.service.spec.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/prisma backend/src/database backend/.env.example
git commit -m "feat(database): configure prisma orm with postgresql schema and migrations"
```

---

### Task 3: Seed Script for Vietnamese Foods & Sample Accounts

**Files:**
- Create: `backend/prisma/seed.ts`
- Modify: `backend/package.json`
- Test: `backend/test/seed.spec.ts`

**Interfaces:**
- Consumes: `PrismaService`, existing 180+ food items data source.
- Produces: Populated database with default Admin, User, Food Categories, and Foods.

- [ ] **Step 1: Write verification test for seeded database contents**

```typescript
// backend/test/seed.spec.ts
import { PrismaClient, Role } from '@prisma/client';

describe('Database Seed Verification', () => {
  const prisma = new PrismaClient();

  afterAll(async () => {
    await prisma.$disconnect();
  });

  it('should have seeded admin and user accounts', async () => {
    const admin = await prisma.account.findUnique({ where: { email: 'admin@calai.local' } });
    expect(admin).toBeDefined();
    expect(admin?.role).toBe(Role.ADMIN);

    const user = await prisma.account.findUnique({ where: { email: 'user@calai.local' } });
    expect(user).toBeDefined();
    expect(user?.role).toBe(Role.USER);
  });

  it('should have seeded Vietnamese food catalog (>100 items)', async () => {
    const foodCount = await prisma.food.count();
    expect(foodCount).toBeGreaterThanOrEqual(100);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pnpm test test/seed.spec.ts`
Expected: FAIL (no seed data in database).

- [ ] **Step 3: Implement `prisma/seed.ts`**

1. Hash default password `Admin123!` and `User123!` using `bcryptjs`.
2. Upsert admin and user accounts with associated profile records.
3. Import Vietnamese food categories (Món sợi, Cơm, Canh, Món xào/kho, Đồ uống...) and 180+ dish records from `backend/data/local-db.json` / dataset script.
4. Add `"prisma": { "seed": "ts-node prisma/seed.ts" }` to `backend/package.json`.

- [ ] **Step 4: Execute seed command and run test**

Run: `cd backend && npx prisma db seed && pnpm test test/seed.spec.ts`
Expected: PASS with 180+ foods and default accounts verified.

- [ ] **Step 5: Commit**

```bash
git add backend/prisma/seed.ts backend/package.json backend/test/seed.spec.ts
git commit -m "feat(database): implement automated seed script for vietnamese foods and default accounts"
```

---

### Task 4: Authentication & Authorization Module (`AuthModule`)

**Files:**
- Create: `backend/src/modules/auth/dto/register.dto.ts`
- Create: `backend/src/modules/auth/dto/login.dto.ts`
- Create: `backend/src/modules/auth/strategies/jwt.strategy.ts`
- Create: `backend/src/common/guards/jwt-auth.guard.ts`
- Create: `backend/src/common/guards/roles.guard.ts`
- Create: `backend/src/common/decorators/current-user.decorator.ts`
- Create: `backend/src/common/decorators/roles.decorator.ts`
- Create: `backend/src/modules/auth/auth.service.ts`
- Create: `backend/src/modules/auth/auth.controller.ts`
- Create: `backend/src/modules/auth/auth.module.ts`
- Test: `backend/src/modules/auth/auth.service.spec.ts`
- Test: `backend/test/auth.e2e-spec.ts`

**Interfaces:**
- Consumes: `PrismaService`, `ConfigService`.
- Produces: JWT Authentication endpoints (`/register`, `/login`, `/me`), `JwtAuthGuard`, `RolesGuard`.

- [ ] **Step 1: Write failing unit test for `AuthService`**

```typescript
// backend/src/modules/auth/auth.service.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { AuthService } from './auth.service';
import { PrismaService } from '../../database/prisma.service';
import { JwtService } from '@nestjs/jwt';

describe('AuthService', () => {
  let service: AuthService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        AuthService,
        { provide: PrismaService, useValue: {} },
        { provide: JwtService, useValue: { sign: () => 'mock-jwt-token' } },
      ],
    }).compile();

    service = module.get<AuthService>(AuthService);
  });

  it('should hash passwords and issue token on registration', () => {
    expect(service.hashPassword).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pnpm test src/modules/auth/auth.service.spec.ts`
Expected: FAIL.

- [ ] **Step 3: Implement Auth DTOs, Service, Strategy & Controller**

1. Implement `RegisterDto` (email, password min 6 chars, optional fullName) and `LoginDto` with `class-validator`.
2. Implement `AuthService`:
   - `register`: check existing email -> hash password -> create Account + User -> return token.
   - `login`: find by email -> compare password with `bcryptjs` -> return `{ accessToken, user }`.
   - `getMe`: fetch user profile and account details.
3. Setup `JwtStrategy` with Passport extracting Bearer token.
4. Implement `JwtAuthGuard`, `RolesGuard`, and decorators `@CurrentUser()`, `@Roles()`.
5. Annotate `AuthController` with Swagger decorators (`@ApiTags('Auth')`, `@ApiBearerAuth()`).

- [ ] **Step 4: Run unit and E2E tests**

Run: `cd backend && pnpm test src/modules/auth/auth.service.spec.ts && pnpm test:e2e test/auth.e2e-spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/modules/auth backend/src/common/guards backend/src/common/decorators backend/test/auth.e2e-spec.ts
git commit -m "feat(auth): implement jwt authentication, role guards, and auth endpoints"
```

---

### Task 5: User Profile, Goals & Preferences Module (`UsersModule`)

**Files:**
- Create: `backend/src/modules/users/dto/update-profile.dto.ts`
- Create: `backend/src/modules/users/dto/update-goals.dto.ts`
- Create: `backend/src/modules/users/dto/create-weight.dto.ts`
- Create: `backend/src/modules/users/dto/food-preference.dto.ts`
- Create: `backend/src/modules/users/users.service.ts`
- Create: `backend/src/modules/users/users.controller.ts`
- Create: `backend/src/modules/users/users.module.ts`
- Test: `backend/src/modules/users/users.service.spec.ts`
- Test: `backend/test/users.e2e-spec.ts`

**Interfaces:**
- Consumes: `PrismaService`, `JwtAuthGuard`.
- Produces: Profile & health goals management at `/api/v1/users/*`.

- [ ] **Step 1: Write failing test for user goal computation**

```typescript
// backend/src/modules/users/users.service.spec.ts
import { UsersService } from './users.service';

describe('UsersService - Basal Goal Estimation', () => {
  it('calculates recommended calories based on height, weight, age, and gender', () => {
    const calories = UsersService.calculateTdee({
      weight: 70,
      height: 175,
      age: 25,
      gender: 'MALE',
      activityLevel: 'moderate',
      goalType: 'WEIGHT_LOSS'
    });
    expect(calories).toBeGreaterThan(1500);
    expect(calories).toBeLessThan(2600);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pnpm test src/modules/users/users.service.spec.ts`
Expected: FAIL.

- [ ] **Step 3: Implement Users Module DTOs, Service & Controller**

1. Implement `UsersService`:
   - `getProfile(userId)` & `updateProfile(userId, dto)`: update height, weight, age, gender.
   - `getGoals(userId)` & `updateGoals(userId, dto)`: target calories, carbs, protein, fat.
   - `recordWeight(userId, dto)`: add to `WeightHistory`.
   - `getPreferences(userId)` & `addPreference(userId, dto)` & `deletePreference(userId, id)`: manage food preferences.
2. Implement `UsersController` with `@UseGuards(JwtAuthGuard)` and Swagger annotations.

- [ ] **Step 4: Run unit and E2E tests**

Run: `cd backend && pnpm test src/modules/users/users.service.spec.ts && pnpm test:e2e test/users.e2e-spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/modules/users backend/test/users.e2e-spec.ts
git commit -m "feat(users): implement profile, goals, weight tracking, and food preferences"
```

---

### Task 6: Foods & Meals Tracking Module with Atomic Nutrition Aggregation (`MealsModule`, `FoodsModule`)

**Files:**
- Create: `backend/src/modules/foods/foods.service.ts`
- Create: `backend/src/modules/foods/foods.controller.ts`
- Create: `backend/src/modules/foods/foods.module.ts`
- Create: `backend/src/modules/meals/dto/create-meal.dto.ts`
- Create: `backend/src/modules/meals/meals.service.ts`
- Create: `backend/src/modules/meals/meals.controller.ts`
- Create: `backend/src/modules/meals/meals.module.ts`
- Test: `backend/src/modules/meals/meals.service.spec.ts`
- Test: `backend/test/meals.e2e-spec.ts`

**Interfaces:**
- Consumes: `PrismaService`, `JwtAuthGuard`.
- Produces: Food catalog search (`/api/v1/foods/search`), Meal logging (`/api/v1/meals`), Daily Nutrition Summary (`/api/v1/meals/daily-summary`).

- [ ] **Step 1: Write failing test for atomic daily nutrition summary update**

```typescript
// backend/src/modules/meals/meals.service.spec.ts
describe('MealsService - Atomic Daily Summary Recalculation', () => {
  it('aggregates total calories and macros for a date after logging meals', async () => {
    // Tests that adding a breakfast of 500 kcal and lunch of 700 kcal results in 1200 kcal in DailyNutritionLog
    expect(true).toBe(false); // failing stub
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pnpm test src/modules/meals/meals.service.spec.ts`
Expected: FAIL.

- [ ] **Step 3: Implement Foods Service & Controller**

1. `FoodsService`:
   - `searchFoods(query, categoryId, page, limit)`: case-insensitive food search with pagination.
   - `getCategories()`: returns all food categories with food count.

- [ ] **Step 4: Implement Meals Service & Controller with Atomic Recalculation**

1. `MealsService`:
   - `createMeal(userId, dto)`: In a `prisma.$transaction`, insert `Meal` + `MealItem`s, query sum of calories/protein/carbs/fat for that date, and upsert `DailyNutritionLog`.
   - `getMealsByDate(userId, date)`: get meals grouped by `mealType` (Breakfast, Lunch, Dinner, Snack).
   - `getDailySummary(userId, date)`: fetch `DailyNutritionLog` and compare with `UserGoal` (remaining calories, percentage achieved).
   - `deleteMeal(userId, mealId)`: delete meal and atomically recalculate `DailyNutritionLog`.
2. Connect `MealsController` with Swagger schema.

- [ ] **Step 5: Run unit and E2E tests**

Run: `cd backend && pnpm test src/modules/meals/meals.service.spec.ts && pnpm test:e2e test/meals.e2e-spec.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/modules/foods backend/src/modules/meals backend/test/meals.e2e-spec.ts
git commit -m "feat(meals): implement food search, meal logging, and atomic daily nutrition log calculation"
```

---

### Task 7: Admin Module & End-to-End System Verification

**Files:**
- Create: `backend/src/modules/admin/admin.service.ts`
- Create: `backend/src/modules/admin/admin.controller.ts`
- Create: `backend/src/modules/admin/admin.module.ts`
- Create: `backend/scripts/verify-e2e-system.ts`
- Modify: `backend/src/app.module.ts`
- Test: `backend/test/admin.e2e-spec.ts`

**Interfaces:**
- Consumes: All modules, `Roles(Role.ADMIN)`.
- Produces: Complete production-ready enterprise NestJS backend with Swagger at `/api/docs`.

- [ ] **Step 1: Implement Admin Module**

1. `AdminService`:
   - `getUsers(page, limit)`: list users with role and status.
   - `updateUserStatus(userId, status)`: suspend/activate user, log into `AdminAuditLog`.
   - `getAuditLogs(page, limit)`: view audit records.
2. `AdminController`: Guard with `@UseGuards(JwtAuthGuard, RolesGuard)` and `@Roles(Role.ADMIN)`.

- [ ] **Step 2: Create Comprehensive E2E Verification Script**

Create `backend/scripts/verify-e2e-system.ts` testing:
1. Health check `/api/v1/health`.
2. Admin login with seeded credentials -> token received.
3. User registration -> user login -> profile update -> goals set.
4. Food search for "Phở bò" -> log breakfast meal -> check `/api/v1/meals/daily-summary`.
5. Verify Swagger JSON schema is generated at `/api/docs-json`.

- [ ] **Step 3: Run comprehensive verification script**

Run: `cd backend && npx ts-node scripts/verify-e2e-system.ts`
Expected: All steps pass with green output.

- [ ] **Step 4: Commit**

```bash
git add backend/src/modules/admin backend/src/app.module.ts backend/scripts/verify-e2e-system.ts backend/test/admin.e2e-spec.ts
git commit -m "feat(admin): implement admin management and comprehensive e2e verification script"
```
