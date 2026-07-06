from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CloudProviderType(str, Enum):
    LOCAL_SYNC = "local_sync"
    GOOGLE_DRIVE = "google_drive"
    GOOGLE_PHOTOS = "google_photos"
    ONEDRIVE = "onedrive"
    ICLOUD_LOCAL = "icloud_local"
    APPLE_PHOTOS = "apple_photos"


class CloudAuthState(str, Enum):
    LOCAL_ONLY = "local_only"
    NEEDS_AUTH = "needs_auth"
    AUTHENTICATED = "authenticated"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class CloudCapability(str, Enum):
    LIST_SOURCES = "list_sources"
    LIST_ASSETS = "list_assets"
    DOWNLOAD = "download"
    AUTHENTICATE = "authenticate"
    TOKEN_REFRESH = "token_refresh"
    LOCAL_SYNC = "local_sync"
    READ_ONLY = "read_only"
    IMPORT_EXPORT_ONLY = "import_export_only"


class CloudDownloadState(str, Enum):
    LOCAL = "local"
    CACHED = "cached"
    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


@dataclass
class CloudAccount:
    provider: str
    account_id: str
    display_name: str
    auth_state: str
    is_read_only: bool = True
    capabilities: List[str] = field(default_factory=list)
    limitation_text: str = ""
    status_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CloudAccount":
        return cls(
            provider=str(data.get("provider", "")),
            account_id=str(data.get("account_id", "")),
            display_name=str(data.get("display_name", "")),
            auth_state=str(data.get("auth_state", CloudAuthState.DISCONNECTED.value)),
            is_read_only=bool(data.get("is_read_only", True)),
            capabilities=[str(item) for item in data.get("capabilities", []) if isinstance(item, str)],
            limitation_text=str(data.get("limitation_text", "")),
            status_text=str(data.get("status_text", "")),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class CloudSource:
    provider: str
    account_id: str
    source_id: str
    name: str
    source_uri: str
    kind: str
    is_read_only: bool
    limitation_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CloudSource":
        return cls(
            provider=str(data.get("provider", "")),
            account_id=str(data.get("account_id", "")),
            source_id=str(data.get("source_id", "")),
            name=str(data.get("name", "")),
            source_uri=str(data.get("source_uri", "")),
            kind=str(data.get("kind", "folder")),
            is_read_only=bool(data.get("is_read_only", True)),
            limitation_text=str(data.get("limitation_text", "")),
            metadata=dict(data.get("metadata", {}) or {}),
        )


@dataclass
class CloudAsset:
    provider: str
    account_id: str
    asset_id: str
    stable_id: str
    revision_id: str
    name: str
    mime_type: str
    size: int
    width: Optional[int]
    height: Optional[int]
    created_time: str
    modified_time: str
    source_uri: str
    download_state: str
    is_read_only: bool
    local_cache_path: str = ""
    original_provider_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CloudAsset":
        return cls(
            provider=str(data.get("provider", "")),
            account_id=str(data.get("account_id", "")),
            asset_id=str(data.get("asset_id", "")),
            stable_id=str(data.get("stable_id", data.get("asset_id", ""))),
            revision_id=str(data.get("revision_id", "")),
            name=str(data.get("name", "")),
            mime_type=str(data.get("mime_type", "")),
            size=int(data.get("size", 0) or 0),
            width=data.get("width"),
            height=data.get("height"),
            created_time=str(data.get("created_time", "")),
            modified_time=str(data.get("modified_time", "")),
            source_uri=str(data.get("source_uri", "")),
            download_state=str(data.get("download_state", CloudDownloadState.NOT_DOWNLOADED.value)),
            is_read_only=bool(data.get("is_read_only", True)),
            local_cache_path=str(data.get("local_cache_path", "")),
            original_provider_metadata=dict(data.get("original_provider_metadata", {}) or {}),
        )


@dataclass
class CloudDownloadResult:
    local_path: str
    manifest_path: str
    was_cached: bool
    download_state: str
    bytes_written: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CloudScanResult:
    assets: List[CloudAsset]
    next_page_token: Optional[str] = None
    listed_count: int = 0
    limitation_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assets": [asset.to_dict() for asset in self.assets],
            "next_page_token": self.next_page_token,
            "listed_count": self.listed_count,
            "limitation_text": self.limitation_text,
        }
