from __future__ import annotations

import json
import os
from typing import Dict, Iterable, List, Optional

from .apple_photos import ApplePhotosProvider
from .cache import CloudCacheManager, app_data_dir
from .google_drive import GoogleDriveProvider
from .google_photos import GooglePhotosProvider
from .icloud_local import ICloudLocalProvider
from .local_sync import LocalSyncProvider
from .models import CloudAccount, CloudAsset, CloudDownloadState, CloudProviderType, CloudSource
from .onedrive import OneDriveProvider
from .token_store import TokenStore


class CloudServiceManager:
    def __init__(
        self,
        token_store: TokenStore | None = None,
        cache_manager: CloudCacheManager | None = None,
        providers: Optional[Dict[str, object]] = None,
    ):
        self.token_store = token_store or TokenStore()
        self.cache_manager = cache_manager or CloudCacheManager()
        self._accounts_path = os.path.join(app_data_dir(), "cloud_accounts.json")
        self.providers = providers or {
            CloudProviderType.LOCAL_SYNC.value: LocalSyncProvider(),
            CloudProviderType.GOOGLE_DRIVE.value: GoogleDriveProvider(self.token_store),
            CloudProviderType.GOOGLE_PHOTOS.value: GooglePhotosProvider(self.token_store),
            CloudProviderType.ONEDRIVE.value: OneDriveProvider(self.token_store),
            CloudProviderType.ICLOUD_LOCAL.value: ICloudLocalProvider(),
            CloudProviderType.APPLE_PHOTOS.value: ApplePhotosProvider(),
        }
        self.accounts: Dict[str, CloudAccount] = {}
        self.load_accounts()

    def available_providers(self) -> list[object]:
        return list(self.providers.values())

    def _save_accounts(self) -> None:
        os.makedirs(os.path.dirname(self._accounts_path), exist_ok=True)
        with open(self._accounts_path, "w", encoding="utf-8") as handle:
            json.dump([account.to_dict() for account in self.accounts.values()], handle, ensure_ascii=False, indent=2)

    def load_accounts(self) -> None:
        self.accounts = {}
        if not os.path.exists(self._accounts_path):
            return
        try:
            with open(self._accounts_path, "r", encoding="utf-8") as handle:
                items = json.load(handle)
        except Exception:
            return
        for item in items:
            try:
                account = CloudAccount.from_dict(item)
            except Exception:
                continue
            self.accounts[account.account_id] = account

    def add_account(self, provider_type: str, parent_widget=None) -> CloudAccount:
        provider = self.providers[provider_type]
        account = provider.authenticate(parent_widget=parent_widget)
        self.accounts[account.account_id] = account
        self._save_accounts()
        return account

    def list_accounts(self) -> list[CloudAccount]:
        return list(self.accounts.values())

    def list_sources(self, account_id: str) -> list[CloudSource]:
        account = self.accounts[account_id]
        provider = self.providers[account.provider]
        return provider.list_sources(account_id)

    def disconnect_account(self, account_id: str) -> None:
        account = self.accounts.get(account_id)
        if not account:
            return
        provider = self.providers.get(account.provider)
        if provider is not None:
            provider.disconnect(account_id)
        del self.accounts[account_id]
        self._save_accounts()

    def scan_source(
        self,
        source: CloudSource,
        mime_filter: Optional[Iterable[str]] = None,
        max_pages: int = 100,
    ) -> list[CloudAsset]:
        provider = self.providers[source.provider]
        assets: list[CloudAsset] = []
        page_token = None
        page_count = 0
        while page_count < max_pages:
            result = provider.list_assets(source, mime_filter=mime_filter, page_token=page_token)
            assets.extend(result.assets)
            page_token = result.next_page_token
            page_count += 1
            if not page_token:
                break
        return assets

    def ensure_local_asset(self, asset: CloudAsset) -> CloudAsset:
        provider = self.providers[asset.provider]
        if asset.download_state == CloudDownloadState.NOT_DOWNLOADED.value:
            provider.download_asset(asset, self.cache_manager)
        elif asset.local_cache_path and os.path.exists(asset.local_cache_path):
            pass
        elif asset.source_uri and os.path.isabs(asset.source_uri) and os.path.exists(asset.source_uri):
            provider.download_asset(asset, self.cache_manager)
        else:
            provider.download_asset(asset, self.cache_manager)
        return asset

    def health_check(self, account_id: str) -> str:
        account = self.accounts.get(account_id)
        if not account:
            return "missing"
        provider = self.providers.get(account.provider)
        if provider is None:
            return "missing"
        return provider.health_check(account_id)
