# Contributing

## Dev setup
```bash
pip install -r requirements.txt
```

## Local checks
```bash
python -m py_compile KajovoPhotoSelector.py kps_security.py
python -m unittest discover -s tests -v
```

## Coding standards
- Python 4-space indentation.
- Czech UI texty a logy držet konzistentní.
- Nové file IO cesty stavět přes `BASE_DIR`/`resource_path`.

## CI local parity
CI spouští stejné příkazy jako výše (compile + unit tests).
