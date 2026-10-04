export interface ApiResponse<T = any> {
  success: boolean;
  statusCode: number;
  data: T;
  message: string;
  timestamp: string;
}

export interface ApiErrorResponse {
  success: false;
  statusCode: number;
  message: string;
  error?: string | any;
  timestamp: string;
}
