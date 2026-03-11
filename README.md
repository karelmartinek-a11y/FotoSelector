# FotoSelector

Desktopová PyQt6 aplikace pro ruční třídění fotografií do virtuálních hromádek, hledání duplicit a následný fyzický přesun nebo smazání.

## Co aplikace dělá
- načte obrázky z vybraných adresářů do hlavního pohledu,
- umožní je přesouvat do bucketů `T1` až `T4`, `TRASH` a `DUPLICITA`,
- umí najít vizuální duplicity pomocí perceptuálního hashe,
- při finálním provedení přesune soubory do cílových složek nebo je smaže / pošle do koše.

## Rychlý start
```bash
pip install -r requirements.txt
python KajovoPhotoSelector.py
```

Windows launcher pro lokální použití:
```bat
START.BAT
```

## Session a bezpečnost
- Session se ukládá jako JSON.
- Po načtení session aplikace zobrazí zdrojové složky uložené v session a chce jejich potvrzení. Uživatel je nemusí vybírat znovu.
- Cílové složky bucketů se z JSON z bezpečnostních důvodů automaticky neobnovují. Po načtení session se musí znovu namapovat v UI.
- Při přesunu se cílový soubor nikdy tiše nepřepíše; při kolizi dostane suffix ` (1)`, ` (2)` atd.

## Testování
Základní lokální ověření:
```bash
python -m compileall -q KajovoPhotoSelector.py kps_security.py tests
python -m unittest discover -s tests -v
```

Headless GUI a E2E smoke testy používají:
```bash
set QT_QPA_PLATFORM=offscreen
```

Podrobnosti jsou v [docs/TESTING.md](docs/TESTING.md).

## Struktura repozitáře
- `KajovoPhotoSelector.py`: hlavní GUI aplikace a doménová logika.
- `kps_security.py`: sanitizace session dat a path safety helpery.
- `resources/`: obrázky, ikony, zvuky a reklamní video.
- `tests/`: regresní a E2E smoke testy.
- `docs/`: aktivní dokumentace architektury, bezpečnosti a testování.

## Další dokumentace
- [Architektura](docs/ARCHITECTURE.md)
- [Bezpečnost](docs/SECURITY.md)
- [Testování](docs/TESTING.md)
- [Přispívání](docs/CONTRIBUTING.md)
