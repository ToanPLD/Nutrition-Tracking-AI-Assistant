import { NestFactory } from '@nestjs/core';
import { ValidationPipe, Logger } from '@nestjs/common';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { AppModule } from './app.module';

async function bootstrap() {
  const logger = new Logger('Bootstrap');
  const app = await NestFactory.create(AppModule);

  // 1. Global Prefix
  app.setGlobalPrefix('api/v1');

  // Support both legacy /api and /api/v1 seamlessly
  app.use((req: any, _res: any, next: any) => {
    if (
      req.url.startsWith('/api/') &&
      !req.url.startsWith('/api/v1/') &&
      !req.url.startsWith('/api/docs')
    ) {
      req.url = req.url.replace('/api/', '/api/v1/');
    }
    next();
  });

  // 2. CORS
  app.enableCors({
    origin: '*',
    credentials: true,
  });

  // 3. Validation Pipe
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      transform: true,
      forbidNonWhitelisted: true,
      transformOptions: { enableImplicitConversion: true },
    }),
  );

  // 4. Swagger Documentation
  const config = new DocumentBuilder()
    .setTitle('CalAI Nutrition Tracking API')
    .setDescription('Enterprise Production-Grade RESTful API for CalAI Nutrition Assistant')
    .setVersion('1.0')
    .addBearerAuth()
    .build();

  const document = SwaggerModule.createDocument(app, config);
  SwaggerModule.setup('api/docs', app, document, {
    customSiteTitle: 'CalAI API Documentation',
  });

  const port = process.env.PORT || 3000;
  await app.listen(port);

  logger.log(`🚀 [CalAI NestJS Backend] Server running on http://localhost:${port}/api/v1`);
  logger.log(`📖 [Swagger Docs] Available at http://localhost:${port}/api/docs`);
}

bootstrap().catch((err) => {
  console.error('Fatal startup error:', err);
  process.exit(1);
});
