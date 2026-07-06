from __future__ import annotations

from .local_sync import LocalSyncProvider, detect_cloud_sources
from .models import CloudCapability, CloudProviderType, CloudSource


class ApplePhotosProvider(LocalSyncProvider):
    provider_type = CloudProviderType.APPLE_PHOTOS.value

    def display_name(self) -> str:
        return "Apple Photos - lokalni knihovna (jen pro cteni)"

    def capabilities(self) -> list[str]:
        return super().capabilities() + [CloudCapability.READ_ONLY.value]

    def list_sources(self, account_id: str) -> list[CloudSource]:
        return [
            CloudSource(
                provider=self.provider_type,
                account_id=account_id,
                source_id=src.root,
                name=src.label,
                source_uri=src.root,
                kind=src.category,
                is_read_only=True,
                limitation_text="Pristupuje pouze ke lokalni knihovne Photos na macOS. Cloudovy login iCloud Photos se nepredstira.",
                metadata=src.to_dict(),
            )
            for src in detect_cloud_sources(provider="icloud")
            if src.category == "photos"
        ]
