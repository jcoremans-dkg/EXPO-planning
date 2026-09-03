
import html
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, event, text

EXCEL_FILE = "Data_Expo_programma_9_september_2026.xlsx"
DB_FILE = "data_expo_keuzes.db"
MAX_PERSONEN = 8

st.set_page_config(
    page_title="Data Expo Teamplanner",
    page_icon="📊",
    layout="wide"
)

# -----------------------------
# Data laden
# -----------------------------
@st.cache_data
def load_programma():
    df = pd.read_excel(EXCEL_FILE, skiprows=4)

    # Verwachte kolommen uit het Excelbestand:
    # Start, Eind, Course / sessie, Zaal / locatie, Programmaonderdeel, Bron
    df = df.dropna(subset=["Start", "Eind", "Course / sessie"]).copy()

    df["Start"] = df["Start"].astype(str).str[:5]
    df["Eind"] = df["Eind"].astype(str).str[:5]

    df = df.reset_index(drop=True)
    df["session_id"] = df.index + 1
    return df


data = load_programma()


# -----------------------------
# Database
# -----------------------------
# Lokaal: een SQLite-bestand naast de app.
# In de cloud: Postgres, via [database] url in .streamlit/secrets.toml.
def db_url():
    try:
        uit_secrets = st.secrets["database"]["url"]

        if uit_secrets:
            return str(uit_secrets)
    except Exception:
        pass

    return f"sqlite:///{DB_FILE}"


@st.cache_resource
def get_engine():
    url = db_url()

    if url.startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False}
        )

        @event.listens_for(engine, "connect")
        def _zet_wal(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")

        return engine

    return create_engine(url, pool_pre_ping=True, pool_recycle=300)


def is_postgres():
    return get_engine().dialect.name == "postgresql"


# Eerdere versies zetten sloten op de tabellen die verwijderen tegenhielden.
# Keuzes mogen weer weg, dus die sloten worden opgeruimd.
OUDE_SLOTEN = [
    ("keuzes_niet_verwijderen", "keuzes"),
    ("keuzes_niet_wijzigen", "keuzes"),
    ("personen_niet_verwijderen", "personen"),
]


@st.cache_resource
def init_db():
    """Maakt de tabellen aan. Loopt eenmaal per serverproces."""
    with get_engine().begin() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS personen (
                naam TEXT PRIMARY KEY
            )
        """)

        conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS keuzes (
                naam TEXT NOT NULL,
                session_id INTEGER NOT NULL,
                PRIMARY KEY (naam, session_id)
            )
        """)

        if is_postgres():
            for slot, tabel in OUDE_SLOTEN:
                conn.exec_driver_sql(
                    f"DROP TRIGGER IF EXISTS {slot} ON {tabel}"
                )

            conn.exec_driver_sql(
                "DROP FUNCTION IF EXISTS weiger_wijziging()"
            )
        else:
            for slot, _tabel in OUDE_SLOTEN:
                conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS {slot}")


def get_personen():
    with get_engine().connect() as conn:
        return [
            row[0]
            for row in conn.execute(
                text("SELECT naam FROM personen ORDER BY naam")
            )
        ]


def add_persoon(naam):
    naam = naam.strip()

    if not naam:
        return False, "Vul een naam in."

    personen = get_personen()

    if naam.lower() in [p.lower() for p in personen]:
        return False, "Deze naam bestaat al."

    if len(personen) >= MAX_PERSONEN:
        return False, f"Er kunnen maximaal {MAX_PERSONEN} personen meedoen."

    with get_engine().begin() as conn:
        conn.execute(
            text("INSERT INTO personen (naam) VALUES (:naam)"),
            {"naam": naam}
        )

    return True, f"{naam} is toegevoegd."


def get_keuzes(naam=None):
    with get_engine().connect() as conn:
        if naam:
            rows = conn.execute(
                text(
                    "SELECT naam, session_id FROM keuzes WHERE naam = :naam"
                ),
                {"naam": naam}
            )
        else:
            rows = conn.execute(
                text("SELECT naam, session_id FROM keuzes")
            )

        return [(row[0], int(row[1])) for row in rows]


