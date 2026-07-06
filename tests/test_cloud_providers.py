import json
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from KajovoPhotoSelector import ImageRecord, MainWindow, image_record_from_cloud_asset
from cloud_providers.apple_photos import ApplePhotosProvider
from cloud_providers.cache import CloudCacheManager
from cloud_providers.google_drive import GoogleDriveProvider
from cloud_providers.google_photos import GooglePhotosProvider
from cloud_providers.local_sync import CloudLocalSource, detect_cloud_sources
from cloud_providers.manager import CloudServiceManager
from cloud_providers.models import (
    CloudAccount,
    CloudAsset,
    CloudAuthState,
    CloudCapability,
    CloudDownloadState,
    CloudProviderType,
    CloudSource,
)
from cloud_providers.onedrive import OneDriveProvider
from support import APP, DummyProgress, DummySfx, write_test_image


class FakeTokenStore:
    def __init__(self):
        self.tokens = {}
        self.warning_message = ""

    def get_token(self, account_key):
        return self.tokens.get(account_key)

    def set_token(self, account_key, token_value):
        self.tokens[account_key] = token_value

    def delete_token(self, account_key):
        self.tokens.pop(account_key, None)


class FakeGoogleDriveListRequest:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class FakeGoogleDriveFilesResource:
    def __init__(self, pages, calls):
        self.pages = pages
        self.calls = calls

    def list(self, **params):
        page_token = params.get("pageToken")
        self.calls.append(params)
        return FakeGoogleDriveListRequest(self.pages.get(page_token))


class FakeGoogleDriveDrivesResource:
    def list(self, **kwargs):
        return FakeGoogleDriveListRequest({"drives": []})


class FakeGoogleDriveAboutResource:
    def get(self, **kwargs):
        return FakeGoogleDriveListRequest({"user": {"displayName": "Test", "emailAddress": "test@example.com"}})


class FakeGoogleDriveService:
    def __init__(self, pages, calls):
        self._files = FakeGoogleDriveFilesResource(pages, calls)

    def files(self):
        return self._files

    def drives(self):
        return FakeGoogleDriveDrivesResource()

    def about(self):
        return FakeGoogleDriveAboutResource()


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=0):
        yield b"content"


class FakeRequests:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def request(self, method, url, headers=None, json=None, params=None, timeout=None):
        key = (method.upper(), url, tuple(sorted((params or {}).items())))
        self.calls.append(
            {"method": method.upper(), "url": url, "headers": headers, "json": json, "params": params, "timeout": timeout}
        )
        payload = self.payloads[key]
        return FakeResponse(payload.get("status_code", 200), payload["json"])

    def get(self, url, headers=None, timeout=None, stream=False):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout, "stream": stream})
        payload = self.payloads[url]
        return FakeResponse(payload.get("status_code", 200), payload["json"])


