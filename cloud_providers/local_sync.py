from __future__ import annotations

import glob
import os
import platform
from dataclasses import dataclass, asdict
from typing import Iterable, List, Mapping, Optional

from .base import CloudProviderBase
from .cache import CloudCacheManager
from .errors import CloudUnavailableError
from .models import (
    CloudAccount,
    CloudAsset,
    CloudAuthState,
    CloudCapability,
    CloudDownloadState,
    CloudScanResult,
    CloudSource,
    CloudProviderType,
)


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic", ".heif"}


@dataclass
class CloudLocalSource:
    provider: str
    label: str
    root: str
    category: str
    read_only: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


PROVIDER_LABELS = {
    "local": "Lokalni slozka",
    "icloud": "iCloud Drive - lokalni synchronizace",
    "google-drive": "Google Drive - lokalni synchronizace",
    "onedrive": "OneDrive - lokalni synchronizace",
    CloudProviderType.LOCAL_SYNC.value: "Synchronizovane cloudove slozky",
    CloudProviderType.ICLOUD_LOCAL.value: "iCloud Drive - lokalne synchronizovana slozka",
    CloudProviderType.APPLE_PHOTOS.value: "Apple Photos - lokalni knihovna",
    CloudProviderType.GOOGLE_DRIVE.value: "Google Drive API",
    CloudProviderType.GOOGLE_PHOTOS.value: "Google Photos - vybrane nebo exportovane polozky",
    CloudProviderType.ONEDRIVE.value: "OneDrive API",
}


def provider_label(provider: str) -> str:
    return PROVIDER_LABELS.get(provider, provider or "Neznamy zdroj")


def _append_source(
    sources: List[CloudLocalSource],
    seen: set,
    provider: str,
    label: str,
    root: str,
    category: str,
    read_only: bool = False,
) -> None:
    if not root:
        return
    abs_root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(abs_root):
        return
    key = os.path.normcase(abs_root)
    if key in seen:
        return
    seen.add(key)
    sources.append(
        CloudLocalSource(
            provider=provider,
            label=label,
            root=abs_root,
            category=category,
            read_only=read_only,
        )
    )


def _detect_macos_sources(home: str, sources: List[CloudLocalSource], seen: set) -> None:
    _append_source(
        sources,
        seen,
        "icloud",
        "iCloud Drive - Dokumenty",
        os.path.join(home, "Library", "Mobile Documents", "com~apple~CloudDocs"),
        "documents",
        read_only=False,
    )

    photo_patterns = [
        os.path.join(home, "Pictures", "*.photoslibrary", "originals"),
        os.path.join(home, "Pictures", "*.photoslibrary", "Masters"),
    ]
    for pattern in photo_patterns:
        for candidate in glob.glob(pattern):
            name = os.path.basename(os.path.dirname(candidate))
            _append_source(
                sources,
                seen,
                "icloud",
                f"Apple Photos - {name}",
                candidate,
                "photos",
                read_only=True,
            )

    for candidate in glob.glob(os.path.join(home, "Library", "CloudStorage", "GoogleDrive*")):
        name = os.path.basename(candidate)
        _append_source(
            sources,
            seen,
            "google-drive",
            f"Google Drive - {name}",
            candidate,
            "documents",
            read_only=False,
        )

    onedrive_candidates = glob.glob(os.path.join(home, "Library", "CloudStorage", "OneDrive*"))
    onedrive_candidates.append(os.path.join(home, "OneDrive"))
    for candidate in onedrive_candidates:
        name = os.path.basename(candidate.rstrip(os.sep)) or "OneDrive"
        _append_source(
            sources,
            seen,
            "onedrive",
            f"OneDrive - {name}",
            candidate,
            "documents",
            read_only=False,
        )


