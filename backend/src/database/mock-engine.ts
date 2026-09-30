import { localStore, LocalDataSchema } from './local-store';

export const executeMockSql = (sql: string, params: any[] = []): { rows?: any[]; result?: any } => {
  localStore.init();

  const cleanSql = sql.trim().replace(/\s+/g, ' ');
  const upperSql = cleanSql.toUpperCase();

  // ─── SHOW TABLES ───
  if (upperSql.startsWith('SHOW TABLES')) {
    return { rows: [{ 'Tables_in_calai': 'accounts' }] };
  }

  // ─── CREATE TABLE / INSERT IGNORE / DELIMITER ───
  if (upperSql.startsWith('CREATE TABLE') || upperSql.startsWith('INSERT IGNORE')) {
    return { result: { insertId: 0, affectedRows: 0 } };
  }

  // ─── 1. SELECT QUERIES ───
  if (upperSql.startsWith('SELECT')) {
    // 1.1 Accounts lookup
    if (upperSql.includes('FROM ACCOUNTS')) {
      if (upperSql.includes('COUNT(*)')) {
        const activeCount = localStore.data.accounts.filter((a) => a.status !== 'suspended').length;
        return { rows: [{ total: activeCount }] };
      }

      if (upperSql.includes('LOWER(A.EMAIL) = LOWER(?)') || upperSql.includes('EMAIL = ?')) {
        const email = String(params[0] || '').toLowerCase();
        const acc = localStore.data.accounts.find((a) => a.email.toLowerCase() === email);
        if (!acc) return { rows: [] };

        const roleMapping = localStore.data.accountroles.find((ar) => ar.account_id === acc.account_id);
        const role = localStore.data.roles.find((r) => r.role_id === (roleMapping?.role_id || 2));
        const user = localStore.data.users.find((u) => u.account_id === acc.account_id);

        return {
          rows: [
            {
              account_id: acc.account_id,
              email: acc.email,
              password_hash: acc.password_hash,
              email_verified: acc.email_verified,
              status: acc.status,
              role_name: role ? role.role_name : 'user',
              user_id: user ? user.user_id : acc.account_id,
              full_name: user ? user.full_name : 'User',
            },
          ],
        };
      }

      if (upperSql.includes('A.ACCOUNT_ID = ?') || upperSql.includes('ACCOUNT_ID = ?')) {
        const accId = Number(params[0]);
        const acc = localStore.data.accounts.find((a) => a.account_id === accId);
        if (!acc) return { rows: [] };

        const roleMapping = localStore.data.accountroles.find((ar) => ar.account_id === acc.account_id);
        const role = localStore.data.roles.find((r) => r.role_id === (roleMapping?.role_id || 2));
        const user = localStore.data.users.find((u) => u.account_id === acc.account_id);

        return {
          rows: [
            {
              account_id: acc.account_id,
              email: acc.email,
              password_hash: acc.password_hash,
              email_verified: acc.email_verified,
              status: acc.status,
              role_name: role ? role.role_name : 'user',
              user_id: user ? user.user_id : acc.account_id,
              full_name: user ? user.full_name : 'User',
              created_at: acc.created_at,
            },
          ],
        };
      }

      // List all accounts with roles
      const list = localStore.data.accounts.map((a) => {
        const ar = localStore.data.accountroles.find((r) => r.account_id === a.account_id);
        const role = localStore.data.roles.find((r) => r.role_id === (ar?.role_id || 2));
        const user = localStore.data.users.find((u) => u.account_id === a.account_id);
        return {
          account_id: a.account_id,
          email: a.email,
          status: a.status,
          role_name: role ? role.role_name : 'user',
          name: user ? user.full_name : 'User',
          created_at: a.created_at,
        };
      });
      return { rows: list };
    }

    // 1.2 Roles lookup
    if (upperSql.includes('FROM ROLES')) {
      if (params[0]) {
        const roleName = String(params[0]).toLowerCase();
        const role = localStore.data.roles.find((r) => r.role_name.toLowerCase() === roleName);
        return { rows: role ? [role] : [] };
      }
      return { rows: localStore.data.roles };
    }

    // 1.3 Users lookup
    if (upperSql.includes('FROM USERS')) {
      if (upperSql.includes('COUNT(*)')) {
        return { rows: [{ total: localStore.data.users.length }] };
      }

      if (upperSql.includes('ACCOUNT_ID = ?')) {
        const accId = Number(params[0]);
        const user = localStore.data.users.find((u) => u.account_id === accId);
        return { rows: user ? [user] : [] };
      }

      if (upperSql.includes('USER_ID = ?') || upperSql.includes('U.USER_ID = ?')) {
        const userId = Number(params[0]);
        const user = localStore.data.users.find((u) => u.user_id === userId);
        if (!user) return { rows: [] };
        const acc = localStore.data.accounts.find((a) => a.account_id === user.account_id);
        const ar = localStore.data.accountroles.find((r) => r.account_id === user.account_id);
        const role = localStore.data.roles.find((r) => r.role_id === (ar?.role_id || 2));

        return {
          rows: [
            {
              ...user,
              name: user.full_name,
              email: acc?.email || '',
              status: acc?.status || 'active',
              role_name: role?.role_name || 'user',
            },
          ],
        };
      }

      // List all users
      const allUsers = localStore.data.users.map((u) => {
        const acc = localStore.data.accounts.find((a) => a.account_id === u.account_id);
        const ar = localStore.data.accountroles.find((r) => r.account_id === u.account_id);
        const role = localStore.data.roles.find((r) => r.role_id === (ar?.role_id || 2));
        return {
          ...u,
          name: u.full_name,
          email: acc?.email || '',
          status: acc?.status || 'active',
          role_name: role?.role_name || 'user',
        };
      });
      return { rows: allUsers };
    }

    // 1.4 Goals
    if (upperSql.includes('FROM USERGOALS')) {
      const userId = Number(params[0]);
      const goal = localStore.data.usergoals.find((g) => g.user_id === userId);
      if (goal) {
        return {
          rows: [
            {
              goal_id: goal.goal_id,
              user_id: goal.user_id,
              dailyCalories: goal.target_calories,
              protein: goal.target_protein,
              carbs: goal.target_carbs,
              fats: goal.target_fat,
              targetWeight: goal.target_weight,
              goal: goal.goal_type,
              activityLevel: goal.activity_level,
            },
          ],
        };
      }
      return { rows: [] };
    }

    // 1.5 Foods & Categories
    if (upperSql.includes('FROM FOODCATEGORIES')) {
      return { rows: localStore.data.foodcategories };
    }

    if (upperSql.includes('FROM FOODS')) {
      if (upperSql.includes('COUNT(*)')) {
        return { rows: [{ total: localStore.data.foods.length }] };
      }

      if (upperSql.includes('LOWER(FOOD_NAME) = LOWER(?)')) {
        const name = String(params[0] || '').toLowerCase();
        const food = localStore.data.foods.find((f) => f.food_name.toLowerCase() === name);
        return { rows: food ? [food] : [] };
      }

      if (upperSql.includes('FOOD_ID = ?') || upperSql.includes('F.FOOD_ID = ?')) {
        const foodId = Number(params[0]);
        const food = localStore.data.foods.find((f) => f.food_id === foodId);
        return { rows: food ? [food] : [] };
      }

      let filtered = [...localStore.data.foods];
      // Search term filtering
      const searchTerm = params.find((p) => typeof p === 'string' && p.startsWith('%') && p.endsWith('%'));
      if (searchTerm) {
        const keyword = searchTerm.replace(/%/g, '').toLowerCase();
        filtered = filtered.filter((f) => f.food_name.toLowerCase().includes(keyword));
      }

      const limit = Number(params[params.length - 1]) || 50;
      return { rows: filtered.slice(0, limit) };
    }

    // 1.6 Meals & Meal items
    if (upperSql.includes('FROM MEALS')) {
      if (upperSql.includes('COUNT(*)')) {
        return { rows: [{ total: localStore.data.meals.length }] };
      }

      if (upperSql.includes('COUNT(DISTINCT USER_ID)')) {
        const usersToday = new Set(localStore.data.meals.map((m) => m.user_id));
        return { rows: [{ total: usersToday.size }] };
      }

      if (upperSql.includes('GROUP BY M.MEAL_DATE')) {
        // Meal history
        const userId = Number(params[0]);
        const userMeals = localStore.data.meals.filter((m) => m.user_id === userId);
        const map = new Map<string, any>();

        for (const m of userMeals) {
          if (!map.has(m.meal_date)) {
            map.set(m.meal_date, {
              meal_date: m.meal_date,
              total_meals: 0,
              total_calories: 0,
              total_protein: 0,
              total_carbs: 0,
              total_fats: 0,
            });
          }
          const rec = map.get(m.meal_date);
          rec.total_meals++;
          const items = localStore.data.mealitems.filter((mi) => mi.meal_id === m.meal_id);
          for (const it of items) {
            rec.total_calories += Number(it.calories || 0);
            rec.total_protein += Number(it.protein || 0);
            rec.total_carbs += Number(it.carbs || 0);
            rec.total_fats += Number(it.fat || 0);
          }
        }
        return { rows: Array.from(map.values()) };
      }

      // Today's summary or list
      const userId = Number(params[0]);
      const date = String(params[1] || new Date().toISOString().split('T')[0]);

      if (upperSql.includes('COALESCE(SUM(MI.CALORIES)')) {
        // Nutrition totals
        const userMeals = localStore.data.meals.filter((m) => m.user_id === userId && m.meal_date === date);
        let c = 0, p = 0, cb = 0, f = 0;
        for (const m of userMeals) {
          const items = localStore.data.mealitems.filter((mi) => mi.meal_id === m.meal_id);
          for (const it of items) {
            c += Number(it.calories || 0);
            p += Number(it.protein || 0);
            cb += Number(it.carbs || 0);
            f += Number(it.fat || 0);
          }
        }
        return { rows: [{ calories: c, protein: p, carbs: cb, fats: f }] };
      }

      // Meals list with items
      const userMeals = localStore.data.meals.filter((m) => m.user_id === userId && m.meal_date === date);
      const rows: any[] = [];
      for (const m of userMeals) {
        const items = localStore.data.mealitems.filter((mi) => mi.meal_id === m.meal_id);
        if (items.length === 0) {
          rows.push({
            meal_id: m.meal_id,
            meal_type: m.meal_type,
            meal_date: m.meal_date,
            created_at: m.created_at,
          });
        } else {
          for (const it of items) {
            const food = localStore.data.foods.find((fd) => fd.food_id === it.food_id);
            rows.push({
              meal_id: m.meal_id,
              meal_type: m.meal_type,
              meal_date: m.meal_date,
              created_at: m.created_at,
              mealitem_id: it.mealitem_id,
              food_id: it.food_id,
              food_name: food ? food.food_name : 'Món ăn',
              quantity: it.quantity,
              calories: it.calories,
              protein: it.protein,
              carbs: it.carbs,
              fat: it.fat,
            });
          }
        }
      }
      return { rows };
    }

    // 1.7 Meal Schedules & Items
    if (upperSql.includes('FROM MEALSCHEDULES')) {
      if (upperSql.includes('IS_PUBLISHED = 1')) {
        const published = localStore.data.mealschedules.filter((s) => s.is_published === 1);
        return {
          rows: published.map((s) => {
            const author = localStore.data.users.find((u) => u.user_id === s.user_id);
            return { ...s, author_name: author ? author.full_name : 'Community Member' };
          }),
        };
      }

      if (upperSql.includes('USER_ID = ?')) {
        const userId = Number(params[0]);
        const schedules = localStore.data.mealschedules.filter((s) => s.user_id === userId);
        return { rows: schedules };
      }

      if (upperSql.includes('SCHEDULE_ID = ?')) {
        const sid = Number(params[0]);
        const s = localStore.data.mealschedules.find((item) => item.schedule_id === sid);
        return { rows: s ? [s] : [] };
      }

      return { rows: localStore.data.mealschedules };
    }

    if (upperSql.includes('FROM MEALSCHEDULEITEMS')) {
      const scheduleId = Number(params[0]);
      const items = localStore.data.mealscheduleitems.filter((i) => i.schedule_id === scheduleId);
      return { rows: items };
    }

    // 1.8 Food Preferences
    if (upperSql.includes('FROM USERFOODPREFERENCES')) {
      const userId = Number(params[0]);
      const prefs = localStore.data.userfoodpreferences.filter((p) => p.user_id === userId);
      return { rows: prefs };
    }

    // 1.9 Food Analysis & Images
    if (upperSql.includes('FROM FOODIMAGES')) {
      const userId = Number(params[0]);
      const imgs = localStore.data.foodimages.filter((img) => img.user_id === userId);
      return { rows: imgs };
    }

    // 1.10 Chat Sessions & Messages
    if (upperSql.includes('FROM CHATSESSIONS')) {
      const userId = Number(params[0]);
      const sessions = localStore.data.chatsessions.filter((cs) => cs.user_id === userId);
      return {
        rows: sessions.map((s) => {
          const msgs = localStore.data.chatmessages.filter((m) => m.session_id === s.session_id);
          const userMsg = msgs.find((m) => m.sender === 'user');
          const lastMsg = msgs[msgs.length - 1];
          return {
            session_id: s.session_id,
            started_at: s.started_at,
            title: userMsg ? userMsg.message_text : 'New Chat',
            last_message: lastMsg ? lastMsg.message_text : '',
          };
        }),
      };
    }

    if (upperSql.includes('FROM CHATMESSAGES')) {
      const sessionId = Number(params[0]);
      const msgs = localStore.data.chatmessages.filter((m) => m.session_id === sessionId);
      return { rows: msgs };
    }

    // 1.11 Admin Audit Logs
    if (upperSql.includes('FROM ADMINAUDITLOGS')) {
      return { rows: localStore.data.adminauditlogs };
    }

    return { rows: [] };
  }

  // ─── 2. INSERT QUERIES ───
  if (upperSql.startsWith('INSERT INTO')) {
    // Accounts
    if (upperSql.includes('ACCOUNTS')) {
      const id = localStore.nextId('accounts', 'account_id');
      const [email, password_hash, email_verified, status] = params;
      localStore.data.accounts.push({
        account_id: id,
        email: email || '',
        password_hash: password_hash || '',
        email_verified: email_verified ?? 1,
        status: status || 'active',
        created_at: new Date().toISOString(),
      });
      localStore.save();
      return { result: { insertId: id, affectedRows: 1 } };
    }

    // Account Roles
    if (upperSql.includes('ACCOUNTROLES')) {
      const [account_id, role_id] = params;
      localStore.data.accountroles.push({ account_id, role_id });
      localStore.save();
      return { result: { insertId: 0, affectedRows: 1 } };
    }

    // Users
    if (upperSql.includes('USERS')) {
      const id = localStore.nextId('users', 'user_id');
      const [account_id, full_name, gender, age, height, weight, has_completed_setup] = params;
      localStore.data.users.push({
        user_id: id,
        account_id,
        full_name: full_name || 'User',
        gender: gender || 'other',
        age: age || 25,
        height: height || 170,
        weight: weight || 65,
        has_completed_setup: has_completed_setup ?? 1,
        created_at: new Date().toISOString(),
      });
      localStore.save();
      return { result: { insertId: id, affectedRows: 1 } };
    }

    // Goals
    if (upperSql.includes('USERGOALS')) {
      const id = localStore.nextId('usergoals', 'goal_id');
      const [user_id, target_calories, target_protein, target_carbs, target_fat, target_weight, goal_type, activity_level] = params;
      localStore.data.usergoals.push({
        goal_id: id,
        user_id,
        target_calories,
        target_protein,
        target_carbs,
        target_fat,
        target_weight,
        goal_type,
        activity_level,
      });
      localStore.save();
      return { result: { insertId: id, affectedRows: 1 } };
    }

    // Meals
    if (upperSql.includes('MEALS (')) {
      const id = localStore.nextId('meals', 'meal_id');
      const [user_id, meal_type, meal_date] = params;
      localStore.data.meals.push({
        meal_id: id,
        user_id,
        meal_type,
        meal_date,
        created_at: new Date().toISOString(),
      });
      localStore.save();
      return { result: { insertId: id, affectedRows: 1 } };
    }

    // Meal Items
    if (upperSql.includes('MEALITEMS')) {
      const id = localStore.nextId('mealitems', 'mealitem_id');
      const [meal_id, food_id, quantity, calories, protein, carbs, fat] = params;
      localStore.data.mealitems.push({
        mealitem_id: id,
        meal_id,
        food_id,
        quantity: quantity || 1,
        calories: calories || 0,
        protein: protein || 0,
        carbs: carbs || 0,
        fat: fat || 0,
      });
      localStore.save();
      return { result: { insertId: id, affectedRows: 1 } };
    }

    // Foods
    if (upperSql.includes('FOODS (')) {
      const id = localStore.nextId('foods', 'food_id');
      const [food_name, calories, protein, carbs, fat] = params;
      localStore.data.foods.push({
        food_id: id,
        food_name,
        calories: calories || 0,
        protein: protein || 0,
        carbs: carbs || 0,
        fat: fat || 0,
      });
      localStore.save();
      return { result: { insertId: id, affectedRows: 1 } };
    }

    // Schedules
    if (upperSql.includes('MEALSCHEDULES (')) {
      const id = localStore.nextId('mealschedules', 'schedule_id');
      const [user_id, name, description, start_date, end_date, color, target_calories, source, plan_payload] = params;
      localStore.data.mealschedules.push({
        schedule_id: id,
        user_id,
        name,
        description,
        start_date,
        end_date,
        color,
        target_calories,
        source: source || 'manual',
        plan_payload,
        is_published: 0,
        created_at: new Date().toISOString(),
      });
      localStore.save();
      return { result: { insertId: id, affectedRows: 1 } };
    }

    // Schedule items
    if (upperSql.includes('MEALSCHEDULEITEMS')) {
      const id = localStore.nextId('mealscheduleitems', 'item_id');
      const [schedule_id, day_offset, meal_type, name, serving, calories, protein, carbs, fat, notes, sort_order] = params;
      localStore.data.mealscheduleitems.push({
        item_id: id,
        schedule_id,
        day_offset,
        meal_type,
        name,
        serving,
        calories,
        protein,
        carbs,
        fat,
        notes,
        sort_order,
      });
      localStore.save();
      return { result: { insertId: id, affectedRows: 1 } };
    }

    // Preferences
    if (upperSql.includes('USERFOODPREFERENCES')) {
      const id = localStore.nextId('userfoodpreferences', 'preference_id');
      const [user_id, food_name, preference_type, meal_slot, note, weight, source] = params;
      localStore.data.userfoodpreferences.push({
        preference_id: id,
        user_id,
        food_name,
        preference_type,
        meal_slot,
        note,
        weight,
        source,
      });
      localStore.save();
      return { result: { insertId: id, affectedRows: 1 } };
    }

    // Chat sessions
    if (upperSql.includes('CHATSESSIONS')) {
      const id = localStore.nextId('chatsessions', 'session_id');
      const [user_id] = params;
      localStore.data.chatsessions.push({
        session_id: id,
        user_id,
        started_at: new Date().toISOString(),
      });
      localStore.save();
      return { result: { insertId: id, affectedRows: 1 } };
    }

    // Chat messages
    if (upperSql.includes('CHATMESSAGES')) {
      const id = localStore.nextId('chatmessages', 'message_id');
      const [session_id, sender, message_text, imgUrlOrThinking, imgNameOrInsight] = params;
      localStore.data.chatmessages.push({
        message_id: id,
        session_id,
        sender,
        message_text,
        image_url: typeof imgUrlOrThinking === 'string' && !imgUrlOrThinking.startsWith('[') ? imgUrlOrThinking : null,
        thinking_steps: typeof imgUrlOrThinking === 'string' && imgUrlOrThinking.startsWith('[') ? JSON.parse(imgUrlOrThinking) : null,
        food_insight: typeof imgNameOrInsight === 'string' && imgNameOrInsight.startsWith('{') ? JSON.parse(imgNameOrInsight) : null,
        created_at: new Date().toISOString(),
      });
      localStore.save();
      return { result: { insertId: id, affectedRows: 1 } };
    }

    // Audit logs
    if (upperSql.includes('ADMINAUDITLOGS')) {
      const id = localStore.nextId('adminauditlogs', 'log_id');
      const [admin_account_id, action, target_type, target_id, detail] = params;
      localStore.data.adminauditlogs.push({
        log_id: id,
        admin_account_id,
        action,
        target_type,
        target_id,
        detail,
        created_at: new Date().toISOString(),
      });
      localStore.save();
      return { result: { insertId: id, affectedRows: 1 } };
    }

    return { result: { insertId: 1, affectedRows: 1 } };
  }

  // ─── 3. UPDATE QUERIES ───
  if (upperSql.startsWith('UPDATE')) {
    if (upperSql.includes('ACCOUNTS SET PASSWORD_HASH')) {
      const [hash, id] = params;
      const acc = localStore.data.accounts.find((a) => a.account_id === Number(id));
      if (acc) acc.password_hash = hash;
      localStore.save();
    } else if (upperSql.includes('ACCOUNTS SET STATUS')) {
      const [status, id] = params;
      const acc = localStore.data.accounts.find((a) => a.account_id === Number(id));
      if (acc) acc.status = status;
      localStore.save();
    } else if (upperSql.includes('MEALSCHEDULES SET IS_PUBLISHED')) {
      const [nextState, , scheduleId] = params;
      const s = localStore.data.mealschedules.find((item) => item.schedule_id === Number(scheduleId));
      if (s) {
        s.is_published = nextState;
        s.published_at = nextState === 1 ? new Date().toISOString() : null;
      }
      localStore.save();
    }
    return { result: { insertId: 0, affectedRows: 1 } };
  }

  // ─── 4. DELETE QUERIES ───
  if (upperSql.startsWith('DELETE FROM')) {
    if (upperSql.includes('MEALS WHERE MEAL_ID = ?')) {
      const mealId = Number(params[0]);
      localStore.data.meals = localStore.data.meals.filter((m) => m.meal_id !== mealId);
      localStore.data.mealitems = localStore.data.mealitems.filter((mi) => mi.meal_id !== mealId);
      localStore.save();
    } else if (upperSql.includes('MEALSCHEDULES WHERE SCHEDULE_ID = ?')) {
      const sid = Number(params[0]);
      localStore.data.mealschedules = localStore.data.mealschedules.filter((s) => s.schedule_id !== sid);
      localStore.data.mealscheduleitems = localStore.data.mealscheduleitems.filter((i) => i.schedule_id !== sid);
      localStore.save();
    } else if (upperSql.includes('USERFOODPREFERENCES WHERE PREFERENCE_ID = ?')) {
      const pid = Number(params[0]);
      localStore.data.userfoodpreferences = localStore.data.userfoodpreferences.filter((p) => p.preference_id !== pid);
      localStore.save();
    } else if (upperSql.includes('CHATSESSIONS WHERE SESSION_ID = ?')) {
      const sid = Number(params[0]);
      localStore.data.chatsessions = localStore.data.chatsessions.filter((s) => s.session_id !== sid);
      localStore.data.chatmessages = localStore.data.chatmessages.filter((m) => m.session_id !== sid);
      localStore.save();
    }
    return { result: { insertId: 0, affectedRows: 1 } };
  }

  return { rows: [], result: { insertId: 0, affectedRows: 0 } };
};
