# De planner online zetten

Doel: een vaste URL die altijd werkt, ook als je eigen pc uitstaat.
Onderdelen: **GitHub** (de code), **Neon** (de database),
**Streamlit Community Cloud** (draait de app). Alle drie gratis.

Reken op een half uur.

---

## 1. GitHub-repo aanmaken

1. Maak op <https://github.com/new> een repo, bijvoorbeeld
   `data-expo-teamplanner`. Zet hem op **Private** — dat kan Streamlit Cloud
   gewoon deployen.
2. Zet deze bestanden in de repo:
   - `app.py`
   - `requirements.txt`
   - `Data_Expo_programma_9_september_2026.xlsx`
   - `README.md`, `DEPLOY.md`
   - `.gitignore`
   - `.streamlit/secrets.toml.example`
3. Zet deze bestanden er **niet** in (`.gitignore` regelt dat al):
   - `data_expo_keuzes.db` — de keuzes van het team
   - `.streamlit/secrets.toml` — het databasewachtwoord

Uploaden kan via de knop "Add file" > "Upload files" op github.com; je hebt
geen git op je pc nodig.

## 2. Database bij Neon

1. Maak een account op <https://neon.tech>. Inloggen met je GitHub-account is
   het snelst, dan heb je er maar één.
2. Maak een nieuw project aan. Naam mag `data-expo` zijn; kies bij regio iets
   in Europa (Frankfurt bijvoorbeeld). De database heet standaard `neondb` —
   die naam is prima.
3. Direct na het aanmaken laat Neon de **connection string** zien (staat er ook
   later nog, onder "Connect" bij je project). Hij ziet er zo uit:

   ```
   postgresql://neondb_owner:WACHTWOORD@ep-koel-voorbeeld-123456-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require
   ```

   Let op twee dingen:
   - Kies de **pooled** variant: in de hostnaam staat dan `-pooler`. Neon zet
     die meestal standaard aan met een schuifje "Connection pooling".
   - `?sslmode=require` moet erachter staan. Neon zet het er zelf al bij; staat
     het er niet, plak het er dan achter.
4. Kopieer die string in één keer, wachtwoord en al. Bewaar hem even in Kladblok
   — je hebt hem nodig bij onderdeel 3, het deployen.

Tabellen hoef je niet aan te maken: de app doet dat zelf bij de eerste start,
inclusief de sloten die verwijderen tegenhouden.

> **Waarom Neon en niet Supabase?** Werkt allebei; de app ziet alleen een
> Postgres-URL. Neon laat de database automatisch sluimeren en start hem bij de
> eerste bezoeker zelf weer op, terwijl een gratis Supabase-project na een week
> zonder gebruik pauzeert en handmatig wakker gemaakt moet worden. Wil je toch
> Supabase: maak daar een project, pak onder "Connect" de **Connection
> pooling**-string (poort 6543, gebruikersnaam in de vorm
> `postgres.<project-ref>`), zet `?sslmode=require` erachter, en ga verder bij
> onderdeel 3. De rest is identiek.

## 3. App deployen op Streamlit Cloud

1. Ga naar <https://share.streamlit.io> en log in met je GitHub-account.
2. "Create app" > kies je repo, branch `main`, bestand `app.py`.
3. Klik op **Advanced settings** > **Secrets** en zet daar neer:

   ```toml
   [database]
   url = "postgresql://neondb_owner:WACHTWOORD@ep-koel-voorbeeld-123456-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require"
   ```

4. Deploy. Je krijgt een URL als
   `https://data-expo-teamplanner.streamlit.app` — die deel je met het team.

Zonder die secret valt de app terug op een lokaal SQLite-bestand. Op Streamlit
Cloud is dat precies wat je niet wilt (die schijf wordt gewist), dus controleer
na de eerste deploy of een keuze bewaard blijft na "Reboot app".

## 4. De keuzes van nu meenemen (optioneel)

Staat er al iets in `data_expo_keuzes.db` dat je wilt overzetten, dan kan dat
met een klein scriptje op je eigen pc:

```python
import sqlite3
from sqlalchemy import create_engine, text

URL = "postgresql://...?sslmode=require"   # dezelfde URL als hierboven
lokaal = sqlite3.connect("data_expo_keuzes.db")
engine = create_engine(URL)

with engine.begin() as conn:
    for (naam,) in lokaal.execute("SELECT naam FROM personen"):
        conn.execute(
            text("INSERT INTO personen (naam) VALUES (:n) ON CONFLICT DO NOTHING"),
            {"n": naam},
        )
    for naam, sid in lokaal.execute("SELECT naam, session_id FROM keuzes"):
        conn.execute(
            text(
                "INSERT INTO keuzes (naam, session_id) VALUES (:n, :s)"
                " ON CONFLICT DO NOTHING"
            ),
            {"n": naam, "s": sid},
        )
```

Doe dit ná de eerste keer dat de app online heeft gedraaid, want dan bestaan de
tabellen. Draai het maar één keer: verwijderen kan later niet meer.

## Waar je op moet letten

- **De URL is openbaar.** Iedereen met de link kan sessies vastleggen; er zit
  geen inlog op. Op internet is dat iets anders dan op het kantoornetwerk.
  Eén wachtwoord voor de hele app is zo toegevoegd als je dat wilt.
- **Slaapstand.** Een gratis Streamlit-app gaat na een tijd zonder bezoek in
  slaapstand. De eerste bezoeker daarna wacht een halve minuut; de keuzes
  blijven staan, want die zitten bij Neon.
- **Neon laat de database sluimeren** na een paar minuten zonder verbinding.
  Dat is geen storing: de eerste bezoeker daarna wacht een seconde of twee
  langer en daarna loopt het weer. De keuzes blijven staan.
- **Krijg je bij de eerste deploy de fout "Endpoint ID not specified"**, dan
  praat een oudere Postgres-driver met Neon zonder SNI. Zet in dat geval
  `&options=endpoint%3Dep-koel-voorbeeld-123456` achter de URL, met daarin het
  stukje van je eigen hostnaam tot vóór `-pooler`.
- **Het programmabestand** zit in de repo. Verandert het programma, dan upload
  je de nieuwe versie en deployt Streamlit automatisch opnieuw.
