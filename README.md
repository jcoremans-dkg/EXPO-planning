
# Data Expo Teamplanner

## Bestanden
- `app.py`
- `requirements.txt`
- `Data_Expo_programma_9_september_2026.xlsx`

Zet deze drie bestanden in dezelfde map.

## Waar de keuzes worden opgeslagen

Standaard in `data_expo_keuzes.db`, een SQLite-bestand naast `app.py`. Staat er
een Postgres-URL in `.streamlit/secrets.toml` onder `[database] url`, dan
gebruikt de app die in plaats daarvan. Zo werkt dezelfde code lokaal en in de
cloud. Zie `DEPLOY.md` voor het online zetten.

## Starten

Open een terminal in de map en voer uit:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Daarna opent de planner in je browser.

## Samen gebruiken

Als je deze app op één gedeelde server of pc draait, kunnen meerdere mensen tegelijk dezelfde planner openen.
De keuzes worden opgeslagen in:

`data_expo_keuzes.db`

Daardoor ziet iedereen dezelfde planning.

Voor gebruik op verschillende locaties/apparaten moet de Streamlit-app bereikbaar zijn via een gedeelde URL.

## Spelregels

De planner is opzettelijk "append-only":

- **Een vastgelegde keuze blijft staan.** Er is geen knop om een keuze, een
  persoon of de hele planning te verwijderen. De database weigert het zelf ook:
  drie triggers (`keuzes_niet_verwijderen`, `keuzes_niet_wijzigen`,
  `personen_niet_verwijderen`) blokkeren elke `DELETE` en `UPDATE`.
  Omdat vastleggen definitief is, vraagt de app eerst om een bevestiging.
- **Je kiest alleen voor jezelf.** Je stelt eenmalig in wie je bent; daarna
  kiest de app altijd voor die persoon. Er is geen dropdown meer waarmee je
  namens een collega sessies kunt vastleggen.

Wil je toch iets herstellen, dan kan dat alleen buiten de app om, met een
SQLite-tool: `DROP TRIGGER keuzes_niet_verwijderen;`, opruimen, en de trigger
daarna opnieuw laten aanmaken door de app te herstarten. Maak eerst een kopie
van `data_expo_keuzes.db`.