def voeg_keuze_toe(naam, session_id):
    with get_engine().begin() as conn:
        resultaat = conn.execute(
            text("""
                INSERT INTO keuzes (naam, session_id)
                VALUES (:naam, :session_id)
                ON CONFLICT DO NOTHING
            """),
            {"naam": naam, "session_id": int(session_id)}
        )

    return resultaat.rowcount > 0


def verwijder_keuze(naam, session_id):
    with get_engine().begin() as conn:
        conn.execute(
            text("""
                DELETE FROM keuzes
                WHERE naam = :naam AND session_id = :session_id
            """),
            {"naam": naam, "session_id": int(session_id)}
        )


def wis_keuzes_persoon(naam):
    with get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM keuzes WHERE naam = :naam"),
            {"naam": naam}
        )


def tijd_naar_minuten(tijd):
    uur, minuut = map(int, tijd.split(":")[:2])
    return uur * 60 + minuut


def overlapt(sessie_a, sessie_b):
    return (
        tijd_naar_minuten(sessie_a["Start"])
        < tijd_naar_minuten(sessie_b["Eind"])
        and
        tijd_naar_minuten(sessie_b["Start"])
        < tijd_naar_minuten(sessie_a["Eind"])
    )


def conflicten_voor_persoon(naam, nieuwe_session_id):
    gekozen_ids = {
        session_id
        for _, session_id in get_keuzes(naam)
    }

    if nieuwe_session_id in gekozen_ids:
        return []

    nieuwe_sessie = data.loc[
        data["session_id"] == nieuwe_session_id
    ].iloc[0]

    conflicten = []

    for session_id in gekozen_ids:
        bestaande = data.loc[
            data["session_id"] == session_id
        ].iloc[0]

        if overlapt(nieuwe_sessie, bestaande):
            conflicten.append(
                f'{bestaande["Start"]}–{bestaande["Eind"]}: '
                f'{bestaande["Course / sessie"]}'
            )

    return conflicten


init_db()


# -----------------------------
# Styling
# -----------------------------
st.markdown("""
<style>
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 3rem;
}

[data-testid="stMetricValue"] {
    font-size: 1.6rem;
}

.session-card {
    border: 1px solid rgba(128,128,128,.25);
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 8px;
}

.time-label {
    font-weight: 700;
    font-size: 1.05rem;
}

.room-label {
    opacity: .7;
    font-size: .9rem;
}

.name-pill {
    display: inline-block;
    padding: 3px 9px;
    border-radius: 999px;
    border: 1px solid rgba(128,128,128,.35);
    margin: 2px 4px 2px 0;
    font-size: .85rem;
}

.name-pill-active {
    border-color: rgba(34,197,94,.9);
    font-weight: 700;
}

.ts-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
    margin: 4px 0 10px 0;
    font-size: .88rem;
    opacity: .85;
}

.ts-legend-item {
    display: inline-flex;
    align-items: center;
    gap: 7px;
}

.ts-swatch {
    width: 14px;
    height: 14px;
    border-radius: 4px;
    display: inline-block;
}

.ts-swatch-green {
    background: rgba(34,197,94,.22);
    border: 1px solid rgba(34,197,94,.85);
}

.ts-swatch-grey {
    background: rgba(128,128,128,.10);
    border: 1px solid rgba(128,128,128,.45);
}

.ts-slot {
    margin-bottom: 18px;
}

.ts-slot-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    padding: 4px 2px 6px 2px;
    border-bottom: 1px solid rgba(128,128,128,.25);
    margin-bottom: 6px;
}

.ts-slot-time {
    font-weight: 800;
    font-size: 1.05rem;
    letter-spacing: .02em;
}

.ts-slot-count {
    font-size: .82rem;
    opacity: .65;
    white-space: nowrap;
}

.ts-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 9px 12px;
    margin-bottom: 5px;
    border-radius: 10px;
    border: 1px solid rgba(128,128,128,.20);
    border-left: 4px solid rgba(128,128,128,.40);
}

.ts-row.ts-covered {
    background: rgba(34,197,94,.14);
    border-color: rgba(34,197,94,.35);
    border-left: 4px solid #22c55e;
}

.ts-info {
    flex: 1 1 320px;
    min-width: 0;
}

.ts-title {
    font-weight: 600;
    line-height: 1.3;
}

.ts-meta {
    font-size: .82rem;
    opacity: .65;
    margin-top: 2px;
}

.ts-names {
    flex: 0 1 auto;
    text-align: right;
}

.ts-empty {
    font-size: .82rem;
    opacity: .45;
    font-style: italic;
}
</style>
""", unsafe_allow_html=True)


