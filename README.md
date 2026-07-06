# FotoSelector

Desktopová PyQt6 aplikace pro ruční třídění fotografií do virtuálních hromádek, hledání duplicit a bezpečný export lokálních i cloudových položek bez vzdáleného mazání originálů.

## Co aplikace dělá
- načte obrázky z lokálních složek i z podporovaných cloudových zdrojů,
- stáhne cloudové položky do řízené lokální cache, aby se duplicitní analýza opírala o skutečný obrazový obsah,
- umožní fotky přesouvat do bucketů `T1` až `T4`, `TRASH` a `DUPLICITA`,
- umí najít forenzní i vizuální duplicity,
- při finálním provedení přesune lokální soubory nebo exportuje kopie cloudových položek do vybraných cílových složek.

## Podporované cloudy a omezení
- `Synchronizované cloudové složky`: backward-compatible režim nad lokálně synchronizovanými složkami Google Drive Desktop, OneDrive a iCloud Drive.
- `Google Drive API`: reálný desktop OAuth konektor v režimu read-only. Umí listovat a stahovat obrázky z `Můj Disk` i ze sdílených disků, pokud to povolení účtu dovolí.
- `OneDrive API`: reálný desktop OAuth konektor přes Microsoft Graph v režimu read-only.
- `Google Photos`: dva pravdivé režimy. `Google Photos Picker` pro položky, které uživatel sám vybere v oficiálním pickeru Google Photos, a `Google Photos export / Google Takeout` pro lokální exportovanou složku. Aplikace netvrdí plný scan celé knihovny Google Photos.
- `iCloud Drive`: pouze lokálně synchronizovaná složka. Neexistuje falešný webový login.
- `Apple Photos / iCloud Photos na macOS`: pouze read-only lokální knihovna `*.photoslibrary/originals` nebo `Masters`, pokud je na disku dostupná.

## Rozdíl mezi synchronizovanou složkou a API konektorem
- `Synchronizovaná složka` znamená, že soubor už fyzicky leží na lokálním disku nebo jako placeholder v klientovi dané služby.
- `API konektor` znamená přihlášení přes oficiální OAuth tok a explicitní stahování položek do cache FotoSelectoru.
- Placeholder nebo cloud-only soubor se nikdy netváří jako hotový lokální soubor pro analýzu duplicit.

## Rychlý start
```bash
python3 -m pip install -r requirements.txt
python3 KajovoPhotoSelector.py
```

Windows launcher pro lokální použití:
```bat
START.BAT
```

## Konfigurace OAuth

### Google Drive
1. V Google Cloud projektu vytvořte OAuth klient typu Desktop App.
2. Nastavte proměnné prostředí `KPS_GOOGLE_CLIENT_ID` a `KPS_GOOGLE_CLIENT_SECRET`.
3. V aplikaci otevřete `Kájo, pridej cloud` a vyberte `Google Drive API`.

### Google Photos Picker
1. Ve stejném nebo samostatném Google Cloud projektu povolte Google Photos Picker API.
2. Vytvořte OAuth klient typu Desktop App.
3. Nastavte `KPS_GOOGLE_CLIENT_ID` a `KPS_GOOGLE_CLIENT_SECRET`.
4. V aplikaci otevřete `Kájo, pridej cloud`, zvolte `Google Photos` a potom `Google Photos Picker - uzivatelem vybrane polozky`.
5. Aplikace vytvoří Picker session, otevře oficiální `pickerUri` v prohlížeči a po dokončení výběru stáhne jen vybrané položky do své cache.

### OneDrive
1. V Microsoft Entra vytvořte veřejnou klientskou aplikaci pro desktop.
2. Nastavte `KPS_MICROSOFT_CLIENT_ID`.
3. Volitelně nastavte `KPS_MICROSOFT_TENANT_ID`; výchozí hodnota je `common`.

Příklad názvů proměnných je v [cloud_config.example.json](cloud_config.example.json).

## Tokeny, cache a bezpečnost
- OAuth tokeny se neukládají do `Kaja_session.json`.
- Primárně se používá systémový keyring. Když není dostupný, aplikace použije lokální fallback soubor s omezenými právy.
- Cloud cache se ukládá mimo repozitář do uživatelského aplikačního adresáře.
- Cache cesta je deterministická podle `provider/account/asset/revision`.
- Cloudové originály se v této implementaci vzdáleně nemažou ani nepřesouvají.
- Google Photos Picker vyžaduje scope `https://www.googleapis.com/auth/photospicker.mediaitems.readonly`.

## Session
- Session se ukládá jako JSON.
- Po načtení session aplikace potvrzuje lokální roots i uložené cloudové zdroje.
- Cílové složky bucketů se z JSON automaticky neobnovují.
- Pokud cloudový účet není dostupný nebo chybí cache kopie, položka se načte jako nedostupná místo pádu aplikace.

## Ověření
```bash
python3 -m compileall -q KajovoPhotoSelector.py kps_security.py cloud_sync.py cloud_providers tests
python3 -m unittest discover -s tests -v
```

## Struktura repozitáře
- `KajovoPhotoSelector.py`: hlavní GUI aplikace a integrační logika.
- `cloud_providers/`: samostatná cloudová vrstva, OAuth providery, cache a token store.
- `cloud_sync.py`: kompatibilní shim pro lokálně synchronizované složky.
- `kps_security.py`: sanitizace session dat a bezpečnost práce s cestami.
- `tests/`: regresní, bezpečnostní, cloudové a headless E2E testy.
- `docs/`: aktivní dokumentace architektury, bezpečnosti a testování.

## Další dokumentace
- [Architektura](docs/ARCHITECTURE.md)
- [Bezpečnost](docs/SECURITY.md)
- [Testování](docs/TESTING.md)
