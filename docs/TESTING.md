# Testing

## Test layers
- `tests/test_security_regressions.py`: path safety, session root sanitizace a kolize cílových cest.
- `tests/test_app_regressions.py`: kritické regresní větve GUI logiky bez interaktivních dialogů.
- `tests/test_e2e_smoke.py`: headless E2E smoke flow přes toolbar tlačítka a PyQt event loop.

## Lokální příkazy
```bash
python -m compileall -q KajovoPhotoSelector.py kps_security.py tests
python -m unittest discover -s tests -v
```

Headless běh na Windows:
```bash
set QT_QPA_PLATFORM=offscreen
python -m unittest discover -s tests -v
```

Headless běh na Linux/macOS:
```bash
export QT_QPA_PLATFORM=offscreen
python -m unittest discover -s tests -v
```

## Co pokrývají E2E smoke testy
- scan adresáře přes UI tlačítko,
- namapování bucket target path,
- přesun záznamu do bucketu,
- save session,
- load session s potvrzením session roots,
- finální apply s reálným přesunem souboru,
- duplicate flow s automatickým rozhodnutím.

## Co stále vyžaduje ruční smoke test
- vizuální layout a responsivita na různých DPI,
- skutečné audio chování,
- interakce se systémovým košem na konkrétní platformě,
- přehrání `reklama.mp4` přes systémový přehrávač.
