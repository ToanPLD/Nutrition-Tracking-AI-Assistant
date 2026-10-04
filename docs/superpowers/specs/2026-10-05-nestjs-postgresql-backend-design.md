# Design Spec: Production-Grade NestJS & PostgreSQL Backend with Prisma ORM

- **Date**: 2026-10-05
- **Topic**: Enterprise-Standard Backend Architecture for CalAI with NestJS, PostgreSQL & Prisma
- **Status**: Approved by User / Ready for Implementation Planning

---

## 1. Context & Motivation

The CalAI Nutrition Tracking AI Assistant currently operates on an Express.js backend with raw MySQL queries and an in-memory/JSON fallback engine (`local-store.ts`). While functional for initial prototyping, it presents limitations for long-term scalability, type safety, and maintainability:
- Lack of strict schema migrations, leading to schema drift.
- Raw SQL queries without compile-time type-safety across relations.
- Inconsistent request validation and response payload shapes.
- Lack of self-documenting API contracts (Swagger/OpenAPI).

The objective is to re-architect the backend to meet industry enterprise standards (Clean Modular Architecture) while tailoring the Developer Experience (DX) for a solo developer working with a local PostgreSQL installation.

---

## 2. Core Architectural Decisions

1. **Framework**: **NestJS (TypeScript)**
   - Modular domain architecture (`@Module`).
   - Dependency Injection (DI) for testability and loose coupling.
   - Built-in validation pipe via `class-validator` and `class-transformer`.
2. **Database & ORM**: **PostgreSQL + Prisma ORM**
   - Strictly typed data layer auto-generated from `schema.prisma`.
   - Automated schema migrations via `npx prisma migrate dev`.
   - Visual database management via **Prisma Studio** (`npx prisma studio`).
3. **API Specification**: **RESTful API + Swagger / OpenAPI**
   - Interactive documentation accessible at `http://localhost:3000/api/docs`.
   - Strict DTO request/response schemas.
4. **Standard Cross-Cutting Concerns**:
   - **Global Response Transform Interceptor**: Consistent JSON response envelop:
     ```json
     {
       "success": true,
       "statusCode": 200,
       "data": { ... },
       "message": "Success message",
       "timestamp": "2026-10-05T00:00:00.000Z"
     }
     ```
   - **Global Exception Filter**: Intercepts HTTP and Prisma exceptions, formatting standardized error envelopes without leaking raw database stack traces.
   - **Security**: JWT-based authentication (Bearer token) with `@CurrentUser()` decorator, `bcryptjs` password hashing, and role-based access control (`RolesGuard`).

---

## 3. Directory Structure

The backend directory will be organized cleanly:

```
backend/
├── prisma/
│   ├── schema.prisma              # Database schema & relations
│   ├── migrations/                # Version-controlled SQL migration history
│   └── seed.ts                    # Automated seed script (180+ Vietnamese foods & sample accounts)
├── src/
│   ├── common/
│   │   ├── decorators/            # @CurrentUser(), @Roles(), @Public()
│   │   ├── filters/               # HttpExceptionFilter, PrismaExceptionFilter
│   │   ├── guards/                # JwtAuthGuard, RolesGuard
│   │   ├── interceptors/          # TransformResponseInterceptor, LoggingInterceptor
│   │   └── dto/                   # PaginationQueryDto, BaseResponseDto
│   ├── config/                    # ConfigModule loading and validating .env
│   ├── database/                  # PrismaModule & PrismaService with connection lifecycle
│   ├── modules/
│   │   ├── auth/                  # Register, login, me, JWT strategy
│   │   ├── users/                 # Profile, health goals, weight history, food preferences
│   │   ├── foods/                 # Food search, categories, nutrition lookup
│   │   ├── meals/                 # Meal logging, meal items, daily log calculation
│   │   ├── schedules/             # Meal plan schedules & items
│   │   ├── chat/                  # AI chat sessions, messages, CalAI/Ollama proxy
│   │   └── admin/                 # User moderation, audit logs, analytics
│   ├── app.module.ts              # Root NestJS module
│   └── main.ts                    # Bootstrap with Swagger, ValidationPipe, CORS, and Port
├── test/                          # Unit and E2E Jest test suites
├── tsconfig.json
└── package.json
```

