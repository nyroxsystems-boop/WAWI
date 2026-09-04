"""Authenticated, tenant-bound media delivery.

Raw MEDIA_ROOT must never be mounted by the reverse proxy: it contains
invoices, external documents, attachments and executable report templates.
Only explicitly tenant-owned raster product images are served here. Sensitive
documents already have object-level API download endpoints.
"""

from pathlib import Path, PurePosixPath

from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from tenancy.permissions import IsActiveTenantContext


class ProtectedMediaView(APIView):
    """Serve a media object only after authentication and ownership checks."""

    permission_classes = [IsAuthenticated, IsActiveTenantContext]

    def get(self, request, media_path):
        normalized = self._normalize(media_path)
        user = request.user

        if not user.is_superuser:
            tenant = getattr(request, 'tenant', None)
            if tenant is None or not self._tenant_owns(normalized, tenant):
                raise Http404

        media_root = Path(settings.MEDIA_ROOT).resolve()
        try:
            candidate = (media_root / normalized).resolve(strict=True)
        except OSError as exc:
            raise Http404 from exc
        if not candidate.is_relative_to(media_root) or not candidate.is_file():
            raise Http404

        with candidate.open('rb') as image_file:
            signature = image_file.read(16)
        content_type = self._image_content_type(signature)
        if content_type is None:
            raise Http404

        response = FileResponse(
            candidate.open('rb'),
            content_type=content_type,
            as_attachment=False,
            filename=candidate.name,
        )
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "default-src 'none'; sandbox"
        response['X-Frame-Options'] = 'DENY'
        return response

    @staticmethod
    def _normalize(raw_path):
        candidate = PurePosixPath(str(raw_path))
        if candidate.is_absolute() or '..' in candidate.parts or '\x00' in str(raw_path):
            raise Http404
        normalized = candidate.as_posix().lstrip('/')
        if not normalized:
            raise Http404
        return normalized

    @staticmethod
    def _tenant_owns(media_path, tenant):
        # Keep this allowlist explicit. PDFs and attachments are downloaded via
        # their object APIs, which already apply domain-specific permissions.
        if not media_path.startswith('products/'):
            return False
        from wws.models import Product

        return Product.objects.filter(tenant=tenant, image=media_path).exists()

    @staticmethod
    def _image_content_type(signature):
        """Detect supported raster formats from bytes, never from an extension."""
        if signature.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        if signature.startswith((b'GIF87a', b'GIF89a')):
            return 'image/gif'
        if signature.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        if signature.startswith(b'RIFF') and signature[8:12] == b'WEBP':
            return 'image/webp'
        if signature[4:8] == b'ftyp' and signature[8:12] in (b'avif', b'avis'):
            return 'image/avif'
        return None
