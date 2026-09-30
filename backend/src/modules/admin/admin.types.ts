export interface CreateUserDto {
  email: string;
  password?: string;
  name: string;
  role?: 'user' | 'admin';
  gender?: 'male' | 'female' | 'other';
  age?: number;
  height?: number;
  weight?: number;
}

export interface UpdateUserDto {
  name?: string;
  email?: string;
  gender?: 'male' | 'female' | 'other';
  age?: number;
  height?: number;
  weight?: number;
  status?: 'active' | 'inactive' | 'suspended';
}

export interface CreateFoodDto {
  foodName: string;
  categoryId?: number;
  calories: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  fiber?: number;
  sugar?: number;
  sodium?: number;
  servingSize?: string;
}

export interface UpdateFoodDto extends Partial<CreateFoodDto> {}