---

## 4. Database Schema Design (Prisma / PostgreSQL)

### 4.1 Authentication & Accounts
- `Account`:
  - `id`: Int (PK autoincrement)
  - `email`: String (Unique)
  - `passwordHash`: String?
  - `emailVerified`: Boolean (default false)
  - `status`: Enum `AccountStatus` (`ACTIVE`, `INACTIVE`, `SUSPENDED`)
  - `role`: Enum `Role` (`USER`, `ADMIN`)
  - `createdAt`, `updatedAt`: DateTime
- `AdminAuditLog`:
  - `id`: Int (PK)
  - `adminAccountId`: Int? (FK to Account)
  - `action`: String
  - `targetType`: String
  - `targetId`: Int?
  - `detail`: String? (Text)
  - `createdAt`: DateTime

### 4.2 User Profile & Health Metrics
- `User`:
  - `id`: Int (PK)
  - `accountId`: Int (Unique, FK to Account with Cascade Delete)
  - `fullName`: String?
  - `gender`: Enum `Gender` (`MALE`, `FEMALE`, `OTHER`)
  - `age`: Int?
  - `height`: Float? (in cm)
  - `weight`: Float? (in kg)
  - `hasCompletedSetup`: Boolean (default false)
  - `createdAt`, `updatedAt`: DateTime
- `UserGoal`:
  - `id`: Int (PK)
  - `userId`: Int (FK to User)
  - `targetCalories`: Int
  - `targetProtein`: Int
  - `targetCarbs`: Int
  - `targetFat`: Int
  - `targetWeight`: Float?
  - `goalType`: Enum `GoalType` (`WEIGHT_LOSS`, `MUSCLE_GAIN`, `MAINTENANCE`, `GENERAL`)
  - `activityLevel`: String (default 'moderate')
- `WeightHistory`:
  - `id`: Int (PK)
  - `userId`: Int (FK to User)
  - `weight`: Float
  - `recordedAt`: DateTime
  - `note`: String?
- `UserFoodPreference`:
  - `id`: Int (PK)
  - `userId`: Int (FK to User)
  - `foodName`: String
  - `preferenceType`: Enum `PreferenceType` (`FAVORITE`, `AVOIDED`, `DISLIKED`, `ALLERGY`)
  - `mealSlot`: String?
  - `note`: String?

### 4.3 Foods & Meal Tracking
- `FoodCategory`:
  - `id`: Int (PK)
  - `name`: String (Unique)
- `Food`:
  - `id`: Int (PK)
  - `name`: String
  - `categoryId`: Int? (FK to FoodCategory)
  - `calories`: Float
  - `protein`: Float
  - `carbs`: Float
  - `fat`: Float
  - `fiber`: Float? (default 0)
  - `servingSize`: String?
  - `imagePath`: String?
- `Meal`:
  - `id`: Int (PK)
  - `userId`: Int (FK to User)
  - `mealType`: Enum `MealType` (`BREAKFAST`, `LUNCH`, `DINNER`, `SNACK`)
  - `mealDate`: DateTime (Date only)
  - `createdAt`: DateTime
- `MealItem`:
  - `id`: Int (PK)
  - `mealId`: Int (FK to Meal with Cascade Delete)
  - `foodId`: Int (FK to Food)
  - `quantity`: Float (default 1.0)
  - `calories`: Float
  - `protein`: Float
  - `carbs`: Float
  - `fat`: Float
- `DailyNutritionLog`:
  - `id`: Int (PK)
  - `userId`: Int (FK to User)
  - `date`: DateTime (Date only)
  - `totalCalories`: Float (default 0)
  - `totalProtein`: Float (default 0)
  - `totalCarbs`: Float (default 0)
  - `totalFat`: Float (default 0)
  - Unique Constraint: `[userId, date]`

