# Contributing

## Lokální setup
```bash
pip install -r requirements.txt
```

Na Windows lze použít i `START.BAT`, který vytvoří `venv` a aplikaci spustí.

## Povinné lokální kontroly
```bash
python -m compileall -q KajovoPhotoSelector.py kps_security.py tests
python -m unittest discover -s tests -v
```

Pro headless GUI testy:
```bash
set QT_QPA_PLATFORM=offscreen
```

## Coding rules
- Python: 4 mezery, bez tabů.
- Zachovávat české UI texty a konzistentní formulace v dialozích a logu.
- Nové file-system cesty stavět přes `BASE_DIR` a `resource_path`.
- U operací s session nebo fyzickými přesuny vždy myslet na bezpečnostní omezení popsaná v `docs/SECURITY.md`.

## Repo hygiene
- Do repa nepatří runtime logy, session JSON, `__pycache__`, lokální `venv`, build artefakty ani ZIP exporty.
- Aktivní dokumentace je v `README.md` a v top-level souborech `docs/*.md`; jednorázové audity a dočasné podklady sem nepatří.

## CI parity
GitHub Actions spouští stejný compile check a `unittest` suite jako lokální workflow.
