import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../../database/prisma.service';
import { AccountStatus } from '@prisma/client';

@Injectable()
export class AdminService {
  constructor(private prisma: PrismaService) {}

  async getUsers(page = 1, limit = 20) {
    const skip = (page - 1) * limit;

    const [users, total] = await Promise.all([
      this.prisma.account.findMany({
        select: {
          id: true,
          email: true,
          role: true,
          status: true,
          createdAt: true,
          user: {
            select: {
              id: true,
              fullName: true,
              gender: true,
              age: true,
            },
          },
        },
        skip,
        take: limit,
        orderBy: { createdAt: 'desc' },
      }),
      this.prisma.account.count(),
    ]);

    return {
      users,
      pagination: {
        total,
        page,
        limit,
        totalPages: Math.ceil(total / limit),
      },
    };
  }

  async updateUserStatus(
    adminAccountId: number,
    targetAccountId: number,
    status: AccountStatus,
  ) {
    const target = await this.prisma.account.findUnique({
      where: { id: targetAccountId },
    });

    if (!target) {
      throw new NotFoundException(`Account with ID ${targetAccountId} not found`);
    }

    const updated = await this.prisma.account.update({
      where: { id: targetAccountId },
      data: { status },
    });

    await this.prisma.adminAuditLog.create({
      data: {
        adminAccountId,
        action: 'UPDATE_ACCOUNT_STATUS',
        targetType: 'ACCOUNT',
        targetId: targetAccountId,
        detail: `Status changed from ${target.status} to ${status}`,
      },
    });

    return updated;
  }

  async getAuditLogs(page = 1, limit = 20) {
    const skip = (page - 1) * limit;

    const [logs, total] = await Promise.all([
      this.prisma.adminAuditLog.findMany({
        include: {
          adminAccount: {
            select: { id: true, email: true },
          },
        },
        skip,
        take: limit,
        orderBy: { createdAt: 'desc' },
      }),
      this.prisma.adminAuditLog.count(),
    ]);

    return {
      logs,
      pagination: {
        total,
        page,
        limit,
        totalPages: Math.ceil(total / limit),
      },
    };
  }
}