### 4.4 Meal Schedules
- `MealSchedule`:
  - `id`: Int (PK)
  - `userId`: Int (FK to User)
  - `name`: String
  - `startDate`, `endDate`: DateTime (Date only)
  - `targetCalories`: Int?
  - `createdAt`: DateTime
- `MealScheduleItem`:
  - `id`: Int (PK)
  - `scheduleId`: Int (FK to MealSchedule with Cascade Delete)
  - `dayOffset`: Int
  - `mealType`: Enum `MealType`
  - `name`: String
  - `calories`, `protein`, `carbs`, `fat`: Float?

---

## 5. Module & Endpoint Specifications

### 5.1 Auth Module (`/api/v1/auth`)
- `POST /register`: Registers new account + user profile shell. Hashes password with bcrypt (salt rounds 10).
- `POST /login`: Validates credentials, issues JWT token with `{ accountId, role, email }`.
- `GET /me`: Returns profile and account details for currently authenticated user.
- `POST /refresh`: Refresh token mechanism.

### 5.2 Users Module (`/api/v1/users`)
- `GET /profile`: Get current user physical metrics.
- `PATCH /profile`: Update user metrics (updates `User` model, triggers baseline goals calculation if unset).
- `GET /goals` & `PUT /goals`: Read and update daily calorie and macronutrient targets.
- `GET /weight-history` & `POST /weight-history`: Track weight over time.
- `GET /preferences` & `POST /preferences` & `DELETE /preferences/:id`: Manage long-term food memory.

### 5.3 Foods & Meals Module (`/api/v1/foods`, `/api/v1/meals`)
- `GET /foods/search?q=...&category=...`: Search Vietnamese food database with pagination.
- `POST /meals`: Create meal with items; in a single atomic transaction (`prisma.$transaction`), saves meal items and recalculates `DailyNutritionLog` for the target date.
- `GET /meals/today`: Get all logged meals for current date grouped by meal type.
- `GET /meals/daily-summary?date=YYYY-MM-DD`: Compare daily intake vs `UserGoal` targets.
- `DELETE /meals/:id`: Remove meal and atomically recalculate daily summary.

### 5.4 Admin Module (`/api/v1/admin`)
- Guarded by `@Roles(Role.ADMIN)`.
- `GET /users`: List users with status.
- `PATCH /users/:id/status`: Ban/unban users.
- `GET /audit-logs`: Audit trail viewer.

---

## 6. Seed Data & Local DX Strategy

1. **Database Connection Configuration**:
   - `.env` configured with standard PostgreSQL URI:
     `DATABASE_URL="postgresql://postgres:password@localhost:5432/calai?schema=public"`
2. **Migration & Initialization**:
   - `npx prisma migrate dev --name init` applies the schema to PostgreSQL.
3. **Data Seeder (`prisma/seed.ts`)**:
   - Seeds Roles and default Admin (`admin@calai.local` / `Admin123!`) and User (`user@calai.local` / `User123!`).
   - Imports 180+ real Vietnamese food items with calories, protein, carbs, and fat from existing datasets into PostgreSQL.
4. **Developer Tools**:
   - `npx prisma studio`: Visual UI for viewing and tweaking tables.
   - Swagger at `http://localhost:3000/api/docs`: Self-contained interactive API testing.

---

## 7. Verification & Testing Strategy

1. **Prisma Schema & Migration Verification**:
   - Validate migration runs cleanly without errors against local PostgreSQL.
   - Run seed script and verify row counts (180+ foods, admin user, food categories).
2. **Unit Testing**:
   - Test `NutritionCalculator` and transaction logic for `DailyNutritionLog` recalculation.
   - Test `AuthService` password hashing and token generation.
3. **End-to-End (E2E) Flow Testing**:
   - Register -> Login -> Fetch Me.
   - Set Profile & Goals -> Add Breakfast Meal -> Query Daily Summary (verify totals match).
   - Chat message -> Mock/Agent fallback verification.
4. **Swagger Contract Verification**:
   - Verify all endpoints appear in `/api/docs` with correct status codes and schema models.