def _detect_windows_sources(home: str, env: Mapping[str, str], sources: List[CloudLocalSource], seen: set) -> None:
    user_profile = env.get("USERPROFILE", home)
    icloud_candidates = [
        os.path.join(user_profile, "iCloudDrive"),
        os.path.join(user_profile, "Pictures", "iCloud Photos"),
        os.path.join(user_profile, "Pictures", "iCloud Photos", "Photos"),
    ]
    for candidate in icloud_candidates:
        category = "photos" if "Photos" in candidate else "documents"
        _append_source(
            sources,
            seen,
            "icloud",
            "iCloud pro Windows",
            candidate,
            category,
            read_only=False,
        )

    google_candidates = [
        os.path.join(user_profile, "My Drive"),
        os.path.join(user_profile, "Google Drive"),
        os.path.join(user_profile, "Shared drives"),
    ]
    for candidate in google_candidates:
        _append_source(
            sources,
            seen,
            "google-drive",
            "Google Drive Desktop",
            candidate,
            "documents",
            read_only=False,
        )

    onedrive_candidates = [
        env.get("OneDrive", ""),
        env.get("OneDriveConsumer", ""),
        env.get("OneDriveCommercial", ""),
        os.path.join(user_profile, "OneDrive"),
    ]
    for candidate in onedrive_candidates:
        _append_source(
            sources,
            seen,
            "onedrive",
            "OneDrive",
            candidate,
            "documents",
            read_only=False,
        )


def _detect_linux_sources(home: str, sources: List[CloudLocalSource], seen: set) -> None:
    for provider, folder in [
        ("google-drive", "Google Drive"),
        ("onedrive", "OneDrive"),
        ("icloud", "iCloudDrive"),
    ]:
        _append_source(
            sources,
            seen,
            provider,
            provider_label(provider),
            os.path.join(home, folder),
            "documents",
            read_only=False,
        )


def detect_cloud_sources(
    provider: Optional[str] = None,
    home: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    platform_name: Optional[str] = None,
) -> List[CloudLocalSource]:
    env_map = env if env is not None else os.environ
    home_dir = os.path.abspath(os.path.expanduser(home or os.path.expanduser("~")))
    plat = (platform_name or platform.system()).lower()
    sources: List[CloudLocalSource] = []
    seen = set()

    if plat == "darwin":
        _detect_macos_sources(home_dir, sources, seen)
    elif plat == "windows":
        _detect_windows_sources(home_dir, env_map, sources, seen)
    else:
        _detect_linux_sources(home_dir, sources, seen)

    if provider:
        return [src for src in sources if src.provider == provider]
    return sources


def normalize_scan_sources(items: Iterable[Mapping[str, object]]) -> List[CloudLocalSource]:
    normalized: List[CloudLocalSource] = []
    seen = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        provider = item.get("provider")
        label = item.get("label")
        root = item.get("root")
        category = item.get("category")
        read_only = bool(item.get("read_only", False))
        if not isinstance(provider, str) or not provider.strip():
            provider = "local"
        if not isinstance(label, str) or not label.strip():
            label = provider_label(provider)
        if not isinstance(root, str) or not root.strip():
            continue
        if not isinstance(category, str) or not category.strip():
            category = "documents"
        abs_root = os.path.abspath(root)
        key = os.path.normcase(abs_root)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            CloudLocalSource(
                provider=provider,
                label=label,
                root=abs_root,
                category=category,
                read_only=read_only,
            )
        )
    return normalized


def source_for_path(path: str, sources: Iterable[CloudLocalSource]) -> Optional[CloudLocalSource]:
    if not isinstance(path, str) or not path.strip():
        return None
    abs_path = os.path.abspath(path)
    path_key = os.path.normcase(abs_path)
    matches: List[CloudLocalSource] = []
    for source in sources:
        root_key = os.path.normcase(os.path.abspath(source.root))
        if path_key == root_key or path_key.startswith(root_key + os.sep):
            matches.append(source)
    if not matches:
        return None
    return max(matches, key=lambda src: len(src.root))


