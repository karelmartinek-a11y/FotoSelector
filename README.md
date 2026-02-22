# FotoSelector

Desktopová aplikace v PyQt6 pro třídění fotografií do virtuálních hromádek a následné fyzické přesuny/smazání.

## Why
- rychlé ruční třídění fotek v jedné obrazovce,
- kontrola duplicit přes perceptuální hash,
- bezpečnější mazání přes `send2trash` (pokud je dostupné).

## Quickstart
```bash
pip install -r requirements.txt
python KajovoPhotoSelector.py
```

## Configuration
Aplikace nemá ENV konfiguraci; používá:
- `resources/` pro assety,
- `KajovoPhotoSelector.log` pro runtime log,
- `Kaja_session.json` jako výchozí název uložené relace.

## Running
```bash
python KajovoPhotoSelector.py
```

## Testing / checks
```bash
python -m unittest discover -s tests -v
python -m py_compile KajovoPhotoSelector.py kps_security.py
```

## Troubleshooting
- Pokud není `send2trash` nainstalováno, mazání je permanentní (`os.remove`).
- Pokud se nenačtou miniatury, ověřte, že soubory jsou validní obrázky a nejsou poškozené.

## Architecture docs
- [Architecture](docs/ARCHITECTURE.md)
- [Security](docs/SECURITY.md)
- [Contributing](docs/CONTRIBUTING.md)
- Diagramy: `docs/diagrams/*.mmd`
