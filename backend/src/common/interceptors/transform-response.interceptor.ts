import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
} from '@nestjs/common';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { ApiResponse } from '../dto/api-response.dto';

@Injectable()
export class TransformResponseInterceptor<T>
  implements NestInterceptor<T, ApiResponse<T>>
{
  intercept(
    context: ExecutionContext,
    next: CallHandler,
  ): Observable<ApiResponse<T>> {
    const ctx = context.switchToHttp();
    const response = ctx.getResponse();
    const statusCode = response.statusCode || 200;

    return next.handle().pipe(
      map((data) => {
        // If response already matches standard envelope, return directly
        if (data && typeof data === 'object' && 'success' in data && 'timestamp' in data) {
          return data;
        }

        const message =
          data && typeof data === 'object' && 'message' in data && typeof data.message === 'string'
            ? data.message
            : 'Success';

        // Extract payload data if message was embedded
        const actualData =
          data && typeof data === 'object' && 'data' in data
            ? data.data
            : data;

        return {
          success: true,
          statusCode,
          data: actualData ?? null,
          message,
          timestamp: new Date().toISOString(),
          ...(actualData && typeof actualData === 'object' && 'valid' in actualData
            ? { valid: (actualData as any).valid }
            : {}),
          ...(data && typeof data === 'object' && 'valid' in data
            ? { valid: (data as any).valid }
            : {}),
        };
      }),
    );
  }
}
