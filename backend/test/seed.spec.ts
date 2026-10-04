import { PrismaClient, Role } from '@prisma/client';

describe('Database Seed Verification', () => {
  const prisma = new PrismaClient();

  afterAll(async () => {
    await prisma.$disconnect();
  });

  it('should have seeded admin and user accounts', async () => {
    const admin = await prisma.account.findUnique({
      where: { email: 'admin@calai.local' },
    });
    expect(admin).toBeDefined();
    expect(admin?.role).toBe(Role.ADMIN);

    const user = await prisma.account.findUnique({
      where: { email: 'user@calai.local' },
    });
    expect(user).toBeDefined();
    expect(user?.role).toBe(Role.USER);
  });

  it('should have seeded Vietnamese food catalog (>100 items)', async () => {
    const foodCount = await prisma.food.count();
    expect(foodCount).toBeGreaterThanOrEqual(100);
  });
});
