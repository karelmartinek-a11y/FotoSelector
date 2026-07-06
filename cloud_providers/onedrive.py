from __future__ import annotations

import json
import os
import time
from typing import Iterable, Optional

from .base import CloudProviderBase
from .cache import CloudCacheManager
from .errors import CloudAuthError, CloudConfigurationError, CloudRateLimitError
from .models import (
    CloudAccount,
    CloudAsset,
    CloudAuthState,
    CloudCapability,
    CloudDownloadState,
    CloudProviderType,
    CloudScanResult,
    CloudSource,
)
from .token_store import TokenStore

try:  # pragma: no cover - volitelné při importu
    import msal
except Exception:  # pragma: no cover
    msal = None

try:  # pragma: no cover
    import requests
except Exception:  # pragma: no cover
    requests = None


class OneDriveProvider(CloudProviderBase):
    provider_type = CloudProviderType.ONEDRIVE.value
    readonly_scopes = ["Files.Read", "User.Read", "offline_access"]

    def __init__(self, token_store: TokenStore, http_session=None):
        self.token_store = token_store
        self.http_session = http_session or requests

    def display_name(self) -> str:
        return "OneDrive API"

    def capabilities(self) -> list[str]:
        return [
            CloudCapability.AUTHENTICATE.value,
            CloudCapability.LIST_SOURCES.value,
            CloudCapability.LIST_ASSETS.value,
            CloudCapability.DOWNLOAD.value,
            CloudCapability.TOKEN_REFRESH.value,
            CloudCapability.READ_ONLY.value,
        ]

    def is_available(self) -> bool:
        return msal is not None and self.http_session is not None

    def _client_id(self) -> str:
        client_id = os.environ.get("KPS_MICROSOFT_CLIENT_ID", "").strip()
        if not client_id:
            raise CloudConfigurationError("Chybi KPS_MICROSOFT_CLIENT_ID pro OneDrive OAuth.")
        return client_id

    def _authority(self) -> str:
        tenant = os.environ.get("KPS_MICROSOFT_TENANT_ID", "common").strip() or "common"
        return f"https://login.microsoftonline.com/{tenant}"

    def _token_key(self, account_id: str) -> str:
        return f"{self.provider_type}:{account_id}"

    def _make_app(self, cache=None):
        if msal is None:
            raise CloudConfigurationError("Chybi balicek msal.")
        return msal.PublicClientApplication(client_id=self._client_id(), authority=self._authority(), token_cache=cache)

    def _load_cache(self, account_id: str):
        if msal is None:
            raise CloudConfigurationError("Chybi balicek msal.")
        cache = msal.SerializableTokenCache()
        raw = self.token_store.get_token(self._token_key(account_id))
        if raw:
            cache.deserialize(raw)
        return cache

    def _save_cache(self, account_id: str, cache) -> None:
        if cache.has_state_changed:
            self.token_store.set_token(self._token_key(account_id), cache.serialize())

    def authenticate(self, parent_widget=None) -> CloudAccount:
        cache = msal.SerializableTokenCache()
        app = self._make_app(cache=cache)
        result = app.acquire_token_interactive(scopes=self.readonly_scopes)
        if "access_token" not in result:
            raise CloudAuthError(result.get("error_description") or "OneDrive prihlaseni selhalo.")
        profile = self._graph_get("https://graph.microsoft.com/v1.0/me", result["access_token"])
        account_id = str(profile.get("userPrincipalName") or profile.get("id") or "onedrive")
        self._save_cache(account_id, cache)
        return CloudAccount(
            provider=self.provider_type,
            account_id=account_id,
            display_name=str(profile.get("displayName") or account_id),
            auth_state=CloudAuthState.AUTHENTICATED.value,
            is_read_only=True,
            capabilities=self.capabilities(),
            status_text=f"Prihlaseno jako {account_id}",
            metadata={"id": profile.get("id"), "principal_name": account_id},
        )

    def disconnect(self, account_id: str) -> None:
        self.token_store.delete_token(self._token_key(account_id))

    def _acquire_token(self, account_id: str) -> str:
        cache = self._load_cache(account_id)
        app = self._make_app(cache=cache)
        accounts = app.get_accounts()
        result = None
        if accounts:
            result = app.acquire_token_silent(self.readonly_scopes, account=accounts[0])
        if not result:
            raise CloudAuthError("OneDrive ucet vyzaduje znovuprehlaseni.")
        self._save_cache(account_id, cache)
        token = result.get("access_token")
        if not token:
            raise CloudAuthError(result.get("error_description") or "OneDrive token neni dostupny.")
        return token

    def _graph_get(self, url: str, access_token: str) -> dict:
        if self.http_session is None:
            raise CloudConfigurationError("Chybi balicek requests.")
        response = self.http_session.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        if response.status_code in {429, 500, 502, 503, 504}:
            raise CloudRateLimitError("Microsoft Graph je docasne omezeny nebo nedostupny.")
        response.raise_for_status()
        return response.json()

    def _graph_stream(self, url: str, access_token: str, target_path: str) -> int:
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
        response = self.http_session.get(
            url,
            headers=headers,
            timeout=60,
            stream=True,
        )
        if response.status_code in {429, 500, 502, 503, 504}:
            raise CloudRateLimitError("Microsoft Graph je docasne omezeny nebo nedostupny.")
        response.raise_for_status()
        with open(target_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    handle.write(chunk)
        return os.path.getsize(target_path)

    def list_sources(self, account_id: str) -> list[CloudSource]:
        access_token = self._acquire_token(account_id)
        me_drive = self._graph_get("https://graph.microsoft.com/v1.0/me/drive?$select=id,driveType,webUrl", access_token)
        sources = [
            CloudSource(
                provider=self.provider_type,
                account_id=account_id,
                source_id=str(me_drive.get("id", "me")),
                name="Muj OneDrive",
                source_uri="onedrive://me/drive",
                kind=str(me_drive.get("driveType", "drive")),
                is_read_only=True,
                limitation_text="Read-only pristup pres Microsoft Graph.",
                metadata=dict(me_drive),
            )
        ]
        drives = self._graph_get("https://graph.microsoft.com/v1.0/me/drives?$select=id,driveType,name,webUrl", access_token)
        for item in drives.get("value", []) or []:
            drive_id = str(item.get("id", ""))
            if drive_id == sources[0].source_id:
                continue
            sources.append(
                CloudSource(
                    provider=self.provider_type,
                    account_id=account_id,
                    source_id=drive_id,
                    name=str(item.get("name", "Sdileny disk")),
                    source_uri=f"onedrive://drive/{drive_id}",
                    kind=str(item.get("driveType", "drive")),
                    is_read_only=True,
                    limitation_text="Read-only pristup pres Microsoft Graph.",
                    metadata=dict(item),
                )
            )
        return sources

    def list_assets(
        self,
        source: CloudSource,
        mime_filter: Optional[Iterable[str]] = None,
        page_token: Optional[str] = None,
    ) -> CloudScanResult:
        access_token = self._acquire_token(source.account_id)
        url = page_token or (
            f"https://graph.microsoft.com/v1.0/drives/{source.source_id}/root/children"
            "?$select=id,name,size,createdDateTime,lastModifiedDateTime,webUrl,eTag,cTag,file,photo,image,folder,@microsoft.graph.downloadUrl"
            "&$top=200"
        )
        response = self._graph_get(url, access_token)
        assets: list[CloudAsset] = []
        mime_prefixes = list(mime_filter or ["image/"])
        for item in response.get("value", []) or []:
            if item.get("folder"):
                continue
            file_info = item.get("file", {}) or {}
            mime_type = str(file_info.get("mimeType", ""))
            has_image_metadata = bool(item.get("image") or item.get("photo"))
            if mime_prefixes and not any(mime_type.startswith(prefix) for prefix in mime_prefixes):
                if not has_image_metadata:
                    continue
            image_metadata = item.get("image") or item.get("photo") or {}
            assets.append(
                CloudAsset(
                    provider=self.provider_type,
                    account_id=source.account_id,
                    asset_id=str(item.get("id", "")),
                    stable_id=str(item.get("id", "")),
                    revision_id=str(item.get("eTag") or item.get("cTag") or item.get("lastModifiedDateTime", "")),
                    name=str(item.get("name", "")),
                    mime_type=mime_type or "image/unknown",
                    size=int(item.get("size", 0) or 0),
                    width=image_metadata.get("width"),
                    height=image_metadata.get("height"),
                    created_time=str(item.get("createdDateTime", "")),
                    modified_time=str(item.get("lastModifiedDateTime", "")),
                    source_uri=str(item.get("webUrl") or f"onedrive://item/{item.get('id', '')}"),
                    download_state=CloudDownloadState.NOT_DOWNLOADED.value,
                    is_read_only=True,
                    original_provider_metadata=dict(item),
                )
            )
        return CloudScanResult(
            assets=assets,
            next_page_token=response.get("@odata.nextLink"),
            listed_count=len(assets),
            limitation_text=source.limitation_text,
        )

    def download_asset(self, asset: CloudAsset, cache_manager: CloudCacheManager):
        access_token = self._acquire_token(asset.account_id)

        def writer(target_path: str) -> int:
            item = self._graph_get(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{asset.asset_id}"
                "?$select=id,name,@microsoft.graph.downloadUrl",
                access_token,
            )
            download_url = item.get("@microsoft.graph.downloadUrl")
            if download_url:
                return self._graph_stream(download_url, "", target_path)  # download URL je predem autorizovana adresa
            return self._graph_stream(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{asset.asset_id}/content",
                access_token,
                target_path,
            )

        return cache_manager.ensure_download(asset, writer)

    def refresh_asset(self, asset: CloudAsset) -> CloudAsset:
        access_token = self._acquire_token(asset.account_id)
        item = self._graph_get(
            f"https://graph.microsoft.com/v1.0/me/drive/items/{asset.asset_id}"
            "?$select=id,name,size,createdDateTime,lastModifiedDateTime,webUrl,eTag,cTag,file,photo,image",
            access_token,
        )
        image_metadata = item.get("image") or item.get("photo") or {}
        asset.name = str(item.get("name", asset.name))
        asset.size = int(item.get("size", asset.size) or 0)
        asset.width = image_metadata.get("width")
        asset.height = image_metadata.get("height")
        asset.created_time = str(item.get("createdDateTime", asset.created_time))
        asset.modified_time = str(item.get("lastModifiedDateTime", asset.modified_time))
        asset.revision_id = str(item.get("eTag") or item.get("cTag") or asset.revision_id)
        asset.source_uri = str(item.get("webUrl", asset.source_uri))
        asset.original_provider_metadata = dict(item)
        return asset

    def revoke_tokens(self, account_id: str) -> None:
        self.disconnect(account_id)

    def health_check(self, account_id: str) -> str:
        try:
            access_token = self._acquire_token(account_id)
            self._graph_get("https://graph.microsoft.com/v1.0/me?$select=id", access_token)
            return "ok"
        except Exception:
            return "unavailable"
