import glob
import os
import platform
from dataclasses import asdict, dataclass
from typing import Iterable, List, Mapping, Optional


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
    "icloud": "iCloud",
    "google-drive": "Google Drive",
    "onedrive": "OneDrive",
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
                f"iCloud Fotky - {name}",
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
            f"{provider_label(provider)}",
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
