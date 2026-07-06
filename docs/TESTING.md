# Testování

## Test vrstvy
- `tests/test_security_regressions.py`: bezpečnost roots, sanitizace session a bezpečné cílové cesty.
- `tests/test_app_regressions.py`: kritické větve GUI logiky a session chování.
- `tests/test_cloud_providers.py`: cloud cache, session bez tokenů, Google Photos Picker flow, omezení Google Photos, Google Drive a OneDrive stránkování.
- `tests/test_e2e_smoke.py`: headless smoke test toolbar toku.

## Povinné příkazy
```bash
python3 -m compileall -q KajovoPhotoSelector.py kps_security.py cloud_sync.py cloud_providers tests
python3 -m unittest discover -s tests -v
```

## Co pokrývají cloudové testy
- token se nikdy neukládá do session JSON,
- převod `CloudAsset -> ImageRecord`,
- session load s odpojeným cloudovým účtem,
- deterministická cache `provider/account/asset/revision`,
- opakovaný download bez zbytečného stahování,
- ochrana proti předání cloud-only položky do duplicate pipeline,
- stránkování a filtrování Google Drive,
- stránkování a metadata OneDrive,
- vytvoření Google Photos Picker session a načtení uživatelem vybraných položek,
- pravdivé omezení Google Photos,
- read-only režim Apple Photos,
- funkčnost detekce lokálních synchronizovaných zdrojů.

## Doporučený ruční smoke test
1. Spusťte aplikaci bez OAuth proměnných a ověřte, že lokální režim funguje.
2. Přidejte lokální adresář, najděte duplicity a proveďte přesun.
3. Otevřete `Kájo, pridej cloud`, projděte dialog účtů a zdrojů a ověřte, že bez přihlašovacích údajů neukazuje falešný úspěch.
4. Máte-li nakonfigurovaný Google Photos Picker, přihlaste se, dokončete výběr v oficiálním pickeru a ověřte vznik lokální cache.
5. Máte-li nakonfigurovaný Google Drive nebo OneDrive účet, přihlaste se, vyberte zdroj a ověřte vznik lokální cache.
6. U cloudové položky v bucketu ověřte, že `Kájo, proveď to` exportuje kopii a nesmaže vzdálený originál.
