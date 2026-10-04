import {
  Injectable,
  ConflictException,
  UnauthorizedException,
  NotFoundException,
} from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcryptjs';
import { PrismaService } from '../../database/prisma.service';
import { RegisterDto } from './dto/register.dto';
import { LoginDto } from './dto/login.dto';
import { Role, AccountStatus, Gender } from '@prisma/client';

@Injectable()
export class AuthService {
  constructor(
    private prisma: PrismaService,
    private jwtService: JwtService,
  ) {}

  async hashPassword(password: string): Promise<string> {
    return bcrypt.hash(password, 10);
  }

  async comparePassword(password: string, hash: string): Promise<boolean> {
    return bcrypt.compare(password, hash);
  }

  async register(dto: RegisterDto) {
    const existing = await this.prisma.account.findUnique({
      where: { email: dto.email.toLowerCase() },
    });

    if (existing) {
      throw new ConflictException('An account with this email already exists');
    }

    const passwordHash = await this.hashPassword(dto.password);

    const account = await this.prisma.account.create({
      data: {
        email: dto.email.toLowerCase(),
        passwordHash,
        role: Role.USER,
        status: AccountStatus.ACTIVE,
        emailVerified: true,
        user: {
          create: {
            fullName: dto.fullName || null,
            gender: Gender.OTHER,
            hasCompletedSetup: false,
          },
        },
      },
      include: {
        user: true,
      },
    });

    const token = this.generateToken(account.id, account.email, account.role);

    return {
      accessToken: token,
      token,
      role: account.role.toLowerCase(),
      account: {
        id: account.id,
        email: account.email,
        role: account.role,
        user: account.user,
      },
    };
  }

  async login(dto: LoginDto) {
    const account = await this.prisma.account.findUnique({
      where: { email: dto.email.toLowerCase() },
      include: {
        user: {
          include: {
            goals: {
              orderBy: { createdAt: 'desc' },
              take: 1,
            },
          },
        },
      },
    });

    if (!account || !account.passwordHash) {
      throw new UnauthorizedException('Invalid email or password');
    }

    const passwordValid = await this.comparePassword(dto.password, account.passwordHash);
    if (!passwordValid) {
      throw new UnauthorizedException('Invalid email or password');
    }

    if (account.status !== AccountStatus.ACTIVE) {
      throw new UnauthorizedException('This account has been deactivated or suspended');
    }

    const token = this.generateToken(account.id, account.email, account.role);

    return {
      accessToken: token,
      token,
      role: account.role.toLowerCase(),
      account: {
        id: account.id,
        email: account.email,
        role: account.role,
        user: account.user,
      },
    };
  }

  async getMe(accountId: number) {
    const account = await this.prisma.account.findUnique({
      where: { id: accountId },
      include: {
        user: {
          include: {
            goals: {
              orderBy: { createdAt: 'desc' },
              take: 1,
            },
          },
        },
      },
    });

    if (!account) {
      throw new NotFoundException('Account not found');
    }

    return {
      id: account.id,
      email: account.email,
      role: account.role,
      status: account.status,
      user: account.user,
    };
  }

  private generateToken(accountId: number, email: string, role: Role): string {
    const payload = {
      sub: accountId,
      email,
      role,
    };
    return this.jwtService.sign(payload);
  }
}
