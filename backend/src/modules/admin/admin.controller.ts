import {
  Controller,
  Get,
  Patch,
  Param,
  Body,
  Query,
  ParseIntPipe,
  DefaultValuePipe,
  UseGuards,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiQuery, ApiBearerAuth } from '@nestjs/swagger';
import { AdminService } from './admin.service';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { RolesGuard } from '../../common/guards/roles.guard';
import { Roles } from '../../common/decorators/roles.decorator';
import { CurrentUser, CurrentUserPayload } from '../../common/decorators/current-user.decorator';
import { Role, AccountStatus } from '@prisma/client';

@ApiTags('Admin')
@ApiBearerAuth()
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles(Role.ADMIN)
@Controller('admin')
export class AdminController {
  constructor(private adminService: AdminService) {}

  @Get('users')
  @ApiOperation({ summary: 'List all accounts with pagination (Admin only)' })
  @ApiQuery({ name: 'page', required: false, type: Number, example: 1 })
  @ApiQuery({ name: 'limit', required: false, type: Number, example: 20 })
  async getUsers(
    @Query('page', new DefaultValuePipe(1), ParseIntPipe) page: number = 1,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number = 20,
  ) {
    const data = await this.adminService.getUsers(page, limit);
    return { data };
  }

  @Patch('users/:id/status')
  @ApiOperation({ summary: 'Update user account status (Admin only)' })
  async updateUserStatus(
    @CurrentUser() admin: CurrentUserPayload,
    @Param('id', ParseIntPipe) targetId: number,
    @Body('status') status: AccountStatus,
  ) {
    const updated = await this.adminService.updateUserStatus(
      admin.accountId,
      targetId,
      status,
    );
    return {
      message: 'Account status updated and audit logged',
      data: updated,
    };
  }

  @Get('audit-logs')
  @ApiOperation({ summary: 'View administrative audit logs (Admin only)' })
  async getAuditLogs(
    @Query('page', new DefaultValuePipe(1), ParseIntPipe) page: number = 1,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number = 20,
  ) {
    const data = await this.adminService.getAuditLogs(page, limit);
    return { data };
  }
}
