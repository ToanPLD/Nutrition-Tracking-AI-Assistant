import fs from 'fs';
import path from 'path';
import { hashPasswordSync } from '../shared/utils/hash';

export interface LocalDataSchema {
  accounts: any[];
  roles: any[];
  accountroles: any[];
  users: any[];
  usergoals: any[];
  foodcategories: any[];
  foods: any[];
  meals: any[];
  mealitems: any[];
  dailynutritionlogs: any[];
  mealschedules: any[];
  mealscheduleitems: any[];
  userfoodpreferences: any[];
  foodimages: any[];
  foodrecognitionresults: any[];
  chatsessions: any[];
  chatmessages: any[];
  adminauditlogs: any[];
}

const DB_FILE_PATH = path.resolve(process.cwd(), 'data', 'local-db.json');

class LocalStore {
  public data: LocalDataSchema = {
    accounts: [],
    roles: [],
    accountroles: [],
    users: [],
    usergoals: [],
    foodcategories: [],
    foods: [],
    meals: [],
    mealitems: [],
    dailynutritionlogs: [],
    mealschedules: [],
    mealscheduleitems: [],
    userfoodpreferences: [],
    foodimages: [],
    foodrecognitionresults: [],
    chatsessions: [],
    chatmessages: [],
    adminauditlogs: [],
  };

  private initialized = false;

  public init() {
    if (this.initialized) return;

    const dataDir = path.dirname(DB_FILE_PATH);
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }

    if (fs.existsSync(DB_FILE_PATH)) {
      try {
        const content = fs.readFileSync(DB_FILE_PATH, 'utf-8');
        this.data = JSON.parse(content);
        this.initialized = true;
        console.log(`📂 [Local DB] Loaded persisted database from ${DB_FILE_PATH}`);
        return;
      } catch (err) {
        console.warn('[Local DB] Error reading local-db.json, re-initializing...', err);
      }
    }

