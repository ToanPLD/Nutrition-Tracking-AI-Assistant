import { UsersService } from './users.service';

describe('UsersService - Basal Goal Estimation', () => {
  it('calculates recommended calories based on height, weight, age, and gender', () => {
    const calories = UsersService.calculateTdee({
      weight: 70,
      height: 175,
      age: 25,
      gender: 'MALE',
      activityLevel: 'moderate',
      goalType: 'WEIGHT_LOSS',
    });
    expect(calories).toBeGreaterThan(1500);
    expect(calories).toBeLessThan(2600);
  });
});
