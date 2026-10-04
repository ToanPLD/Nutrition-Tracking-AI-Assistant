import { Injectable, OnModuleInit, OnModuleDestroy, Logger } from '@nestjs/common';
import { PrismaClient } from '@prisma/client';

@Injectable()
export class PrismaService
  extends PrismaClient
  implements OnModuleInit, OnModuleDestroy
{
  private readonly logger = new Logger(PrismaService.name);

  async onModuleInit() {
    try {
      await this.$connect();
      this.logger.log('✅ [PostgreSQL] Connected successfully via Prisma ORM!');
    } catch (error) {
      this.logger.warn(`⚠️ [PostgreSQL] Initial connection deferred or offline: ${error}`);
    }
  }

  async onModuleDestroy() {
    await this.$disconnect();
    this.logger.log('🛑 [PostgreSQL] Prisma client disconnected.');
  }
}