# -----------------------------
# Header
# -----------------------------
st.title("Data Expo – Teamplanner")
st.caption(
    "Woensdag 9 september 2026 · Kies per persoon de sessies. "
    "De tijdlijn laat direct zien wie waarheen gaat."
)

personen = get_personen()

c1, c2, c3 = st.columns(3)
c1.metric("Teamleden", f"{len(personen)} / {MAX_PERSONEN}")
c2.metric("Sessies", len(data))
c3.metric("Gemaakte keuzes", len(get_keuzes()))


# -----------------------------
# Wie ben je?
# -----------------------------
st.subheader("1. Wie ben je?")

personen = get_personen()
actieve_persoon = st.session_state.get("ik")

if actieve_persoon and actieve_persoon not in personen:
    del st.session_state["ik"]
    actieve_persoon = None

if not actieve_persoon:
    st.caption(
        "Kies eerst je eigen naam. Je kiest daarna alleen sessies voor "
        "jezelf — niemand plant iets voor iemand anders in."
    )

    if personen:
        col_naam, col_ok = st.columns(
            [4, 1],
            vertical_alignment="bottom"
        )

        with col_naam:
            gekozen_naam = st.selectbox(
                "Ik ben",
                personen,
                key="naam_selectie"
            )

        with col_ok:
            if st.button(
                "Dit ben ik",
                type="primary",
                width="stretch"
            ):
                st.session_state["ik"] = gekozen_naam
                st.rerun()

    with st.expander(
        "Ik sta er nog niet bij",
        expanded=not personen
    ):
        with st.form("persoon_toevoegen", clear_on_submit=True):
            nieuwe_naam = st.text_input(
                "Je naam",
                placeholder="Bijvoorbeeld Jens"
            )

            if st.form_submit_button(
                "Toevoegen en verder",
                type="primary"
            ):
                ok, melding = add_persoon(nieuwe_naam)

                if ok:
                    st.session_state["ik"] = nieuwe_naam.strip()
                    st.rerun()
                else:
                    st.warning(melding)

    st.info(
        "Zodra je je naam hebt gekozen, zie je het volledige tijdschema."
    )
    st.stop()

st.success(f"Je kiest als **{actieve_persoon}**.")

with st.expander("Ben jij dit niet?"):
    st.caption(
        "Gebruik dit alleen als je per ongeluk de verkeerde naam koos, of "
        "als een collega dit apparaat overneemt. Kiezen voor iemand anders "
        "is niet de bedoeling."
    )

    if st.button("Wissel van persoon"):
        del st.session_state["ik"]
        st.rerun()


# -----------------------------
# Keuze bevestigen
# -----------------------------
@st.dialog("Deze sessies overlappen")
def bevestig_keuze(naam, session_id):
    sessie = data.loc[data["session_id"] == session_id].iloc[0]

    st.markdown(f'**{sessie["Course / sessie"]}**')
    st.caption(
        f'{sessie["Start"]}–{sessie["Eind"]} · '
        f'{sessie["Zaal / locatie"]}'
    )

    conflicten = conflicten_voor_persoon(naam, session_id)

    if conflicten:
        st.warning("Dit valt over een sessie die je al gekozen hebt:")

        for conflict in conflicten:
            st.write(f"• {conflict}")

    st.caption(
        "Je kunt allebei kiezen en later alsnog een van de twee weghalen."
    )

    col_ja, col_nee = st.columns(2)

    with col_ja:
        if st.button(
            "Toch kiezen",
            type="primary",
            width="stretch"
        ):
            voeg_keuze_toe(naam, session_id)
            del st.session_state["te_bevestigen"]
            st.rerun()

    with col_nee:
        if st.button(
            "Annuleren",
            width="stretch"
        ):
            del st.session_state["te_bevestigen"]
            st.rerun()


