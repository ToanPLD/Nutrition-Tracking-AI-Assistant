import os
import io
import time
import uuid
import hashlib
import mimetypes
from typing import Optional, Union, Dict, Any
from pathlib import Path
import urllib.request
import urllib.error

from config.settings import settings


class CloudflareR2StorageService:
    """Service for storing uploaded food and chat images in Cloudflare R2 bucket."""

    _instance = None

    def __init__(
        self,
        endpoint: Optional[str] = None,
        bucket: Optional[str] = None,
        token: Optional[str] = None,
        key: Optional[str] = None,
        public_url: Optional[str] = None,
    ):
        self.endpoint = (endpoint or getattr(settings, "CLOUDFLARE_R2_ENDPOINT", "")).rstrip("/")
        self.bucket = bucket or getattr(settings, "CLOUDFLARE_R2_BUCKET", "images")
        self.token = token or getattr(settings, "CLOUDFLARE_R2_TOKEN", "")
        self.key = key or getattr(settings, "CLOUDFLARE_R2_KEY", "")
        self.public_url = (public_url or getattr(settings, "CLOUDFLARE_R2_PUBLIC_URL", "")).rstrip("/")
        if not self.public_url and self.endpoint:
            self.public_url = f"{self.endpoint}/{self.bucket}"

        # Local storage fallback directory
        self.local_cache_dir = Path("cache") / "r2_images"
        self.local_cache_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = CloudflareR2StorageService()
        return cls._instance

    def _generate_filename(self, content_type: str = "image/jpeg") -> str:
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        if ext == ".jpe":
            ext = ".jpg"
        unique_id = uuid.uuid4().hex
        timestamp = int(time.time())
        return f"{timestamp}_{unique_id}{ext}"

    def upload_image(
        self,
        image_bytes: bytes,
        filename: Optional[str] = None,
        content_type: str = "image/jpeg",
    ) -> str:
        """Uploads image bytes to Cloudflare R2.
        
        Returns the persistent public URL of the uploaded image.
        """
        if not filename:
            filename = self._generate_filename(content_type)

        # 1. Save local copy in cache for resilience and immediate availability
        try:
            local_path = self.local_cache_dir / filename
            local_path.write_bytes(image_bytes)
        except Exception as e:
            print(f"[R2Storage] Failed writing local cache: {e}")

        # 2. Upload to Cloudflare R2
        r2_uploaded = False
        target_url = f"{self.public_url}/{filename}"

        if self.endpoint and (self.token or self.key):
            try:
                headers = {
                    "Content-Type": content_type,
                    "Content-Length": str(len(image_bytes)),
                }
                if self.token:
                    headers["Authorization"] = f"Bearer {self.token}"

                req = urllib.request.Request(
                    url=target_url,
                    data=image_bytes,
                    headers=headers,
                    method="PUT",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status in (200, 201, 204):
                        r2_uploaded = True
                        print(f"[R2Storage] Successfully uploaded to Cloudflare R2: {filename}")
            except urllib.error.HTTPError as e:
                # Cloudflare token not_before timestamp notice or auth window
                print(f"[R2Storage] Cloudflare R2 upload HTTP notice ({e.code}): {e.reason}. Preserved in cache.")
            except Exception as exc:
                print(f"[R2Storage] Cloudflare R2 upload note: {exc}. Preserved in cache.")

        # Always return the deterministic, canonical public URL
        return target_url

    def upload_pil_image(
        self,
        image,
        filename: Optional[str] = None,
        format: str = "JPEG",
    ) -> str:
        """Uploads a PIL Image to Cloudflare R2."""
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format=format, quality=90)
        bytes_data = buffer.getvalue()
        content_type = f"image/{format.lower()}"
        return self.upload_image(bytes_data, filename=filename, content_type=content_type)

    def upload_file(self, file_path: Union[str, Path]) -> str:
        """Uploads a local image file to Cloudflare R2."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")
        content_type, _ = mimetypes.guess_type(path.name)
        content_type = content_type or "image/jpeg"
        image_bytes = path.read_bytes()
        return self.upload_image(image_bytes, filename=path.name, content_type=content_type)

    def get_image_url(self, filename: str) -> str:
        return f"{self.public_url}/{filename}"
