// backend/tests/food-analysis-service.test.mjs
import { test, describe, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { FoodAnalysisService } = require('../dist/modules/user/services/food-analysis.service.js');
const { AppError } = require('../dist/shared/errors/app-error.js');
const { profileService } = require('../dist/modules/user/services/profile.service.js');
const { r2StorageService } = require('../dist/services/r2-storage.service.js');
const dbQueryModule = require('../dist/database/query.js');

describe('FoodAnalysisService.analyzeImage', () => {
  let service;
  let originalFetch;
  let originalDbExecute;
  let originalDbQueryOne;
  let originalGetUserId;
  let originalR2Upload;

  beforeEach(() => {
    service = new FoodAnalysisService();
    originalFetch = global.fetch;
    originalDbExecute = dbQueryModule.dbExecute;
    originalDbQueryOne = dbQueryModule.dbQueryOne;
    originalGetUserId = profileService.getUserId;
    originalR2Upload = r2StorageService.uploadImage;

    // Mock DB and profile helpers
    profileService.getUserId = async () => 1;
    r2StorageService.uploadImage = async (url) => url;
    dbQueryModule.dbExecute = async () => ({ insertId: 99 });
    dbQueryModule.dbQueryOne = async () => null;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    dbQueryModule.dbExecute = originalDbExecute;
    dbQueryModule.dbQueryOne = originalDbQueryOne;
    profileService.getUserId = originalGetUserId;
    r2StorageService.uploadImage = originalR2Upload;
  });

  test('should throw AppError and NOT fall back to mock salad when Cal-AI returns 500 error', async () => {
    global.fetch = async () => ({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Internal model inference error' })
    });

    await assert.rejects(
      async () => {
        await service.analyzeImage(1, { imageUrl: 'data:image/jpeg;base64,123' });
      },
      (err) => {
        assert(err instanceof AppError, 'Expected err to be instance of AppError');
        assert.strictEqual(err.statusCode, 502);
        assert(err.message.includes('Internal model inference error') || err.message.includes('500'));
        return true;
      }
    );
  });

  test('should throw AppError on Cal-AI timeout or network failure', async () => {
    global.fetch = async () => {
      const err = new Error('The operation was aborted');
      err.name = 'TimeoutError';
      throw err;
    };

    await assert.rejects(
      async () => {
        await service.analyzeImage(1, { imageUrl: 'data:image/jpeg;base64,123' });
      },
      (err) => {
        assert(err instanceof AppError, 'Expected err to be instance of AppError');
        assert.strictEqual(err.statusCode, 502);
        assert(err.message.includes('timed out'));
        return true;
      }
    );
  });

  test('should successfully map Cal-AI analysis response and return recognized food', async () => {
    global.fetch = async (url, options) => {
      assert(options.body.includes('data:image/jpeg;base64,123'));
      return {
        ok: true,
        status: 200,
        json: async () => ({
          name: 'Phở bò tái nạm',
          calories: 450,
          protein: 32.5,
          carbs: 60.0,
          fat: 10.0,
          confidence: 0.95,
          estimated_portion: '1 tô phở lớn 500g'
        })
      };
    };

    const res = await service.analyzeImage(1, { imageUrl: 'data:image/jpeg;base64,123' });
    assert.strictEqual(res.name, 'Phở bò tái nạm');
    assert.strictEqual(res.totalKcal, 450);
    assert.strictEqual(res.protein, 32.5);
    assert.strictEqual(res.carbs, 60.0);
    assert.strictEqual(res.fats, 10.0);
    assert.strictEqual(res.confidence, 0.95);
    assert.strictEqual(res.estimatedPortion, '1 tô phở lớn 500g');
  });
});
