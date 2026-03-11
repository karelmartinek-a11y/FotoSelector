# Security

## Co chráníme
- originální fotografie uživatele,
- cílové složky bucketů,
- session JSON s lokálními cestami,
- správnost finálního přesunu nebo smazání.

## Nedůvěryhodné vstupy
- obsah zvolených adresářů,
- načítaný `session.json`,
- lokální filesystem včetně symlinků, junctionů a kolizních cílových souborů.

## Aktivní ochrany v kódu
- Session se deserializuje pouze přes `json`.
- Session roots se normalizují přes `realpath()`, musí existovat a nesmí to být root filesystemu.
- Obrázky ze session se obnovují jen tehdy, pokud jejich cesta opravdu leží uvnitř potvrzených roots.
- Před obnovou session uživatel potvrzuje zdrojové složky uložené v session; není nucen je vybírat znovu.
- Bucket target paths se z JSON automaticky neobnovují.
- Bucket kódy a ID načtených záznamů se sanitizují.
- Přesun souboru používá non-conflicting target path, takže nedochází k tichému přepisu existujícího souboru.
- Po cancelu nebo částečném selhání apply flow nezahazuje slepě celý virtuální stav.

## Zbytková rizika
- Session roots jsou pořád metadata dodaná souborem, takže potvrzení uživatelem je poslední hranice důvěry.
- Pokud není dostupný `send2trash`, mazání padá na `os.remove`, tedy permanentní delete.
- GUI smoke testy běží headless; vizuální kvalita a ergonomie stále vyžadují ruční kontrolu.

## Doporučení pro další změny
- nepřidávat `pickle`, `eval`, `exec` ani automatické načítání cílových bucket cest,
- nové filesystem operace vždy validovat vůči explicitnímu scope,
- při rozšíření session formátu přidat regresní testy současně s implementací.