    this.seedInitialData();
    this.save();
    this.initialized = true;
    console.log('✨ [Local DB] Seeded fresh embedded database with Vietnamese foods & demo accounts!');
  }

  public save() {
    try {
      fs.writeFileSync(DB_FILE_PATH, JSON.stringify(this.data, null, 2), 'utf-8');
    } catch (err) {
      console.error('[Local DB] Failed to save local-db.json:', err);
    }
  }

  private seedInitialData() {
    // 1. Roles
    this.data.roles = [
      { role_id: 1, role_name: 'admin' },
      { role_id: 2, role_name: 'user' },
    ];

    // 2. Demo Accounts
    const adminPassHash = hashPasswordSync('Admin123!');
    const userPassHash = hashPasswordSync('User123!');

    this.data.accounts = [
      {
        account_id: 1,
        email: 'admin@calai.local',
        password_hash: adminPassHash,
        email_verified: 1,
        status: 'active',
        created_at: new Date().toISOString(),
      },
      {
        account_id: 2,
        email: 'user@calai.local',
        password_hash: userPassHash,
        email_verified: 1,
        status: 'active',
        created_at: new Date().toISOString(),
      },
    ];

    this.data.accountroles = [
      { account_id: 1, role_id: 1 },
      { account_id: 2, role_id: 2 },
    ];

    // 3. User Profiles
    this.data.users = [
      {
        user_id: 1,
        account_id: 1,
        full_name: 'CalAI Admin',
        gender: 'male',
        age: 30,
        height: 175,
        weight: 70,
        has_completed_setup: 1,
        created_at: new Date().toISOString(),
      },
      {
        user_id: 2,
        account_id: 2,
        full_name: 'Nguyễn Văn A',
        gender: 'male',
        age: 24,
        height: 172,
        weight: 65,
        has_completed_setup: 1,
        created_at: new Date().toISOString(),
      },
    ];

    // 4. User Goals
    this.data.usergoals = [
      {
        goal_id: 1,
        user_id: 1,
        target_calories: 2200,
        target_protein: 160,
        target_carbs: 220,
        target_fat: 70,
        target_weight: 70,
        goal_type: 'maintenance',
        activity_level: 'moderate',
      },
      {
        goal_id: 2,
        user_id: 2,
        target_calories: 2000,
        target_protein: 150,
        target_carbs: 200,
        target_fat: 65,
        target_weight: 63,
        goal_type: 'weight_loss',
        activity_level: 'moderate',
      },
    ];

    // 5. Seed Foods from CSV if available
    this.seedFoodsFromCsv();

    // 6. Seed Sample Meal Schedule
    const today = new Date().toISOString().split('T')[0];
    this.data.mealschedules = [
      {
        schedule_id: 1,
        user_id: 1,
        name: 'Thực đơn Eat Clean 7 Ngày',
        description: 'Chế độ ăn giàu đạm, rau củ quả tươi sạch giúp kiểm soát calo và giữ dáng hiệu quả.',
        start_date: today,
        end_date: today,
        color: '#10B981',
        target_calories: 1900,
        source: 'manual',
        is_published: 1,
        published_at: new Date().toISOString(),
        achieved: 0,
        created_at: new Date().toISOString(),
      },
    ];

    this.data.mealscheduleitems = [
      {
        item_id: 1,
        schedule_id: 1,
        day_offset: 0,
        meal_type: 'breakfast',
        name: 'Trứng luộc & Bánh mì đen',
        serving: '1 phần',
        calories: 320,
        protein: 18,
        carbs: 35,
        fat: 10,
        notes: 'Uống kèm 1 cốc nước ấm',
        sort_order: 1,
      },
      {
        item_id: 2,
        schedule_id: 1,
        day_offset: 0,
        meal_type: 'lunch',
        name: 'Ức gà áp chảo & Cơm gạo lứt',
        serving: '1 đĩa',
        calories: 550,
        protein: 45,
        carbs: 60,
        fat: 12,
        notes: 'Kèm salad rau xà lách sốt dầu giấm',
        sort_order: 2,
      },
      {
        item_id: 3,
        schedule_id: 1,
        day_offset: 0,
        meal_type: 'dinner',
        name: 'Cá hồi hấp & Bông cải xanh',
        serving: '1 phần',
        calories: 420,
        protein: 38,
        carbs: 15,
        fat: 18,
        notes: 'Ăn nhẹ trước 19h30',
        sort_order: 3,
      },
    ];
  }

  private seedFoodsFromCsv() {
    const csvPath = path.resolve(process.cwd(), 'data', 'dataFoodVietNam.csv');
    if (!fs.existsSync(csvPath)) {
      this.data.foods = [
        { food_id: 1, food_name: 'Cơm trắng', calories: 130, protein: 2.7, carbs: 28.2, fat: 0.3, serving_size: '100g' },
        { food_id: 2, food_name: 'Ức gà luộc', calories: 165, protein: 31.0, carbs: 0.0, fat: 3.6, serving_size: '100g' },
        { food_id: 3, food_name: 'Trứng gà', calories: 155, protein: 13.0, carbs: 1.1, fat: 11.0, serving_size: '1 quả' },
        { food_id: 4, food_name: 'Bánh phở', calories: 141, protein: 3.2, carbs: 32.1, fat: 0.0, serving_size: '100g' },
        { food_id: 5, food_name: 'Bánh mì', calories: 249, protein: 7.9, carbs: 52.6, fat: 0.8, serving_size: '1 ổ' },
      ];
      return;
    }

    try {
      const content = fs.readFileSync(csvPath, 'utf-8');
      const lines = content.split('\n');
      const categoriesMap = new Map<string, number>();
      let foodId = 1;
      let catId = 1;

      for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;

        // Parse CSV fields handling quoted commas
        const regex = /(?:,|\n|^)("(?:(?:"")*[^"]*)*"|[^",\n]*|(?:\n|$))/g;
        const matches: string[] = [];
        let match;
        while ((match = regex.exec(line)) !== null && matches.length < 18) {
          let val = match[1];
          if (val && val.startsWith('"') && val.endsWith('"')) {
            val = val.substring(1, val.length - 1).replace(/""/g, '"');
          }
          matches.push(val);
          if (regex.lastIndex >= line.length) break;
        }

        if (matches.length < 5) continue;

        const name = (matches[0] || '').trim();
        const cal = parseFloat((matches[1] || '0').replace(',', '.')) || 0;
        const pro = parseFloat((matches[2] || '0').replace(',', '.')) || 0;
        const fat = parseFloat((matches[3] || '0').replace(',', '.')) || 0;
        const carb = parseFloat((matches[4] || '0').replace(',', '.')) || 0;
        const catName = (matches[16] || 'Món ăn Việt Nam').replace(/"/g, '').trim();

        if (!categoriesMap.has(catName)) {
          categoriesMap.set(catName, catId);
          this.data.foodcategories.push({ category_id: catId, category_name: catName });
          catId++;
        }

        this.data.foods.push({
          food_id: foodId++,
          food_name: name,
          category_id: categoriesMap.get(catName) || null,
          calories: cal,
          protein: pro,
          carbs: carb,
          fat: fat,
          serving_size: '100g',
        });
      }
      console.log(`🍲 [Local DB] Seeded ${this.data.foods.length} authentic Vietnamese foods!`);
    } catch (e) {
      console.warn('[Local DB] Error parsing CSV, using default foods', e);
    }
  }

  // --- Helpers for ID generation ---
  public nextId(table: keyof LocalDataSchema, idKey: string): number {
    const list = this.data[table] as any[];
    if (list.length === 0) return 1;
    const max = Math.max(...list.map((item) => Number(item[idKey]) || 0));
    return max + 1;
  }
}

export const localStore = new LocalStore();
