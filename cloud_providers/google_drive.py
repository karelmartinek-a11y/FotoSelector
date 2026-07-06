from __future__ import annotations

import io
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
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseDownload
except Exception:  # pragma: no cover - aplikace má zůstat spustitelná i bez balíků
    Credentials = None
    InstalledAppFlow = None
    Request = None
    build = None
    HttpError = Exception
    MediaIoBaseDownload = None


class GoogleDriveProvider(CloudProviderBase):
    provider_type = CloudProviderType.GOOGLE_DRIVE.value
    readonly_scopes = ["https://www.googleapis.com/auth/drive.readonly"]

    def __init__(self, token_store: TokenStore, service_factory=None):
        self.token_store = token_store
        self.service_factory = service_factory or self._build_service

    def display_name(self) -> str:
        return "Google Drive API"

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
        return InstalledAppFlow is not None and build is not None

    def _config_payload(self) -> dict:
        client_id = os.environ.get("KPS_GOOGLE_CLIENT_ID", "").strip()
        client_secret = os.environ.get("KPS_GOOGLE_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise CloudConfigurationError(
                "Chybi KPS_GOOGLE_CLIENT_ID nebo KPS_GOOGLE_CLIENT_SECRET pro Google Drive OAuth desktop flow."
            )
        return {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }

    def _token_key(self, account_id: str) -> str:
        return f"{self.provider_type}:{account_id}"

    def _account_metadata_key(self, account_id: str) -> str:
        return f"{self.provider_type}:{account_id}:meta"

    def _serialize_credentials(self, credentials) -> str:
        return credentials.to_json()

    def _load_credentials(self, account_id: str):
        if Credentials is None:
            raise CloudConfigurationError("Chybi knihovny google-auth nebo google-api-python-client.")
        raw = self.token_store.get_token(self._token_key(account_id))
        if not raw:
            raise CloudAuthError("Google Drive ucet neni prihlaseny.")
        info = json.loads(raw)
        credentials = Credentials.from_authorized_user_info(info, scopes=self.readonly_scopes)
        if credentials.expired and credentials.refresh_token and Request is not None:
            credentials.refresh(Request())
            self.token_store.set_token(self._token_key(account_id), self._serialize_credentials(credentials))
        return credentials

    def _build_service(self, account_id: str):
        credentials = self._load_credentials(account_id)
        return build("drive", "v3", credentials=credentials, cache_discovery=False)

    def authenticate(self, parent_widget=None) -> CloudAccount:
        if InstalledAppFlow is None:
            raise CloudConfigurationError("Chybi google-auth-oauthlib. Nelze spustit Google Drive OAuth.")
        flow = InstalledAppFlow.from_client_config(self._config_payload(), self.readonly_scopes)
        credentials = flow.run_local_server(port=0, open_browser=True)
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        profile = self._execute_with_retry(lambda: service.about().get(fields="user").execute())
        user = profile.get("user", {}) or {}
        account_id = user.get("emailAddress") or user.get("displayName") or "google-drive"
        self.token_store.set_token(self._token_key(account_id), self._serialize_credentials(credentials))
        return CloudAccount(
            provider=self.provider_type,
            account_id=account_id,
            display_name=user.get("displayName") or account_id,
            auth_state=CloudAuthState.AUTHENTICATED.value,
            is_read_only=True,
            capabilities=self.capabilities(),
            status_text=f"Prihlaseno jako {account_id}",
            metadata={"email": account_id},
        )

    def disconnect(self, account_id: str) -> None:
        self.token_store.delete_token(self._token_key(account_id))

    def _execute_with_retry(self, callback, retries: int = 4):
        delay = 1.0
        for attempt in range(retries):
            try:
                return callback()
            except HttpError as exc:
                status = getattr(getattr(exc, "resp", None), "status", None)
                if status in {429, 500, 502, 503, 504} and attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                if status == 429:
                    raise CloudRateLimitError("Google Drive API vratilo rate limit. Zkuste akci za chvili znovu.") from exc
                raise

    def list_sources(self, account_id: str) -> list[CloudSource]:
        service = self.service_factory(account_id)
        about = self._execute_with_retry(lambda: service.about().get(fields="user").execute())
        sources = [
            CloudSource(
                provider=self.provider_type,
                account_id=account_id,
                source_id="me",
                name="Muj Disk",
                source_uri="gdrive://me",
                kind="drive",
                is_read_only=True,
                limitation_text="Cte pouze metadata a obsah v rezimu read-only.",
                metadata={"space": "drive", "user": about.get("user", {})},
            )
        ]
        drives = self._execute_with_retry(
            lambda: service.drives().list(pageSize=100, fields="drives(id,name),nextPageToken").execute()
        )
        for drive in drives.get("drives", []) or []:
            sources.append(
                CloudSource(
                    provider=self.provider_type,
                    account_id=account_id,
                    source_id=str(drive.get("id", "")),
                    name=str(drive.get("name", "Sdileny disk")),
                    source_uri=f"gdrive://drive/{drive.get('id', '')}",
                    kind="shared_drive",
                    is_read_only=True,
                    limitation_text="Sdileny disk v rezimu read-only.",
                    metadata=dict(drive),
                )
            )
        return sources

    def list_assets(
        self,
        source: CloudSource,
        mime_filter: Optional[Iterable[str]] = None,
        page_token: Optional[str] = None,
    ) -> CloudScanResult:
        service = self.service_factory(source.account_id)
        fields = (
            "nextPageToken, files(id,name,mimeType,size,md5Checksum,imageMediaMetadata,"
            "createdTime,modifiedTime,webViewLink,headRevisionId,driveId,parents)"
        )
        mime_prefixes = list(mime_filter or ["image/"])
        query = "trashed = false and mimeType contains 'image/'"
        params = {
            "fields": fields,
            "pageSize": 100,
            "pageToken": page_token,
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
            "q": query,
            "orderBy": "modifiedTime desc",
        }
        if source.kind == "shared_drive":
            params["corpora"] = "drive"
            params["driveId"] = source.source_id
        else:
            params["corpora"] = "user"
            params["spaces"] = "drive"
        response = self._execute_with_retry(lambda: service.files().list(**params).execute())
        assets: list[CloudAsset] = []
        for item in response.get("files", []) or []:
            mime_type = str(item.get("mimeType", ""))
            if mime_prefixes and not any(mime_type.startswith(prefix) for prefix in mime_prefixes):
                continue
            image_metadata = item.get("imageMediaMetadata", {}) or {}
            assets.append(
                CloudAsset(
                    provider=self.provider_type,
                    account_id=source.account_id,
                    asset_id=str(item.get("id", "")),
                    stable_id=str(item.get("id", "")),
                    revision_id=str(item.get("headRevisionId", "")) or str(item.get("modifiedTime", "")),
                    name=str(item.get("name", "")),
                    mime_type=mime_type,
                    size=int(item.get("size", 0) or 0),
                    width=image_metadata.get("width"),
                    height=image_metadata.get("height"),
                    created_time=str(item.get("createdTime", "")),
                    modified_time=str(item.get("modifiedTime", "")),
                    source_uri=str(item.get("webViewLink") or f"gdrive://file/{item.get('id', '')}"),
                    download_state=CloudDownloadState.NOT_DOWNLOADED.value,
                    is_read_only=True,
                    original_provider_metadata=dict(item),
                )
            )
        return CloudScanResult(
            assets=assets,
            next_page_token=response.get("nextPageToken"),
            listed_count=len(assets),
            limitation_text=source.limitation_text,
        )

    def download_asset(self, asset: CloudAsset, cache_manager: CloudCacheManager):
        service = self.service_factory(asset.account_id)

        def writer(target_path: str) -> int:
            request = service.files().get_media(fileId=asset.asset_id)
            with open(target_path, "wb") as handle:
                downloader = MediaIoBaseDownload(handle, request)
                done = False
                while not done:
                    _, done = self._execute_with_retry(lambda: downloader.next_chunk())
            return os.path.getsize(target_path)

        return cache_manager.ensure_download(asset, writer)

    def refresh_asset(self, asset: CloudAsset) -> CloudAsset:
        service = self.service_factory(asset.account_id)
        item = self._execute_with_retry(
            lambda: service.files().get(
                fileId=asset.asset_id,
                fields="id,name,mimeType,size,imageMediaMetadata,createdTime,modifiedTime,webViewLink,headRevisionId",
                supportsAllDrives=True,
            ).execute()
        )
        image_metadata = item.get("imageMediaMetadata", {}) or {}
        asset.name = str(item.get("name", asset.name))
        asset.mime_type = str(item.get("mimeType", asset.mime_type))
        asset.size = int(item.get("size", asset.size) or 0)
        asset.width = image_metadata.get("width")
        asset.height = image_metadata.get("height")
        asset.created_time = str(item.get("createdTime", asset.created_time))
        asset.modified_time = str(item.get("modifiedTime", asset.modified_time))
        asset.revision_id = str(item.get("headRevisionId", asset.revision_id))
        asset.source_uri = str(item.get("webViewLink", asset.source_uri))
        asset.original_provider_metadata = dict(item)
        return asset

    def revoke_tokens(self, account_id: str) -> None:
        self.disconnect(account_id)

    def health_check(self, account_id: str) -> str:
        try:
            service = self.service_factory(account_id)
            self._execute_with_retry(lambda: service.about().get(fields="user").execute())
            return "ok"
        except Exception:
            return "unavailable"