class CloudProviderTests(unittest.TestCase):
    def setUp(self):
        self.win = MainWindow(sfx=DummySfx())

    def tearDown(self):
        self.win.deleteLater()

    def test_cloud_asset_to_image_record_maps_cloud_metadata(self):
        asset = CloudAsset(
            provider=CloudProviderType.GOOGLE_DRIVE.value,
            account_id="uzivatel@example.com",
            asset_id="asset-1",
            stable_id="stable-1",
            revision_id="rev-1",
            name="fotka.jpg",
            mime_type="image/jpeg",
            size=123,
            width=10,
            height=20,
            created_time="2026-01-01T00:00:00Z",
            modified_time="2026-01-02T00:00:00Z",
            source_uri="gdrive://file/asset-1",
            download_state=CloudDownloadState.CACHED.value,
            is_read_only=True,
            local_cache_path="/tmp/fotka.jpg",
            original_provider_metadata={"md5Checksum": "abc"},
        )

        record = image_record_from_cloud_asset(asset, record_id=7)

        self.assertTrue(record.is_cloud)
        self.assertEqual(record.cloud_provider, CloudProviderType.GOOGLE_DRIVE.value)
        self.assertEqual(record.cloud_account_id, "uzivatel@example.com")
        self.assertEqual(record.cloud_asset_id, "asset-1")
        self.assertEqual(record.cloud_revision_id, "rev-1")
        self.assertEqual(record.local_cache_path, "/tmp/fotka.jpg")

    def test_token_is_never_saved_to_session_json(self):
        with tempfile.TemporaryDirectory() as root:
            image_path = os.path.join(root, "lokalni.png")
            session_path = os.path.join(root, "session.json")
            write_test_image(image_path)
            fake_token_store = FakeTokenStore()
            fake_token_store.set_token("google_drive:uzivatel@example.com", "tajny-token-123")
            self.win.cloud_manager = CloudServiceManager(
                token_store=fake_token_store,
                cache_manager=CloudCacheManager(root_dir=os.path.join(root, "cache")),
                providers={},
            )
            self.win.cloud_manager.accounts = {
                "uzivatel@example.com": CloudAccount(
                    provider=CloudProviderType.GOOGLE_DRIVE.value,
                    account_id="uzivatel@example.com",
                    display_name="Uzivatel",
                    auth_state=CloudAuthState.AUTHENTICATED.value,
                    is_read_only=True,
                    capabilities=[CloudCapability.AUTHENTICATE.value],
                    metadata={"email": "uzivatel@example.com"},
                )
            }
            self.win.images = [
                ImageRecord(id=1, path=image_path, size=os.path.getsize(image_path), bucket="MAIN"),
            ]

            with patch.object(self.win, "_exec_save_dialog", return_value=session_path):
                self.assertTrue(self.win._do_save())

            with open(session_path, "r", encoding="utf-8") as handle:
                content = handle.read()
            self.assertNotIn("tajny-token-123", content)
            self.assertNotIn("refresh_token", content)

    def test_disconnected_cloud_account_does_not_break_session_load(self):
        with tempfile.TemporaryDirectory() as root:
            session_path = os.path.join(root, "session.json")
            with open(session_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "roots": [],
                        "cloud_sources": [
                            {
                                "provider": CloudProviderType.GOOGLE_DRIVE.value,
                                "account_id": "chybejici@example.com",
                                "source_uri": "gdrive://me",
                            }
                        ],
                        "images": [
                            {
                                "id": 1,
                                "path": "",
                                "size": 123,
                                "bucket": "MAIN",
                                "is_cloud": True,
                                "cloud_provider": CloudProviderType.GOOGLE_DRIVE.value,
                                "cloud_account_id": "chybejici@example.com",
                                "cloud_asset_id": "asset-1",
                                "cloud_revision_id": "rev-1",
                                "cloud_source_uri": "gdrive://file/asset-1",
                                "download_state": CloudDownloadState.CACHED.value,
                            }
                        ],
                    },
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )

            with patch.object(self.win, "_exec_open_dialog", return_value=session_path), \
                patch.object(self.win, "prompt_unsaved", return_value="discard"), \
                patch.object(self.win, "confirm_session_sources", return_value=True), \
                patch("KajovoPhotoSelector.DagmarProgress", DummyProgress), \
                patch.object(self.win, "_coin_per_file"), \
                patch.object(self.win, "toast"):
                self.win.on_load()

            self.assertEqual(len(self.win.images), 1)
            self.assertEqual(self.win.images[0].download_state, CloudDownloadState.UNAVAILABLE.value)

    def test_cloud_cache_path_uses_provider_account_asset_and_revision(self):
        with tempfile.TemporaryDirectory() as root:
            cache_manager = CloudCacheManager(root_dir=root)
            asset = CloudAsset(
                provider="provider-x",
                account_id="ucet-y",
                asset_id="asset-z",
                stable_id="stable-z",
                revision_id="rev-1",
                name="photo.jpg",
                mime_type="image/jpeg",
                size=1,
                width=None,
                height=None,
                created_time="",
                modified_time="",
                source_uri="source",
                download_state=CloudDownloadState.NOT_DOWNLOADED.value,
                is_read_only=True,
            )

            cache_path = cache_manager.build_cache_path(asset)

            self.assertIn("provider-x", cache_path)
            self.assertIn("ucet-y", cache_path)
            self.assertIn("asset-z", cache_path)
            self.assertIn("rev-1", cache_path)

    def test_repeated_download_reuses_unchanged_cache(self):
        with tempfile.TemporaryDirectory() as root:
            cache_manager = CloudCacheManager(root_dir=root)
            asset = CloudAsset(
                provider="provider",
                account_id="ucet",
                asset_id="asset",
                stable_id="asset",
                revision_id="rev",
                name="file.bin",
                mime_type="image/jpeg",
                size=4,
                width=None,
                height=None,
                created_time="",
                modified_time="",
                source_uri="source",
                download_state=CloudDownloadState.NOT_DOWNLOADED.value,
                is_read_only=True,
            )
            calls = {"count": 0}

            def downloader(target_path):
                calls["count"] += 1
                with open(target_path, "wb") as handle:
                    handle.write(b"data")
                return 4

            first = cache_manager.ensure_download(asset, downloader)
            second = cache_manager.ensure_download(asset, downloader)

            self.assertFalse(first.was_cached)
            self.assertTrue(second.was_cached)
            self.assertEqual(calls["count"], 1)

    def test_cloud_only_asset_is_not_sent_to_duplicate_pipeline_as_local_file(self):
        with tempfile.TemporaryDirectory() as root:
            local1 = os.path.join(root, "a.png")
            local2 = os.path.join(root, "b.png")
            write_test_image(local1, color=(1, 2, 3))
            write_test_image(local2, color=(4, 5, 6))
            placeholder = ImageRecord(
                id=1,
                path="gdrive://file/placeholder",
                size=100,
                bucket="MAIN",
                is_cloud=True,
                cloud_provider=CloudProviderType.GOOGLE_DRIVE.value,
                cloud_account_id="acc",
                cloud_asset_id="asset",
                download_state=CloudDownloadState.NOT_DOWNLOADED.value,
            )
            rec2 = ImageRecord(id=2, path=local1, size=os.path.getsize(local1), bucket="MAIN")
            rec3 = ImageRecord(id=3, path=local2, size=os.path.getsize(local2), bucket="MAIN")
            self.win.images = [placeholder, rec2, rec3]
            self.win.image_by_id = {rec.id: rec for rec in self.win.images}
            seen_paths = []

            def fake_signature(path, size):
                seen_paths.append(path)
                return None

            with patch("KajovoPhotoSelector.sampled_file_signature", side_effect=fake_signature), \
                patch("KajovoPhotoSelector.perceptual_hash", return_value=None), \
                patch.object(self.win, "toast"):
                self.win.on_find_duplicates()

            self.assertNotIn("gdrive://file/placeholder", seen_paths)
            self.assertIn(local1, seen_paths)
            self.assertIn(local2, seen_paths)

    def test_google_drive_provider_paginates_results(self):
        calls = []
        pages = {
            None: {
                "files": [
                    {"id": "1", "name": "a.jpg", "mimeType": "image/jpeg", "size": "10", "imageMediaMetadata": {}}
                ],
                "nextPageToken": "page-2",
            },
            "page-2": {
                "files": [
                    {"id": "2", "name": "b.jpg", "mimeType": "image/jpeg", "size": "20", "imageMediaMetadata": {}}
                ]
            },
        }
        provider = GoogleDriveProvider(FakeTokenStore(), service_factory=lambda account_id: FakeGoogleDriveService(pages, calls))
        source = CloudSource(
            provider=CloudProviderType.GOOGLE_DRIVE.value,
            account_id="acc",
            source_id="me",
            name="Muj Disk",
            source_uri="gdrive://me",
            kind="drive",
            is_read_only=True,
        )

        first = provider.list_assets(source)
        second = provider.list_assets(source, page_token=first.next_page_token)

        self.assertEqual(first.next_page_token, "page-2")
        self.assertEqual([asset.asset_id for asset in first.assets + second.assets], ["1", "2"])
        self.assertEqual(len(calls), 2)

    def test_google_drive_provider_filters_only_image_mime_types(self):
        provider = GoogleDriveProvider(
            FakeTokenStore(),
            service_factory=lambda account_id: FakeGoogleDriveService(
                {
                    None: {
                        "files": [
                            {"id": "1", "name": "a.jpg", "mimeType": "image/jpeg", "size": "10", "imageMediaMetadata": {}},
                            {"id": "2", "name": "doc.txt", "mimeType": "text/plain", "size": "5", "imageMediaMetadata": {}},
                        ]
                    }
                },
                [],
            ),
        )
        source = CloudSource(
            provider=CloudProviderType.GOOGLE_DRIVE.value,
            account_id="acc",
            source_id="me",
            name="Muj Disk",
            source_uri="gdrive://me",
            kind="drive",
            is_read_only=True,
        )

        result = provider.list_assets(source)

        self.assertEqual(len(result.assets), 1)
        self.assertEqual(result.assets[0].mime_type, "image/jpeg")

    def test_onedrive_provider_paginates_results(self):
        payloads = {
            "https://graph.microsoft.com/v1.0/drives/drive-1/root/children?$select=id,name,size,createdDateTime,lastModifiedDateTime,webUrl,eTag,cTag,file,photo,image,folder,@microsoft.graph.downloadUrl&$top=200": {
                "json": {
                    "value": [
                        {"id": "1", "name": "a.jpg", "size": 10, "file": {"mimeType": "image/jpeg"}, "image": {"width": 1, "height": 1}}
                    ],
                    "@odata.nextLink": "page-2",
                }
            },
            "page-2": {
                "json": {
                    "value": [
                        {"id": "2", "name": "b.jpg", "size": 20, "file": {"mimeType": "image/jpeg"}, "photo": {"width": 2, "height": 2}}
                    ]
                }
            },
        }
        fake_requests = FakeRequests(payloads)
        provider = OneDriveProvider(FakeTokenStore(), http_session=fake_requests)
        provider._acquire_token = lambda account_id: "token"
        source = CloudSource(
            provider=CloudProviderType.ONEDRIVE.value,
            account_id="acc",
            source_id="drive-1",
            name="Muj OneDrive",
            source_uri="onedrive://me/drive",
            kind="drive",
            is_read_only=True,
        )

        first = provider.list_assets(source)
        second = provider.list_assets(source, page_token=first.next_page_token)

        self.assertEqual(first.next_page_token, "page-2")
        self.assertEqual([asset.asset_id for asset in first.assets + second.assets], ["1", "2"])

    def test_onedrive_provider_recognizes_image_and_photo_metadata(self):
        url = (
            "https://graph.microsoft.com/v1.0/drives/drive-1/root/children"
            "?$select=id,name,size,createdDateTime,lastModifiedDateTime,webUrl,eTag,cTag,file,photo,image,folder,@microsoft.graph.downloadUrl"
            "&$top=200"
        )
        fake_requests = FakeRequests(
            {
                url: {
                    "json": {
                        "value": [
                            {
                                "id": "photo-1",
                                "name": "fotka.bin",
                                "size": 33,
                                "file": {"mimeType": "application/octet-stream"},
                                "photo": {"width": 100, "height": 50},
                            }
                        ]
                    }
                }
            }
        )
        provider = OneDriveProvider(FakeTokenStore(), http_session=fake_requests)
        provider._acquire_token = lambda account_id: "token"
        source = CloudSource(
            provider=CloudProviderType.ONEDRIVE.value,
            account_id="acc",
            source_id="drive-1",
            name="Muj OneDrive",
            source_uri="onedrive://me/drive",
            kind="drive",
            is_read_only=True,
        )

        result = provider.list_assets(source)

        self.assertEqual(len(result.assets), 1)
        self.assertEqual(result.assets[0].width, 100)
        self.assertEqual(result.assets[0].height, 50)

    def test_google_photos_provider_truthfully_reports_limited_mode(self):
        provider = GooglePhotosProvider(FakeTokenStore())
        with tempfile.TemporaryDirectory() as root, patch(
            "PyQt6.QtWidgets.QInputDialog.getItem",
            return_value=("Google Photos export / Google Takeout", True),
        ), patch(
            "PyQt6.QtWidgets.QFileDialog.getExistingDirectory",
            return_value=root,
        ):
            account = provider.authenticate()
            sources = provider.list_sources(account.account_id)

        self.assertIn("export", account.display_name.lower())
        self.assertIn("nikoli plna knihovna", sources[0].limitation_text.lower())

    def test_google_photos_picker_provider_creates_session_and_lists_selected_items(self):
        token_store = FakeTokenStore()
        token_store.set_token(
            "google_photos:google-photos-picker-default",
            json.dumps(
                {
                    "token": "picker-token",
                    "refresh_token": "refresh-token",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                    "scopes": ["https://www.googleapis.com/auth/photospicker.mediaitems.readonly"],
                }
            ),
        )
        payloads = {
            "create_session": {
                "json": {
                    "id": "session-1",
                    "pickerUri": "https://photos.google.com/picker/session-1",
                    "pollingConfig": {"pollInterval": "0s", "timeoutIn": "5s"},
                    "mediaItemsSet": False,
                }
            },
            ("GET", "https://photospicker.googleapis.com/v1/sessions/session-1", ()): {
                "json": {
                    "id": "session-1",
                    "mediaItemsSet": True,
                }
            },
            (
                "GET",
                "https://photospicker.googleapis.com/v1/mediaItems",
                (("pageSize", 100), ("pageToken", None), ("sessionId", "session-1")),
            ): {
                "json": {
                    "mediaItems": [
                        {
                            "id": "picked-1",
                            "createTime": "2026-01-01T00:00:00Z",
                            "mediaFile": {
                                "baseUrl": "https://lh3.googleusercontent.com/p/example",
                                "mimeType": "image/jpeg",
                                "filename": "picked.jpg",
                                "mediaFileMetadata": {"width": 1200, "height": 800},
                            },
                        }
                    ]
                }
            },
        }
        fake_requests = FakeRequests(payloads)
        provider = GooglePhotosProvider(token_store=token_store, http_session=fake_requests)
        provider._load_credentials = lambda account_id: type("Creds", (), {"token": "picker-token"})()
        source = CloudSource(
            provider=CloudProviderType.GOOGLE_PHOTOS.value,
            account_id="google-photos-picker-default",
            source_id="picker-selection",
            name="Picker",
            source_uri="gphotos-picker://selection",
            kind="picker",
            is_read_only=True,
            limitation_text="Uzivatel v Google Photos sam vybere konkretni polozky.",
            metadata={"mode": "picker", "max_item_count": 2000},
        )

        original_request = fake_requests.request

        def request_with_any(method, url, headers=None, json=None, params=None, timeout=None):
            if method.upper() == "POST" and url == "https://photospicker.googleapis.com/v1/sessions":
                fake_requests.calls.append(
                    {"method": method.upper(), "url": url, "headers": headers, "json": json, "params": params, "timeout": timeout}
                )
                payload = fake_requests.payloads["create_session"]
                return FakeResponse(payload.get("status_code", 200), payload["json"])
            return original_request(method, url, headers=headers, json=json, params=params, timeout=timeout)

        fake_requests.request = request_with_any

        with patch("cloud_providers.google_photos.webbrowser.open", return_value=True), \
            patch("cloud_providers.google_photos.time.sleep", return_value=None):
            result = provider.list_assets(source, mime_filter=["image/"])

        self.assertEqual(len(result.assets), 1)
        self.assertEqual(result.assets[0].asset_id, "picked-1")
        self.assertEqual(result.assets[0].width, 1200)
        self.assertIn("vybere", source.limitation_text.lower())

    def test_apple_photos_local_provider_is_read_only(self):
        provider = ApplePhotosProvider()
        with patch(
            "cloud_providers.apple_photos.detect_cloud_sources",
            return_value=[CloudLocalSource(provider="icloud", label="Photos", root="/tmp/photos", category="photos", read_only=True)],
        ):
            sources = provider.list_sources("apple-photos")

        self.assertEqual(len(sources), 1)
        self.assertTrue(sources[0].is_read_only)

    def test_local_cloud_sync_detection_stays_functional(self):
        with tempfile.TemporaryDirectory() as home:
            icloud = os.path.join(home, "Library", "Mobile Documents", "com~apple~CloudDocs")
            gdrive = os.path.join(home, "Library", "CloudStorage", "GoogleDrive-test")
            onedrive = os.path.join(home, "Library", "CloudStorage", "OneDrive-test")
            photos = os.path.join(home, "Pictures", "Kaja.photoslibrary", "originals")
            for path in [icloud, gdrive, onedrive, photos]:
                os.makedirs(path, exist_ok=True)

            sources = detect_cloud_sources(home=home, platform_name="Darwin")

        providers = {source.provider for source in sources}
        self.assertIn("icloud", providers)
        self.assertIn("google-drive", providers)
        self.assertIn("onedrive", providers)


if __name__ == "__main__":
    unittest.main()