# -----------------------------
# Programma
# -----------------------------
st.divider()
st.subheader(f"2. Sessies kiezen voor {actieve_persoon}")
st.caption(
    "Klik op \"Gaat hierheen\" om je aan te melden. Klik nog eens op een "
    "gekozen sessie om je keuze weer weg te halen."
)

with st.expander("Al mijn keuzes in één keer wissen"):
    st.caption(
        f"Dit haalt alleen de keuzes van {actieve_persoon} weg; die van je "
        "collega's blijven staan. Je kunt daarna gewoon opnieuw kiezen."
    )

    if st.button("Wis al mijn keuzes"):
        wis_keuzes_persoon(actieve_persoon)
        st.rerun()

zoekterm = st.text_input(
    "Zoeken",
    placeholder="Zoek op sessie, zaal of tijd..."
).strip().lower()

te_bevestigen = st.session_state.get("te_bevestigen")

if te_bevestigen is not None:
    bevestig_keuze(actieve_persoon, int(te_bevestigen))

keuzes_actief = {
    session_id
    for _, session_id in get_keuzes(actieve_persoon)
}

alle_keuzes = get_keuzes()

namen_per_sessie = {}
for naam, session_id in alle_keuzes:
    namen_per_sessie.setdefault(session_id, []).append(naam)


gefilterd = data.copy()

if zoekterm:
    mask = (
        gefilterd["Course / sessie"]
        .astype(str)
        .str.lower()
        .str.contains(zoekterm, na=False)
        |
        gefilterd["Zaal / locatie"]
        .astype(str)
        .str.lower()
        .str.contains(zoekterm, na=False)
        |
        gefilterd["Start"]
        .astype(str)
        .str.lower()
        .str.contains(zoekterm, na=False)
    )

    gefilterd = gefilterd[mask]


for _, row in gefilterd.iterrows():
    session_id = int(row["session_id"])
    gekozen = session_id in keuzes_actief
    bezoekers = namen_per_sessie.get(session_id, [])

    col_time, col_session, col_action = st.columns(
        [1.2, 6, 1.7],
        vertical_alignment="center"
    )

    with col_time:
        st.markdown(
            f"**{row['Start']}**  \n"
            f"{row['Eind']}"
        )

    with col_session:
        st.markdown(
            f"**{row['Course / sessie']}**"
        )
        st.caption(row["Zaal / locatie"])

        if bezoekers:
            st.markdown(
                " ".join(
                    f"`{naam}`"
                    for naam in bezoekers
                )
            )

    with col_action:
        if gekozen:
            if st.button(
                "✓ Gekozen",
                key=f"keuze_{actieve_persoon}_{session_id}",
                type="primary",
                width="stretch",
                help="Klik om je keuze weer weg te halen."
            ):
                verwijder_keuze(actieve_persoon, session_id)
                st.rerun()
        elif st.button(
            "Gaat hierheen",
            key=f"keuze_{actieve_persoon}_{session_id}",
            width="stretch"
        ):
            if conflicten_voor_persoon(actieve_persoon, session_id):
                st.session_state["te_bevestigen"] = session_id
            else:
                voeg_keuze_toe(actieve_persoon, session_id)

            st.rerun()

    st.divider()


# -----------------------------
# Tijdschema (volledig programma)
# -----------------------------
st.divider()
st.subheader("3. Tijdschema")

alle_keuzes = get_keuzes()

namen_per_sessie = {}
for naam, session_id in alle_keuzes:
    namen_per_sessie.setdefault(int(session_id), []).append(naam)

for session_id in namen_per_sessie:
    namen_per_sessie[session_id].sort(key=str.lower)

gedekt_totaal = len(namen_per_sessie)

