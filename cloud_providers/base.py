from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from .models import CloudAccount, CloudAsset, CloudScanResult, CloudSource


class CloudProviderBase(ABC):
    provider_type: str = ""

    @abstractmethod
    def display_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def authenticate(self, parent_widget=None) -> CloudAccount:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self, account_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_sources(self, account_id: str) -> list[CloudSource]:
        raise NotImplementedError

    @abstractmethod
    def list_assets(
        self,
        source: CloudSource,
        mime_filter: Optional[Iterable[str]] = None,
        page_token: Optional[str] = None,
    ) -> CloudScanResult:
        raise NotImplementedError

    @abstractmethod
    def download_asset(self, asset: CloudAsset, cache_manager) -> object:
        raise NotImplementedError

    @abstractmethod
    def refresh_asset(self, asset: CloudAsset) -> CloudAsset:
        raise NotImplementedError

    @abstractmethod
    def revoke_tokens(self, account_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def health_check(self, account_id: str) -> str:
        raise NotImplementedError
