import { MealsService } from './meals.service';

describe('MealsService - Macro Aggregation', () => {
  it('correctly aggregates calories and macronutrients for multiple items', () => {
    const items = [
      { calories: 350, protein: 25, carbs: 40, fat: 10, quantity: 1.5 }, // 525 kcal, 37.5p, 60c, 15f
      { calories: 150, protein: 5, carbs: 30, fat: 2, quantity: 2.0 },   // 300 kcal, 10p, 60c, 4f
    ];

    const totals = MealsService.sumNutrition(items);

    expect(totals.calories).toBe(825);
    expect(totals.protein).toBe(47.5);
    expect(totals.carbs).toBe(120);
    expect(totals.fat).toBe(19);
  });
});