t1, t2, t3 = st.columns(3)
t1.metric("Sessies in programma", len(data))
t2.metric("Minimaal 1 bezoeker", gedekt_totaal)
t3.metric("Nog niemand", len(data) - gedekt_totaal)

st.markdown(
    '<div class="ts-legend">'
    '<span class="ts-legend-item">'
    '<span class="ts-swatch ts-swatch-green"></span>'
    'Wordt door minimaal één persoon bezocht</span>'
    '<span class="ts-legend-item">'
    '<span class="ts-swatch ts-swatch-grey"></span>'
    'Nog niemand naartoe</span>'
    '</div>',
    unsafe_allow_html=True
)

weergave = st.radio(
    "Weergave",
    ["Volledig programma", "Alleen bezochte sessies", "Alleen niet-bezochte sessies"],
    horizontal=True,
    key="tijdschema_weergave"
)

alleen_mijn_tijdslots = st.checkbox(
    "Toon alleen tijdsloten waarin iemand van het team iets doet",
    value=False,
    key="tijdschema_alleen_actieve_slots"
)

schema = data.sort_values(
    ["Start", "Eind", "Course / sessie"]
).copy()

for (start, eind), tijdgroep in schema.groupby(["Start", "Eind"], sort=True):
    rijen = []
    gedekt_in_slot = 0

    for _, row in tijdgroep.iterrows():
        session_id = int(row["session_id"])
        bezoekers = namen_per_sessie.get(session_id, [])

        if bezoekers:
            gedekt_in_slot += 1

        if weergave == "Alleen bezochte sessies" and not bezoekers:
            continue

        if weergave == "Alleen niet-bezochte sessies" and bezoekers:
            continue

        titel = html.escape(str(row["Course / sessie"]))

        meta_delen = [
            str(row[kolom])
            for kolom in ("Zaal / locatie", "Type")
            if kolom in row.index and pd.notna(row[kolom])
        ]
        meta = html.escape(" · ".join(meta_delen))

        if bezoekers:
            pillen = "".join(
                '<span class="name-pill{extra}">{naam}</span>'.format(
                    extra=" name-pill-active" if naam == actieve_persoon else "",
                    naam=html.escape(naam)
                )
                for naam in bezoekers
            )
        else:
            pillen = '<span class="ts-empty">nog niemand</span>'

        rijen.append(
            '<div class="ts-row {klasse}">'
            '<div class="ts-info"><div class="ts-title">{titel}</div>'
            '<div class="ts-meta">{meta}</div></div>'
            '<div class="ts-names">{pillen}</div>'
            '</div>'.format(
                klasse="ts-covered" if bezoekers else "ts-open",
                titel=titel,
                meta=meta,
                pillen=pillen
            )
        )

    if alleen_mijn_tijdslots and gedekt_in_slot == 0:
        continue

    if not rijen:
        continue

    st.markdown(
        '<div class="ts-slot">'
        '<div class="ts-slot-head">'
        '<span class="ts-slot-time">{start} – {eind}</span>'
        '<span class="ts-slot-count">{gedekt} van {totaal} bezocht</span>'
        '</div>{rijen}</div>'.format(
            start=html.escape(start),
            eind=html.escape(eind),
            gedekt=gedekt_in_slot,
            totaal=len(tijdgroep),
            rijen="".join(rijen)
        ),
        unsafe_allow_html=True
    )


# -----------------------------
# Overzichtstabel
# -----------------------------
with st.expander("Volledig planningsoverzicht als tabel"):
    alle_keuzes = get_keuzes()

    if alle_keuzes:
        overzicht = pd.DataFrame(
            alle_keuzes,
            columns=["Naam", "session_id"]
        ).merge(
            data,
            on="session_id",
            how="left"
        )

        overzicht = overzicht[
            [
                "Start",
                "Eind",
                "Course / sessie",
                "Zaal / locatie",
                "Naam"
            ]
        ].sort_values(
            ["Start", "Course / sessie", "Naam"]
        )

        st.dataframe(
            overzicht,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.write("Nog geen keuzes.")
