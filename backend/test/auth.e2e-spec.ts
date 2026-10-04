import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../src/app.module';
import { PrismaService } from '../src/database/prisma.service';

describe('AuthController (e2e)', () => {
  let app: INestApplication;
  let prisma: PrismaService;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    app.setGlobalPrefix('api/v1');
    app.use((req: any, _res: any, next: any) => {
      if (
        req.url.startsWith('/api/') &&
        !req.url.startsWith('/api/v1/') &&
        !req.url.startsWith('/api/docs')
      ) {
        req.url = req.url.replace('/api/', '/api/v1/');
      }
      next();
    });
    app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
    await app.init();

    prisma = app.get<PrismaService>(PrismaService);
  });

  afterAll(async () => {
    await app.close();
  });

  it('/api/v1/auth/login (POST) successfully logs in seeded user', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/v1/auth/login')
      .send({
        email: 'user@calai.local',
        password: 'User123!',
      });

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.data.accessToken).toBeDefined();
    expect(res.body.data.token).toBeDefined();
    expect(res.body.data.role).toBe('user');
    expect(res.body.data.account.email).toBe('user@calai.local');
  });

  it('/api/auth/login (POST) works seamlessly via backward compatibility rewrite', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        email: 'user@calai.local',
        password: 'User123!',
      });

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.data.token).toBeDefined();
    expect(res.body.data.role).toBe('user');
  });

  it('/api/auth/validate (POST) validates token and returns valid status', async () => {
    // 1. Get token
    const loginRes = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        email: 'user@calai.local',
        password: 'User123!',
      });
    const token = loginRes.body.data.accessToken;

    // 2. Validate token
    const valRes = await request(app.getHttpServer())
      .post('/api/auth/validate')
      .set('Authorization', `Bearer ${token}`);

    expect(valRes.status).toBe(200);
    expect(valRes.body.success).toBe(true);
    expect(valRes.body.data.valid).toBe(true);
  });

  it('/api/v1/auth/login (POST) rejects invalid password with 401', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/v1/auth/login')
      .send({
        email: 'user@calai.local',
        password: 'WrongPassword!',
      });

    expect(res.status).toBe(401);
    expect(res.body.success).toBe(false);
  });

  it('/api/v1/auth/register (POST) creates new user and returns token', async () => {
    const uniqueEmail = `test_${Date.now()}@example.com`;
    const res = await request(app.getHttpServer())
      .post('/api/v1/auth/register')
      .send({
        email: uniqueEmail,
        password: 'TestPassword123!',
        fullName: 'Test Candidate',
      });

    expect(res.status).toBe(201);
    expect(res.body.success).toBe(true);
    expect(res.body.data.accessToken).toBeDefined();
    expect(res.body.data.account.email).toBe(uniqueEmail);

    // Verify /api/v1/auth/me with the issued token
    const token = res.body.data.accessToken;
    const meRes = await request(app.getHttpServer())
      .get('/api/v1/auth/me')
      .set('Authorization', `Bearer ${token}`);

    expect(meRes.status).toBe(200);
    expect(meRes.body.data.email).toBe(uniqueEmail);
  });

  it('/api/v1/auth/me (GET) returns 401 when token is missing', async () => {
    const res = await request(app.getHttpServer()).get('/api/v1/auth/me');
    expect(res.status).toBe(401);
    expect(res.body.success).toBe(false);
  });
});
