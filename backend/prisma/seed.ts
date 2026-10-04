import { PrismaClient, Role, AccountStatus, Gender } from '@prisma/client';
import * as bcrypt from 'bcryptjs';
import * as fs from 'fs';
import * as path from 'path';

const prisma = new PrismaClient();

function parseVnNumber(raw: string | undefined): number {
  if (!raw || raw.trim() === '' || raw.trim() === '0') return 0;
  const cleaned = raw.trim().replace(/[^0-9,.-]/g, '').replace(',', '.');
  const n = parseFloat(cleaned);
  return isNaN(n) ? 0 : n;
}

function parseCsvLine(line: string): string[] {
  const fields: string[] = [];
  let inQuote = false;
  let current = '';
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuote = !inQuote;
    } else if (ch === ',' && !inQuote) {
      fields.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  fields.push(current);
  return fields;
}

async function main() {
  console.log('🌱 [Seeder] Starting automated database seed...');

  // 1. Seed Accounts
  const adminPasswordHash = await bcrypt.hash('Admin123!', 10);
  const userPasswordHash = await bcrypt.hash('User123!', 10);

  const adminAccount = await prisma.account.upsert({
    where: { email: 'admin@calai.local' },
    update: { passwordHash: adminPasswordHash, role: Role.ADMIN },
    create: {
      email: 'admin@calai.local',
      passwordHash: adminPasswordHash,
      role: Role.ADMIN,
      status: AccountStatus.ACTIVE,
      emailVerified: true,
      user: {
        create: {
          fullName: 'CalAI Administrator',
          gender: Gender.OTHER,
          hasCompletedSetup: true,
        },
      },
    },
  });
  console.log(`✅ Seeded Admin: ${adminAccount.email}`);

  const sampleUser = await prisma.account.upsert({
    where: { email: 'user@calai.local' },
    update: { passwordHash: userPasswordHash, role: Role.USER },
    create: {
      email: 'user@calai.local',
      passwordHash: userPasswordHash,
      role: Role.USER,
      status: AccountStatus.ACTIVE,
      emailVerified: true,
      user: {
        create: {
          fullName: 'Nguyen Van A',
          gender: Gender.MALE,
          age: 26,
          height: 175,
          weight: 70,
          hasCompletedSetup: true,
          goals: {
            create: {
              targetCalories: 2100,
              targetProtein: 140,
              targetCarbs: 230,
              targetFat: 65,
              targetWeight: 68,
              goalType: 'WEIGHT_LOSS',
              activityLevel: 'moderate',
            },
          },
        },
      },
    },
  });
  console.log(`✅ Seeded Sample User: ${sampleUser.email}`);

  // 2. Seed Vietnamese Foods Catalog
  const csvPath = path.join(__dirname, '..', 'data', 'dataFoodVietNam.csv');
  if (fs.existsSync(csvPath)) {
    console.log(`📖 Reading food catalog from ${csvPath}...`);
    const content = fs.readFileSync(csvPath, 'utf-8');
    const lines = content.split(/\r?\n/).filter((l) => l.trim().length > 0);

    const categoryCache = new Map<string, number>();

    let importedCount = 0;
    // Skip header line
    for (let i = 1; i < lines.length; i++) {
      const f = parseCsvLine(lines[i]);
      if (f.length < 17) continue;

      const rawName = f[0].trim();
      if (!rawName) continue;

      const categoryName = f[16]?.trim() || 'Thực phẩm khác';

      let categoryId = categoryCache.get(categoryName);
      if (!categoryId) {
        const cat = await prisma.foodCategory.upsert({
          where: { name: categoryName },
          update: {},
          create: { name: categoryName },
        });
        categoryId = cat.id;
        categoryCache.set(categoryName, categoryId);
      }

      const calories = parseVnNumber(f[1]);
      const protein = parseVnNumber(f[2]);
      const fat = parseVnNumber(f[3]);
      const carbs = parseVnNumber(f[4]);
      const fiber = parseVnNumber(f[5]);

      await prisma.food.create({
        data: {
          name: rawName,
          categoryId,
          calories,
          protein,
          carbs,
          fat,
          fiber,
          servingSize: '100g',
        },
      });
      importedCount++;
    }
    console.log(`✅ Seeded ${importedCount} Vietnamese food catalog items across ${categoryCache.size} categories!`);
  } else {
    console.warn(`⚠️ CSV file not found at ${csvPath}`);
  }

  console.log('✨ [Seeder] Database seeding completed successfully!');
}

main()
  .catch((e) => {
    console.error('Seeding error:', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
