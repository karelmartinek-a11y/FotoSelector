from __future__ import annotations

from .local_sync import LocalSyncProvider, detect_cloud_sources
from .models import CloudProviderType, CloudSource


class ICloudLocalProvider(LocalSyncProvider):
    provider_type = CloudProviderType.ICLOUD_LOCAL.value

    def display_name(self) -> str:
        return "iCloud Drive - lokalne synchronizovana slozka"

    def list_sources(self, account_id: str) -> list[CloudSource]:
        return [
            CloudSource(
                provider=self.provider_type,
                account_id=account_id,
                source_id=src.root,
                name=src.label,
                source_uri=src.root,
                kind=src.category,
                is_read_only=src.read_only,
                limitation_text="Pracuje pouze s lokalne synchronizovanou slozkou iCloud Drive. Nejde o webovy login do iCloudu.",
                metadata=src.to_dict(),
            )
            for src in detect_cloud_sources(provider="icloud")
            if src.category == "documents"
        ]
