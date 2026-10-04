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

  it('triggers and persists baseline goals on updateProfile if unset', async () => {
    const mockPrisma: any = {
      user: {
        update: jest.fn().mockResolvedValue({
          id: 1,
          height: 175,
          weight: 70,
          age: 25,
          gender: 'MALE',
        }),
      },
      weightHistory: {
        create: jest.fn().mockResolvedValue({}),
      },
      userGoal: {
        findFirst: jest.fn().mockResolvedValue(null), // no goals set yet
        create: jest.fn().mockResolvedValue({ id: 101, targetCalories: 2100 }),
      },
    };

    const service = new UsersService(mockPrisma);
    await service.updateProfile(1, { height: 175, weight: 70, age: 25 });

    expect(mockPrisma.userGoal.create).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          userId: 1,
          targetCalories: expect.any(Number),
        }),
      }),
    );
  });
});
