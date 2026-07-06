from __future__ import annotations

import json
import os
import time
import uuid
import webbrowser
from typing import Iterable, Optional

from .base import CloudProviderBase
from .cache import CloudCacheManager
from .errors import CloudAuthError, CloudConfigurationError, CloudUnavailableError, CloudUserActionRequired
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
except Exception:  # pragma: no cover
    Credentials = None
    InstalledAppFlow = None
    Request = None

try:  # pragma: no cover
    import requests
except Exception:  # pragma: no cover
    requests = None


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".tif", ".tiff"}


def _parse_duration_seconds(value: str, fallback: float) -> float:
    if not isinstance(value, str) or not value.endswith("s"):
        return fallback
    try:
        return max(0.0, float(value[:-1]))
    except ValueError:
        return fallback


class GooglePhotosProvider(CloudProviderBase):
    provider_type = CloudProviderType.GOOGLE_PHOTOS.value
    picker_scope = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"

    def __init__(self, token_store: TokenStore | None = None, http_session=None):
        self.token_store = token_store or TokenStore()
        self.http_session = http_session or requests

    def display_name(self) -> str:
        return "Google Photos - picker nebo export"

    def capabilities(self) -> list[str]:
        return [
            CloudCapability.AUTHENTICATE.value,
            CloudCapability.LIST_SOURCES.value,
            CloudCapability.LIST_ASSETS.value,
            CloudCapability.DOWNLOAD.value,
            CloudCapability.READ_ONLY.value,
            CloudCapability.IMPORT_EXPORT_ONLY.value,
        ]

    def is_available(self) -> bool:
        return True

    def _oauth_scopes(self) -> list[str]:
        return [self.picker_scope]

    def _config_payload(self) -> dict:
        client_id = os.environ.get("KPS_GOOGLE_CLIENT_ID", "").strip()
        client_secret = os.environ.get("KPS_GOOGLE_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise CloudConfigurationError(
                "Chybi KPS_GOOGLE_CLIENT_ID nebo KPS_GOOGLE_CLIENT_SECRET pro Google Photos Picker OAuth."
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

    def _load_credentials(self, account_id: str):
        if Credentials is None:
            raise CloudConfigurationError("Chybi knihovny google-auth nebo google-auth-oauthlib.")
        raw = self.token_store.get_token(self._token_key(account_id))
        if not raw:
            raise CloudAuthError("Google Photos Picker ucet neni prihlaseny.")
        info = json.loads(raw)
        credentials = Credentials.from_authorized_user_info(info, scopes=self._oauth_scopes())
        if credentials.expired and credentials.refresh_token and Request is not None:
            credentials.refresh(Request())
            self.token_store.set_token(self._token_key(account_id), credentials.to_json())
        return credentials

    def authenticate(self, parent_widget=None) -> CloudAccount:
        from PyQt6.QtWidgets import QFileDialog, QInputDialog  # noqa: PLC0415

        modes = [
            "Google Photos Picker - uzivatelem vybrane polozky",
            "Google Photos export / Google Takeout",
        ]
        chosen_mode, ok = QInputDialog.getItem(
            parent_widget,
            "Google Photos",
            "Vyberte podporovany rezim:",
            modes,
            0,
            False,
        )
        if not ok or not chosen_mode:
            raise CloudUnavailableError("Vyber rezimu Google Photos byl zrusen.")

        if chosen_mode == modes[1]:
            folder = QFileDialog.getExistingDirectory(
                parent_widget,
                "Vyberte export Google Photos nebo slozku Google Takeout",
            )
            if not folder:
                raise CloudUnavailableError("Nebyla vybrana zadna exportovana slozka Google Photos.")
            root = os.path.abspath(folder)
            return CloudAccount(
                provider=self.provider_type,
                account_id=f"google-photos-export::{root}",
                display_name=f"Google Photos export - {os.path.basename(root) or 'vyber'}",
                auth_state=CloudAuthState.LOCAL_ONLY.value,
                is_read_only=True,
                capabilities=self.capabilities(),
                limitation_text=(
                    "Pouze importovane nebo exportovane polozky. "
                    "Tento rezim neskenuje celou cloudovou knihovnu Google Photos."
                ),
                status_text="Importni rezim nad lokalnim exportem Google Photos / Google Takeout.",
                metadata={"mode": "import_export", "root": root},
            )

        if InstalledAppFlow is None:
            raise CloudConfigurationError("Chybi google-auth-oauthlib. Nelze spustit Google Photos Picker OAuth.")
        flow = InstalledAppFlow.from_client_config(self._config_payload(), self._oauth_scopes())
        credentials = flow.run_local_server(port=0, open_browser=True)
        account_id = "google-photos-picker-default"
        self.token_store.set_token(self._token_key(account_id), credentials.to_json())
        return CloudAccount(
            provider=self.provider_type,
            account_id=account_id,
            display_name="Google Photos Picker",
            auth_state=CloudAuthState.AUTHENTICATED.value,
            is_read_only=True,
            capabilities=self.capabilities(),
            limitation_text=(
                "Oficialni Google Photos Picker spristupni pouze polozky, ktere uzivatel v Google Photos sam vybere. "
                "Nejde o plny scan cele knihovny."
            ),
            status_text="Prihlaseni pripraveno pro Google Photos Picker.",
            metadata={"mode": "picker", "max_item_count": 2000},
        )

    def disconnect(self, account_id: str) -> None:
        if account_id.startswith("google-photos-export::"):
            return
        self.token_store.delete_token(self._token_key(account_id))

    def list_sources(self, account_id: str) -> list[CloudSource]:
        if account_id.startswith("google-photos-export::"):
            root = account_id.split("::", 1)[1]
            return [
                CloudSource(
                    provider=self.provider_type,
                    account_id=account_id,
                    source_id=root,
                    name="Google Photos export",
                    source_uri=root,
                    kind="import_export",
                    is_read_only=True,
                    limitation_text="Pouze importovane nebo exportovane polozky, nikoli plna knihovna Google Photos.",
                    metadata={"mode": "import_export", "root": root},
                )
            ]
        return [
            CloudSource(
                provider=self.provider_type,
                account_id=account_id,
                source_id="picker-selection",
                name="Google Photos Picker - uzivatelem vybrane polozky",
                source_uri="gphotos-picker://selection",
                kind="picker",
                is_read_only=True,
                limitation_text=(
                    "Pri kazdem scanu se otevre oficialni Google Photos Picker a uzivatel vybere konkretni polozky."
                ),
                metadata={"mode": "picker", "max_item_count": 2000},
            )
        ]

    def _iter_local_export_assets(self, source: CloudSource) -> list[CloudAsset]:
        assets: list[CloudAsset] = []
        for current_root, _dirnames, filenames in os.walk(source.source_uri):
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in IMAGE_EXTENSIONS:
                    continue
                path = os.path.join(current_root, filename)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
                assets.append(
                    CloudAsset(
                        provider=self.provider_type,
                        account_id=source.account_id,
                        asset_id=path,
                        stable_id=path,
                        revision_id=str(int(os.path.getmtime(path))) if os.path.exists(path) else "0",
                        name=filename,
                        mime_type=f"image/{ext.lstrip('.') or 'jpeg'}",
                        size=size,
                        width=None,
                        height=None,
                        created_time="",
                        modified_time="",
                        source_uri=path,
                        download_state=CloudDownloadState.LOCAL.value,
                        is_read_only=True,
                        local_cache_path=path,
                        original_provider_metadata={"mode": "import_export"},
                    )
                )
        return assets

    def _auth_headers(self, account_id: str) -> dict[str, str]:
        credentials = self._load_credentials(account_id)
        return {"Authorization": f"Bearer {credentials.token}"}

    def _request_json(self, method: str, url: str, account_id: str, json_body=None, params=None) -> dict:
        if self.http_session is None:
            raise CloudConfigurationError("Chybi balicek requests.")
        response = self.http_session.request(
            method,
            url,
            headers=self._auth_headers(account_id),
            json=json_body,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json() if hasattr(response, "json") else {}

    def _create_picker_session(self, source: CloudSource) -> dict:
        request_id = str(uuid.uuid4())
        return self._request_json(
            "POST",
            "https://photospicker.googleapis.com/v1/sessions",
            source.account_id,
            json_body={"pickingConfig": {"maxItemCount": str(source.metadata.get("max_item_count", 2000))}},
            params={"requestId": request_id},
        )

    def _poll_picker_until_ready(self, source: CloudSource, session: dict) -> dict:
        current = session
        timeout_seconds = _parse_duration_seconds(
            ((session.get("pollingConfig") or {}).get("timeoutIn", "300s")),
            300.0,
        )
        end_time = time.time() + max(30.0, timeout_seconds)
        while not current.get("mediaItemsSet"):
            if time.time() >= end_time:
                raise CloudUserActionRequired("Vyber Google Photos vcas neskoncil. Spustte scan znovu.")
            poll_interval = _parse_duration_seconds(
                ((current.get("pollingConfig") or {}).get("pollInterval", "3s")),
                3.0,
            )
            time.sleep(max(1.0, poll_interval))
            current = self._request_json(
                "GET",
                f"https://photospicker.googleapis.com/v1/sessions/{session['id']}",
                source.account_id,
            )
        return current

    def _list_picker_media_items(
        self,
        source: CloudSource,
        session_id: str,
        mime_filter: Optional[Iterable[str]],
        page_token: Optional[str] = None,
    ) -> CloudScanResult:
        response = self._request_json(
            "GET",
            "https://photospicker.googleapis.com/v1/mediaItems",
            source.account_id,
            params={"sessionId": session_id, "pageSize": 100, "pageToken": page_token},
        )
        assets: list[CloudAsset] = []
        mime_prefixes = list(mime_filter or ["image/"])
        for item in response.get("mediaItems", []) or []:
            media_file = item.get("mediaFile", {}) or {}
            mime_type = str(media_file.get("mimeType", ""))
            if mime_prefixes and not any(mime_type.startswith(prefix) for prefix in mime_prefixes):
                continue
            metadata = media_file.get("mediaFileMetadata", {}) or {}
            assets.append(
                CloudAsset(
                    provider=self.provider_type,
                    account_id=source.account_id,
                    asset_id=str(item.get("id", "")),
                    stable_id=str(item.get("id", "")),
                    revision_id=str(item.get("createTime", "")),
                    name=str(media_file.get("filename", item.get("id", ""))),
                    mime_type=mime_type or "image/unknown",
                    size=0,
                    width=metadata.get("width"),
                    height=metadata.get("height"),
                    created_time=str(item.get("createTime", "")),
                    modified_time=str(item.get("createTime", "")),
                    source_uri=str(media_file.get("baseUrl", "")),
                    download_state=CloudDownloadState.NOT_DOWNLOADED.value,
                    is_read_only=True,
                    original_provider_metadata={"mode": "picker", "session_id": session_id, **dict(item)},
                )
            )
        return CloudScanResult(
            assets=assets,
            next_page_token=response.get("nextPageToken"),
            listed_count=len(assets),
            limitation_text=source.limitation_text,
        )

    def list_assets(self, source: CloudSource, mime_filter=None, page_token: Optional[str] = None) -> CloudScanResult:
        if source.kind == "import_export":
            assets = self._iter_local_export_assets(source)
            return CloudScanResult(
                assets=assets,
                listed_count=len(assets),
                limitation_text="Pouze importovane nebo exportovane polozky, nikoli plna knihovna Google Photos.",
            )

        session = self._create_picker_session(source)
        picker_uri = session.get("pickerUri")
        if not picker_uri:
            raise CloudUnavailableError("Google Photos Picker nevydal pickerUri.")
        webbrowser.open(picker_uri)
        ready_session = self._poll_picker_until_ready(source, session)
        return self._list_picker_media_items(
            source,
            ready_session["id"],
            mime_filter=mime_filter,
            page_token=page_token,
        )

    def download_asset(self, asset: CloudAsset, cache_manager: CloudCacheManager):
        if asset.original_provider_metadata.get("mode") == "import_export":
            if not os.path.exists(asset.source_uri):
                raise CloudUnavailableError("Exportovana polozka Google Photos neni dostupna.")
            return cache_manager.register_local_asset(asset, asset.source_uri)

        if self.http_session is None:
            raise CloudConfigurationError("Chybi balicek requests.")

        def writer(target_path: str) -> int:
            base_url = str(asset.source_uri)
            if not base_url:
                raise CloudUnavailableError("Google Photos Picker nevratil baseUrl pro stazeni.")
            response = self.http_session.get(
                f"{base_url}=d",
                headers=self._auth_headers(asset.account_id),
                timeout=60,
                stream=True,
            )
            response.raise_for_status()
            with open(target_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        handle.write(chunk)
            return os.path.getsize(target_path)

        return cache_manager.ensure_download(asset, writer)

    def refresh_asset(self, asset: CloudAsset) -> CloudAsset:
        if asset.original_provider_metadata.get("mode") == "import_export":
            if asset.source_uri and os.path.exists(asset.source_uri):
                asset.local_cache_path = asset.source_uri
                asset.download_state = CloudDownloadState.LOCAL.value
            else:
                asset.download_state = CloudDownloadState.UNAVAILABLE.value
            return asset
        return asset

    def revoke_tokens(self, account_id: str) -> None:
        self.disconnect(account_id)

    def health_check(self, account_id: str) -> str:
        if account_id.startswith("google-photos-export::"):
            root = account_id.split("::", 1)[1]
            return "ok" if os.path.isdir(root) else "unavailable"
        try:
            self._load_credentials(account_id)
            return "ok"
        except Exception:
            return "unavailable"