def _looks_like_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def _is_cloud_placeholder(path: str) -> bool:
    if path.lower().endswith(".icloud"):
        return True
    try:
        if os.path.getsize(path) == 0 and os.path.islink(path):
            return True
    except OSError:
        return True
    return False


class LocalSyncProvider(CloudProviderBase):
    provider_type = CloudProviderType.LOCAL_SYNC.value

    def display_name(self) -> str:
        return "Synchronizovane cloudove slozky"

    def capabilities(self) -> list[str]:
        return [
            CloudCapability.LIST_SOURCES.value,
            CloudCapability.LIST_ASSETS.value,
            CloudCapability.DOWNLOAD.value,
            CloudCapability.LOCAL_SYNC.value,
        ]

    def is_available(self) -> bool:
        return True

    def authenticate(self, parent_widget=None) -> CloudAccount:
        return CloudAccount(
            provider=self.provider_type,
            account_id="local-sync",
            display_name=self.display_name(),
            auth_state=CloudAuthState.LOCAL_ONLY.value,
            is_read_only=False,
            capabilities=self.capabilities(),
            status_text="Bez prihlaseni, pracuje nad lokalne synchronizovanymi slozkami.",
        )

    def disconnect(self, account_id: str) -> None:
        return None

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
                limitation_text="Zdroj je lokalne synchronizovana slozka, ne primo cloudove API.",
                metadata=src.to_dict(),
            )
            for src in detect_cloud_sources()
        ]

    def list_assets(self, source: CloudSource, mime_filter=None, page_token: Optional[str] = None) -> CloudScanResult:
        if not os.path.isdir(source.source_uri):
            raise CloudUnavailableError(f"Zdrojova slozka neni dostupna: {source.source_uri}")
        assets: list[CloudAsset] = []
        for current_root, _dirnames, filenames in os.walk(source.source_uri):
            for filename in filenames:
                path = os.path.join(current_root, filename)
                if not _looks_like_image(path):
                    continue
                download_state = (
                    CloudDownloadState.NOT_DOWNLOADED.value if _is_cloud_placeholder(path) else CloudDownloadState.LOCAL.value
                )
                try:
                    stat_result = os.stat(path)
                    size = int(stat_result.st_size)
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
                        mime_type=f"image/{os.path.splitext(filename)[1].lstrip('.').lower() or 'jpeg'}",
                        size=size,
                        width=None,
                        height=None,
                        created_time="",
                        modified_time="",
                        source_uri=path,
                        download_state=download_state,
                        is_read_only=source.is_read_only,
                        local_cache_path="" if download_state != CloudDownloadState.LOCAL.value else path,
                        original_provider_metadata={"source_root": source.source_uri},
                    )
                )
        return CloudScanResult(assets=assets, listed_count=len(assets), limitation_text=source.limitation_text)

    def download_asset(self, asset: CloudAsset, cache_manager: CloudCacheManager):
        if asset.download_state == CloudDownloadState.NOT_DOWNLOADED.value:
            raise CloudUnavailableError("Soubor je v lokalni synchronizaci jen jako placeholder a neni stazen.")
        if not asset.source_uri or not os.path.exists(asset.source_uri):
            raise CloudUnavailableError("Lokalni synchronizovana kopie neni dostupna.")
        return cache_manager.register_local_asset(asset, asset.source_uri)

    def refresh_asset(self, asset: CloudAsset) -> CloudAsset:
        asset.download_state = (
            CloudDownloadState.LOCAL.value
            if asset.source_uri and os.path.exists(asset.source_uri) and not _is_cloud_placeholder(asset.source_uri)
            else CloudDownloadState.NOT_DOWNLOADED.value
        )
        if asset.download_state == CloudDownloadState.LOCAL.value:
            asset.local_cache_path = asset.source_uri
        return asset

    def revoke_tokens(self, account_id: str) -> None:
        return None

    def health_check(self, account_id: str) -> str:
        return "ok"
