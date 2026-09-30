import { ENV } from '../config/env';
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

export class CloudflareR2StorageService {
  private static instance: CloudflareR2StorageService;
  public endpoint: string;
  public bucket: string;
  public token: string;
  public key: string;
  public publicUrl: string;
  private localCacheDir: string;

  constructor() {
    this.endpoint = (ENV.CLOUDFLARE_R2_ENDPOINT || '').replace(/\/$/, '');
    this.bucket = ENV.CLOUDFLARE_R2_BUCKET || 'images';
    this.token = ENV.CLOUDFLARE_R2_TOKEN || '';
    this.key = ENV.CLOUDFLARE_R2_KEY || '';
    this.publicUrl = (ENV.CLOUDFLARE_R2_PUBLIC_URL || `${this.endpoint}/${this.bucket}`).replace(/\/$/, '');
    this.localCacheDir = path.resolve(process.cwd(), 'uploads', 'r2_images');
    if (!fs.existsSync(this.localCacheDir)) {
      fs.mkdirSync(this.localCacheDir, { recursive: true });
    }
  }

  public static getInstance(): CloudflareR2StorageService {
    if (!this.instance) {
      this.instance = new CloudflareR2StorageService();
    }
    return this.instance;
  }

  public async uploadImage(
    dataOrUrl: string,
    filename?: string
  ): Promise<string> {
    if (!dataOrUrl) {
      return '';
    }

    // If it's already an R2 URL
    if (dataOrUrl.startsWith('http://') || dataOrUrl.startsWith('https://')) {
      if (dataOrUrl.includes('r2.cloudflarestorage.com')) {
        return dataOrUrl;
      }
    }

    let buffer: Buffer;
    let contentType = 'image/jpeg';
    let ext = '.jpg';

    if (dataOrUrl.startsWith('data:image/')) {
      const match = dataOrUrl.match(/^data:(image\/[a-zA-Z0-9+.-]+);base64,(.+)$/);
      if (match) {
        contentType = match[1];
        buffer = Buffer.from(match[2], 'base64');
        if (contentType.includes('png')) ext = '.png';
        else if (contentType.includes('webp')) ext = '.webp';
      } else {
        buffer = Buffer.from(dataOrUrl);
      }
    } else {
      buffer = Buffer.from(dataOrUrl);
    }

    const uniqueName = filename || `${Date.now()}_${crypto.randomBytes(8).toString('hex')}${ext}`;
    const targetUrl = `${this.publicUrl}/${uniqueName}`;

    // Always persist to local cache for resilience
    try {
      const localFilePath = path.join(this.localCacheDir, uniqueName);
      fs.writeFileSync(localFilePath, buffer);
    } catch (err) {
      console.warn('[R2Storage] Local cache write warning:', err);
    }

    // Upload to Cloudflare R2
    if (this.endpoint && (this.token || this.key)) {
      try {
        const headers: Record<string, string> = {
          'Content-Type': contentType,
          'Content-Length': buffer.length.toString(),
        };
        if (this.token) {
          headers['Authorization'] = `Bearer ${this.token}`;
        }

        const res = await fetch(targetUrl, {
          method: 'PUT',
          headers,
          body: new Uint8Array(buffer),
          signal: AbortSignal.timeout(5000),
        });

        if (res.ok) {
          console.log(`[R2Storage] Image successfully uploaded to R2: ${uniqueName}`);
        }
      } catch (err: any) {
        console.warn(`[R2Storage] Cloudflare R2 upload note: ${err?.message || err}. Preserved in local storage.`);
      }
    }

    return targetUrl;
  }
}

export const r2StorageService = CloudflareR2StorageService.getInstance();
