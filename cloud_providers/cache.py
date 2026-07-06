from __future__ import annotations

import json
import os
import shutil
import time
from typing import Callable, Dict

from .models import CloudAsset, CloudDownloadResult, CloudDownloadState


def app_data_dir(app_name: str = "KajovoPhotoSelector") -> str:
    home = os.path.expanduser("~")
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return os.path.join(root, app_name)
    if os.sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", app_name)
    return os.path.join(home, ".local", "state", app_name)


def cache_root_dir(app_name: str = "KajovoPhotoSelector") -> str:
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or app_data_dir(app_name)
        return os.path.join(root, app_name, "cloud_cache")
    if os.sys.platform == "darwin":
        return os.path.join(app_data_dir(app_name), "cloud_cache")
    return os.path.join(home_cache_dir(app_name), "cloud_cache")


def home_cache_dir(app_name: str = "KajovoPhotoSelector") -> str:
    home = os.path.expanduser("~")
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return os.path.join(root, app_name)
    if os.sys.platform == "darwin":
        return os.path.join(home, "Library", "Caches", app_name)
    return os.path.join(home, ".cache", app_name)


def _safe_segment(value: str, fallback: str) -> str:
    value = (value or "").strip()
    if not value:
        return fallback
    cleaned = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            cleaned.append(char)
        else:
            cleaned.append("_")
    text = "".join(cleaned).strip("._")
    return text[:80] or fallback


class CloudCacheManager:
    def __init__(self, root_dir: str | None = None):
        self.root_dir = root_dir or cache_root_dir()
        os.makedirs(self.root_dir, exist_ok=True)

    def _asset_dir(self, asset: CloudAsset) -> str:
        revision = asset.revision_id or "bez_revize"
        return os.path.join(
            self.root_dir,
            _safe_segment(asset.provider, "provider"),
            _safe_segment(asset.account_id, "ucet"),
            _safe_segment(asset.asset_id or asset.stable_id, "asset"),
            _safe_segment(revision, "revize"),
        )

    def build_cache_path(self, asset: CloudAsset) -> str:
        asset_dir = self._asset_dir(asset)
        name = _safe_segment(asset.name or "soubor", "soubor")
        return os.path.join(asset_dir, name)

    def build_manifest_path(self, asset: CloudAsset) -> str:
        return os.path.join(self._asset_dir(asset), "manifest.json")

    def manifest_for_asset(self, asset: CloudAsset) -> Dict[str, object] | None:
        manifest_path = self.build_manifest_path(asset)
        if not os.path.exists(manifest_path):
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return None

    def is_cached(self, asset: CloudAsset) -> bool:
        file_path = self.build_cache_path(asset)
        manifest = self.manifest_for_asset(asset)
        if not manifest or not os.path.exists(file_path):
            return False
        return (
            manifest.get("provider") == asset.provider
            and manifest.get("account_id") == asset.account_id
            and manifest.get("asset_id") == asset.asset_id
            and manifest.get("revision_id") == (asset.revision_id or "bez_revize")
        )

    def write_manifest(self, asset: CloudAsset, file_path: str, bytes_written: int) -> str:
        manifest_path = self.build_manifest_path(asset)
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        payload = {
            "provider": asset.provider,
            "account_id": asset.account_id,
            "asset_id": asset.asset_id,
            "stable_id": asset.stable_id,
            "revision_id": asset.revision_id or "bez_revize",
            "source_uri": asset.source_uri,
            "name": asset.name,
            "mime_type": asset.mime_type,
            "local_cache_path": file_path,
            "downloaded_at": int(time.time()),
            "bytes_written": bytes_written,
            "metadata": asset.original_provider_metadata,
        }
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return manifest_path

    def ensure_download(
        self,
        asset: CloudAsset,
        downloader: Callable[[str], int],
    ) -> CloudDownloadResult:
        target_path = self.build_cache_path(asset)
        manifest_path = self.build_manifest_path(asset)
        if self.is_cached(asset):
            asset.local_cache_path = target_path
            asset.download_state = CloudDownloadState.CACHED.value
            size = os.path.getsize(target_path) if os.path.exists(target_path) else 0
            return CloudDownloadResult(
                local_path=target_path,
                manifest_path=manifest_path,
                was_cached=True,
                download_state=asset.download_state,
                bytes_written=size,
            )

        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        partial_path = f"{target_path}.part"
        if os.path.exists(partial_path):
            os.remove(partial_path)
        bytes_written = downloader(partial_path)
        os.replace(partial_path, target_path)
        manifest_path = self.write_manifest(asset, target_path, bytes_written)
        asset.local_cache_path = target_path
        asset.download_state = CloudDownloadState.CACHED.value
        return CloudDownloadResult(
            local_path=target_path,
            manifest_path=manifest_path,
            was_cached=False,
            download_state=asset.download_state,
            bytes_written=bytes_written,
        )

    def register_local_asset(self, asset: CloudAsset, local_path: str) -> CloudDownloadResult:
        asset.local_cache_path = local_path
        asset.download_state = CloudDownloadState.LOCAL.value
        manifest_path = self.write_manifest(asset, local_path, os.path.getsize(local_path) if os.path.exists(local_path) else 0)
        return CloudDownloadResult(
            local_path=local_path,
            manifest_path=manifest_path,
            was_cached=True,
            download_state=asset.download_state,
            bytes_written=os.path.getsize(local_path) if os.path.exists(local_path) else 0,
        )

    def cleanup(self, max_age_days: int = 30) -> int:
        removed = 0
        cutoff = time.time() - max(1, max_age_days) * 86400
        for current_root, dirnames, filenames in os.walk(self.root_dir, topdown=False):
            for filename in filenames:
                path = os.path.join(current_root, filename)
                try:
                    if os.path.getmtime(path) < cutoff:
                        os.remove(path)
                        removed += 1
                except OSError:
                    continue
            for dirname in dirnames:
                path = os.path.join(current_root, dirname)
                try:
                    if not os.listdir(path):
                        shutil.rmtree(path)
                except OSError:
                    continue
        return removed
