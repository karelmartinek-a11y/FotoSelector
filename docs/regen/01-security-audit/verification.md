# Verification - Security Audit 01

## Cíl
- Omezit načítání session dat na povolené roots.
- Zabránit tichému přepisu cílových souborů při přesunu.
- Přidat regresní testy pro obě opravy.

## Jak ověřeno
- `python -m py_compile KajovoPhotoSelector.py kps_security.py`
  - očekávání: bez syntax chyb.
- `python -m unittest discover -s tests -v`
  - očekávání: nové security regresní testy projdou.

## Co se změnilo
- Nový modul `kps_security.py`.
- Session load nyní filtruje `images` podle `session_roots` a existence souborů.
- `safe_move_file` nyní používá non-conflicting target path.
- Přidány unit testy v `tests/test_security_regressions.py`.

## Rizika / limity
- Filtrace při loadu může vynechat staré session položky mimo roots (záměrně kvůli bezpečnosti).
- GUI manuální smoke test není v headless CI prováděn.
