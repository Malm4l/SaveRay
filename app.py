"""SaveRay - FM27 player table from a local SQLite snapshot.

Run:  streamlit run app.py
Data: a snapshot database created by import_save.py in the same folder.
"""
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from roles_engine import (GROUP_TO_POSITIONS, attr_key, load_catalog,
                          score_player, score_role)

HERE = Path(__file__).resolve().parent
DB = HERE / "players.db"
SNAP_DIR = HERE / "snapshots"
ACTIVE_FILE = HERE / "active_snapshot.txt"
GAMES_DIR = (Path.home() / "Documents" / "Sports Interactive"
             / "Football Manager 27" / "games")

TECHNICAL = ["corners", "crossing", "dribbling", "finishing", "first_touch",
             "free_kick_taking", "heading", "long_shots", "long_throws",
             "marking", "passing", "penalty_taking", "tackling", "technique"]
MENTAL = ["aggression", "anticipation", "bravery", "composure", "concentration",
          "decisions", "determination", "flair", "leadership", "off_the_ball",
          "positioning", "teamwork", "vision", "work_rate"]
PHYSICAL = ["acceleration", "agility", "balance", "jumping_reach",
            "natural_fitness", "pace", "stamina", "strength"]
GOALKEEPING = ["aerial_reach", "command_of_area", "communication", "eccentricity",
               "handling", "kicking", "one_on_ones", "punching", "reflexes",
               "rushing_out", "throwing"]
HIDDEN = ["consistency", "dirtiness", "important_matches", "injury_proneness",
          "versatility"]
PERSONALITY = ["adaptability", "ambition", "loyalty", "pressure",
               "professionalism", "sportsmanship", "temperament", "controversy"]
# Attributes where a HIGHER value is WORSE (everything else: higher = better)
BAD_WHEN_HIGH = {"dirtiness", "injury_proneness", "controversy"}
GROUPS = {"Technical": TECHNICAL, "Mental": MENTAL, "Physical": PHYSICAL,
          "Goalkeeping": GOALKEEPING, "Hidden": HIDDEN}
ALL_ATTRS = TECHNICAL + MENTAL + PHYSICAL + GOALKEEPING + HIDDEN
POSITIONS = ["gk", "sw", "dl", "dc", "dr", "wbl", "dm", "wbr",
             "ml", "mc", "mr", "aml", "amc", "amr", "stc"]

st.set_page_config(page_title="SaveRay — FM27 Save Reader", layout="wide")

STRINGS = {
    "en": {
        "saves_in_folder": "Saves in the FM27 games folder",
        "modified": "modified",
        "import_this": "Import this save",
        "importing": "Importing {name}, please wait...",
        "import_failed": "Import failed. ",
        "auto_loaded": "Newest save loaded automatically, {name}",
        "auto_failed": "The newest save could not be loaded yet, so "
                       "the previous data is still shown.",
        "auto_note": "Your save updates automatically when its "
                     "file changes, manual import is only needed "
                     "the first time.",
        "snapshot_note": "A snapshot is the imported copy of a "
                         "save that SaveRay reads, separate from "
                         "the original save file.",
        "games_not_found": "The FM27 games folder was not found in its "
                           "standard location, so the save list cannot "
                           "be shown.",
        "saved_snapshots": "Saved snapshots",
        "imported_word": "imported",
        "use_snapshot": "Use this snapshot",
        "tagline": "X-ray your FM27 save. Every player, every "
                   "attribute, including the hidden ones.",
        "no_snapshot": "No snapshot yet. Import one of your saves "
                       "from the Save menu in the left sidebar.",
        "imported_cap": "Imported",
        "players_word": "players",
        "reset_all": "Reset all filters",
        "reset_help": "Return every filter below to its default value.",
        "search_name": "Search player name",
        "all_word": "(all)",
        "none_word": "(none)",
        "club": "Club",
        "pos_contains": "Natural position contains",
        "age": "Age",
        "min_ca": "Minimum CA",
        "min_pa": "Minimum PA",
        "attr_filter": "Attribute filter",
        "attr_min": "Minimum attribute value",
        "role_min": "Minimum role score",
        "role_min_help": "Uses the Overall score, the final value "
                         "after the position factor (explained in "
                         "the player profile).",
        "role_combine": "Pick one role filter or both. When both are "
                        "picked, a player must pass the minimum score "
                        "in both roles at the same time.",
        "match_rest": "match the current filters",
        "col_name": "Name",
        "col_positions": "Positions",
        "col_height": "Height",
        "col_value": "Transfer Value",
        "col_wage": "Wage",
        "col_contract": "Contract Ends",
        "profile_header": "Player profile",
        "no_players": "No players match the current filters.",
        "select_player": "Select player",
        "warn_caption": "\u26a0 = an attribute where higher is worse, "
                        "not better (in the Hidden group, Dirtiness "
                        "and Injury Proneness).",
        "personality_caption": "Every personality attribute is better "
                               "when higher, except Controversy "
                               "\u26a0, where higher is worse because "
                               "the player courts controversy and "
                               "trouble with the media.",
        "pos_ratings": "Position ratings (1\u201320)",
        "no_position": "No position is rated above 1.",
        "feet_label": "Feet",
        "best_role_header": "Best Role (split by phase)",
        "metric_help": "Attribute fit {fit} \u00b7 at {pos} ({r}/20)",
        "col_position": "Position",
        "no_role": "No role qualifies, because no position is rated "
                   "15 or higher.",
        "info_box": "**How to read these two numbers.**\n\n"
                    "- **Fit** measures how well the player's "
                    "*attributes* suit the role. It is pure skill and "
                    "ignores position.\n"
                    "- **Overall** is the final score after *position* "
                    "is taken into account. Fit is reduced when the "
                    "role sits away from the positions the player is "
                    "comfortable in.\n\n"
                    "When the role sits on a natural position rated 20 "
                    "out of 20, there is no reduction and Overall "
                    "equals Fit. The less comfortable the position, "
                    "the bigger the reduction, so Overall never "
                    "exceeds Fit. Best role lists are ranked by "
                    "**Overall** because that is what is realistic on "
                    "the pitch. A role is only rated at positions of "
                    "15 or higher. Below that, the player is treated "
                    "as unable to play there.",
        "formula_caption": "Formula detail. Fit = (weighted average "
                           "of the role attributes \u2212 1) "
                           "\u00f7 19 \u00d7 100, with priority "
                           "attributes weighted \u00d73 and "
                           "supporting \u00d71. Overall = Fit "
                           "\u00d7 (0.6 + 0.4 \u00d7 position "
                           "rating \u00f7 20).",
        "expander_title": "All roles (79) \u2014 full list per phase",
        "expander_caption": "A blank Overall means the role sits on "
                            "a position rated below 15, so it is not "
                            "scored.",
        "col_phase": "Phase",
    },
    "id": {
        "saves_in_folder": "Save di folder games FM27",
        "modified": "diubah",
        "import_this": "Impor save ini",
        "importing": "Mengimpor {name}, tunggu sebentar...",
        "import_failed": "Impor gagal. ",
        "auto_loaded": "Save terbaru dimuat otomatis, {name}",
        "auto_failed": "Save terbaru belum bisa dimuat, jadi data "
                       "sebelumnya yang masih ditampilkan.",
        "auto_note": "Save otomatis diperbarui saat file berubah, "
                     "impor manual cukup sekali di awal.",
        "snapshot_note": "Snapshot adalah salinan save hasil impor "
                         "yang dibaca SaveRay, terpisah dari file "
                         "save aslinya.",
        "games_not_found": "Folder games FM27 tidak ditemukan di "
                           "lokasi standarnya, jadi daftar save "
                           "tidak bisa ditampilkan.",
        "saved_snapshots": "Snapshot tersimpan",
        "imported_word": "diimpor",
        "use_snapshot": "Pakai snapshot ini",
        "tagline": "X-ray save FM27 kamu. Semua pemain, semua "
                   "atribut, termasuk yang hidden.",
        "no_snapshot": "Belum ada snapshot. Impor dulu salah satu "
                       "save dari menu Save di sidebar kiri.",
        "imported_cap": "Diimpor",
        "players_word": "pemain",
        "reset_all": "Reset semua filter",
        "reset_help": "Kembalikan semua filter di bawah ini ke nilai "
                      "awalnya.",
        "search_name": "Cari nama pemain",
        "all_word": "(semua)",
        "none_word": "(tidak ada)",
        "club": "Klub",
        "pos_contains": "Posisi natural mengandung",
        "age": "Umur",
        "min_ca": "CA minimum",
        "min_pa": "PA minimum",
        "attr_filter": "Filter atribut",
        "attr_min": "Nilai atribut minimum",
        "role_min": "Skor role minimum",
        "role_min_help": "Memakai skor Overall, nilai akhir setelah "
                         "faktor posisi (lihat penjelasan di profil "
                         "pemain).",
        "role_combine": "Boleh pilih salah satu filter role atau "
                        "keduanya. Kalau keduanya dipilih, pemain "
                        "harus lolos skor minimum di dua role itu "
                        "sekaligus.",
        "match_rest": "cocok dengan filter",
        "col_name": "Nama",
        "col_positions": "Posisi",
        "col_height": "Tinggi",
        "col_value": "Nilai Transfer",
        "col_wage": "Gaji",
        "col_contract": "Kontrak Berakhir",
        "profile_header": "Profil pemain",
        "no_players": "Tidak ada pemain pada filter saat ini.",
        "select_player": "Pilih pemain",
        "warn_caption": "\u26a0 = atribut yang makin tinggi justru "
                        "makin buruk (di grup Hidden, Dirtiness dan "
                        "Injury Proneness).",
        "personality_caption": "Semua atribut personality makin "
                               "tinggi makin baik, kecuali "
                               "Controversy \u26a0 \u2014 makin "
                               "tinggi makin buruk (pemain gemar "
                               "memancing kontroversi dan masalah "
                               "dengan media).",
        "pos_ratings": "Rating posisi (1\u201320)",
        "no_position": "Tidak ada posisi dengan rating di atas 1.",
        "feet_label": "Kaki",
        "best_role_header": "Best Role (terpisah per fase)",
        "metric_help": "Fit atribut {fit} \u00b7 di {pos} ({r}/20)",
        "col_position": "Posisi",
        "no_role": "Tidak ada role yang memenuhi syarat posisi "
                   "\u226515.",
        "info_box": "**Cara membaca dua angka ini.**\n\n"
                    "- **Fit** = seberapa cocok *atribut* pemain "
                    "dengan role itu. Murni soal skill, belum melihat "
                    "posisi.\n"
                    "- **Overall** = nilai akhirnya setelah melihat "
                    "*posisi*, Fit dikurangi bila posisi role itu "
                    "bukan posisi nyamannya.\n\n"
                    "Bila posisi role-nya adalah posisi natural "
                    "pemain (rating 20/20), tidak ada potongan. "
                    "Overall = Fit. Makin tidak nyaman posisinya, "
                    "makin besar potongannya \u2014 jadi Overall "
                    "tidak pernah lebih tinggi dari Fit. Urutan best "
                    "role memakai **Overall**, karena itu yang "
                    "realistis dimainkan. Role hanya dinilai untuk "
                    "posisi dengan rating minimal 15. Di bawah itu "
                    "pemain dianggap belum bisa main di sana.",
        "formula_caption": "Detail rumus: Fit = (rata-rata berbobot "
                           "atribut role \u2212 1) \u00f7 19 "
                           "\u00d7 100 (atribut priority berbobot "
                           "\u00d73, supporting \u00d71). Overall "
                           "= Fit \u00d7 (0,6 + 0,4 \u00d7 rating "
                           "posisi \u00f7 20).",
        "expander_title": "Semua role (79) \u2014 daftar lengkap "
                          "per fase",
        "expander_caption": "Overall yang kosong berarti role itu "
                            "menempel di posisi yang ratingnya di "
                            "bawah 15, jadi tidak dinilai.",
        "col_phase": "Fase",
    },
}


def T() -> dict:
    """UI strings for the language chosen in the sidebar."""
    lang = st.session_state.get("ui_lang", "English")
    return STRINGS["id" if lang == "Indonesia" else "en"]




@st.cache_data
def load(db_path: str) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    try:
        return pd.read_sql("SELECT * FROM players", con)
    finally:
        con.close()


@st.cache_data
def meta(db_path: str) -> dict:
    try:
        con = sqlite3.connect(db_path)
        try:
            return dict(pd.read_sql("SELECT key, value FROM meta", con).values)
        finally:
            con.close()
    except Exception:
        return {}


def slugify(stem: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return slug or "save"


def ensure_snapshots() -> None:
    """The snapshots folder always exists. A legacy players.db becomes
    the first snapshot."""
    SNAP_DIR.mkdir(exist_ok=True)
    if DB.exists() and not any(SNAP_DIR.glob("*.db")):
        src_name = Path(str(meta(str(DB)).get("source", "players"))).stem
        target = SNAP_DIR / (slugify(src_name) + ".db")
        target.write_bytes(DB.read_bytes())
        set_active(target)


def get_active_db():
    if ACTIVE_FILE.exists():
        p = Path(ACTIVE_FILE.read_text(encoding="utf-8-sig").strip())
        if p.exists():
            return p
    snaps = sorted(SNAP_DIR.glob("*.db"))
    return snaps[0] if snaps else None


def set_active(path: Path) -> None:
    ACTIVE_FILE.write_text(str(path), encoding="utf-8")


def list_game_saves() -> list:
    if not GAMES_DIR.exists():
        return []
    return sorted(GAMES_DIR.glob("*.fm"),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def list_snapshots() -> list:
    out = []
    for p in sorted(SNAP_DIR.glob("*.db")):
        m = meta(str(p))
        src = Path(str(m.get("source", p.stem))).name
        out.append((p, f"{src} · {T()['imported_word']} {m.get('imported_at', '?')}"))
    return out


def pretty(name: str) -> str:
    return name.replace("attributes_", "").replace("_", " ").title()


def fmt_money(v) -> str:
    """Raw in-game money value as compact currency, e.g. €187.61m."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    v = float(v)
    if abs(v) >= 1_000_000:
        return f"€{v / 1_000_000:.2f}m"
    if abs(v) >= 1_000:
        return f"€{v / 1_000:.0f}k"
    return f"€{v:.0f}"


def fmt_height(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return f"{int(v)} cm"


@st.cache_resource
def catalog():
    return load_catalog()


@st.cache_data(show_spinner=False)
def role_overalls(db_path: str, phase: str, role_name: str) -> pd.Series:
    """Overall score of one role for every player in a snapshot.

    Vectorized twin of roles_engine.score_role, so picking a role
    filter scores the whole database in a fraction of a second
    instead of looping over every player. The result is cached per
    snapshot and role, and every import clears the cache, so reruns
    while the filter is active reuse it for free. NaN marks players
    who are not eligible for the role.
    """
    df = load(db_path)
    role = next(r for r in catalog()
                if r["phase"] == phase and r["name"] == role_name)
    attr_names = list(role["priority"]) + list(role["supporting"])
    cols = ["attributes_" + attr_key(n) for n in attr_names]
    weights = np.array([3.0] * len(role["priority"])
                       + [1.0] * len(role["supporting"]))
    values = df[cols].to_numpy(dtype=float)
    fit = ((values @ weights) / weights.sum() - 1.0) / 19.0 * 100.0
    codes = []
    for group in role["position_groups"]:
        codes.extend(GROUP_TO_POSITIONS[group])
    best = np.zeros(len(df))
    for code in dict.fromkeys(codes):
        col = "positions_" + code.lower()
        rating = (df[col].to_numpy(dtype=float) if col in df.columns
                  else np.ones(len(df)))
        best = np.maximum(best, np.where(rating >= 15, rating, 0.0))
    overall = np.where(best > 0, fit * (0.6 + 0.4 * best / 20.0), np.nan)
    return pd.Series(np.round(overall, 1), index=df.index)


def row_attrs(row, names) -> dict:
    """{display name: value} for the attributes used by the role catalog."""
    out = {}
    for n in names:
        col = "attributes_" + attr_key(n)
        if col in row and pd.notna(row[col]):
            out[n] = int(row[col])
    return out


def row_positions(row) -> dict:
    return {p.upper(): int(row["positions_" + p])
            for p in POSITIONS
            if "positions_" + p in row and pd.notna(row["positions_" + p])}


def reset_filters() -> None:
    """Return every sidebar filter widget to its default value."""
    st.session_state["f_q"] = ""
    st.session_state["f_club"] = T()["all_word"]
    st.session_state["f_pos"] = T()["all_word"]
    bounds = st.session_state.get("_age_bounds")
    if bounds:
        st.session_state["f_age"] = bounds
    st.session_state["f_ca"] = 0
    st.session_state["f_pa"] = 0
    st.session_state["f_attr"] = T()["none_word"]
    st.session_state["f_attr_min"] = 15
    st.session_state["f_role_in"] = T()["none_word"]
    st.session_state["f_role_out"] = T()["none_word"]
    st.session_state["f_role_min"] = 60


def run_import(src: Path, target: Path) -> None:
    subprocess.run(
        [sys.executable, str(HERE / "import_save.py"), str(src),
         str(target)],
        check=True, capture_output=True, text=True)


def auto_candidates() -> list:
    """Saves the auto-loader may pick. The FM overwrite backup is
    skipped, because it holds the previous version of a save."""
    saves = list_game_saves()
    real = [p for p in saves
            if p.stem.lower() != "last save overwrite backup"]
    return real or saves


def pending_save_change(active):
    """The newest save file when the active snapshot is behind it.

    Only the save the active snapshot came from is refreshed. A
    snapshot the user picked on purpose, from another save, is
    left alone.
    """
    cands = auto_candidates()
    if not cands:
        return None
    newest = cands[0]
    fst = newest.stat()
    marker = (newest.name, int(fst.st_mtime), fst.st_size)
    if st.session_state.get("_auto_failed") == marker:
        return None
    if active is None:
        return newest
    info = meta(str(active))
    recorded = (info.get("source_name")
                or Path(str(info.get("source", ""))).name)
    if recorded != newest.name:
        return None
    if info.get("source_mtime") is None:
        return newest
    if (int(info["source_mtime"]) != int(fst.st_mtime)
            or int(info.get("source_size", -1)) != fst.st_size):
        return newest
    return None


def auto_load_latest(active):
    """Import the newest save when its file changed since the
    snapshot was taken. Returns (active_db, status) where status is
    "", "loaded" or "failed"."""
    newest = pending_save_change(active)
    if newest is None:
        return active, ""
    target = SNAP_DIR / (slugify(newest.stem) + ".db")
    try:
        with st.spinner(T()["importing"].format(name=newest.name)):
            run_import(newest, target)
    except subprocess.CalledProcessError:
        stt = newest.stat()
        st.session_state["_auto_failed"] = (
            newest.name, int(stt.st_mtime), stt.st_size)
        return active, "failed"
    set_active(target)
    st.cache_data.clear()
    st.session_state["_auto_name"] = newest.name
    return target, "loaded"


@st.fragment(run_every=20)
def _watch_newest_save() -> None:
    if pending_save_change(get_active_db()) is not None:
        try:
            st.rerun(scope="app")
        except TypeError:
            st.rerun()


def sidebar_save_section(active) -> None:
    st.sidebar.header("Save")
    saves = list_game_saves()
    if saves:
        labels = [
            f"{p.name} · {T()['modified']} {datetime.fromtimestamp(p.stat().st_mtime):%d %b %Y %H.%M}"
            f" · {p.stat().st_size / 1_000_000:.0f} MB"
            for p in saves]
        pick_label = st.sidebar.selectbox(T()["saves_in_folder"], labels)
        if st.sidebar.button(T()["import_this"]):
            src = saves[labels.index(pick_label)]
            target = SNAP_DIR / (slugify(src.stem) + ".db")
            try:
                with st.spinner(T()["importing"].format(name=src.name)):
                    run_import(src, target)
                set_active(target)
                st.cache_data.clear()
                st.rerun()
            except subprocess.CalledProcessError as e:
                st.sidebar.error(T()["import_failed"] + (e.stderr or "")[-300:])
    else:
        st.sidebar.caption(T()["games_not_found"])
    st.sidebar.caption(T()["auto_note"])
    snaps = list_snapshots()
    if snaps:
        snap_labels = [label for _, label in snaps]
        current = next((label for p, label in snaps if p == active), None)
        idx = snap_labels.index(current) if current in snap_labels else 0
        chosen = st.sidebar.selectbox(T()["saved_snapshots"], snap_labels,
                                      index=idx)
        chosen_path = snaps[snap_labels.index(chosen)][0]
        if chosen_path != active and st.sidebar.button(T()["use_snapshot"]):
            set_active(chosen_path)
            st.cache_data.clear()
            st.rerun()
        st.sidebar.caption(T()["snapshot_note"])
    st.sidebar.divider()


def main() -> None:
    st.title("SaveRay — FM27 Save Reader")
    st.sidebar.selectbox("Language", ["English", "Indonesia"],
                         key="ui_lang")
    t = T()
    allw, nonew = t["all_word"], t["none_word"]
    for _k in ("f_club", "f_pos"):
        if st.session_state.get(_k) in ("(all)", "(semua)"):
            st.session_state[_k] = allw
    for _k in ("f_attr", "f_role_in", "f_role_out"):
        if st.session_state.get(_k) in ("(none)", "(tidak ada)"):
            st.session_state[_k] = nonew
    st.caption(t["tagline"])
    ensure_snapshots()
    active = get_active_db()
    active, auto_status = auto_load_latest(active)
    sidebar_save_section(active)
    if active is None:
        st.info(t["no_snapshot"])
        st.stop()

    df = load(str(active))
    info = meta(str(active))
    st.caption(f"Save: {info.get('source', '?')} · {t['imported_cap']}: {info.get('imported_at', '?')} "
               f"· {len(df):,} {t['players_word']}")
    if auto_status == "loaded":
        st.toast(t["auto_loaded"].format(
            name=st.session_state.pop("_auto_name", "")))
    elif auto_status == "failed":
        st.caption(t["auto_failed"])

    # ---------- Sidebar filters ----------
    st.sidebar.header("Filter")
    st.sidebar.button(t["reset_all"], on_click=reset_filters,
                      help=t["reset_help"])
    q = st.sidebar.text_input(t["search_name"], key="f_q")
    clubs = sorted(x for x in df["club_name"].dropna().unique() if x)
    club = st.sidebar.selectbox(t["club"], [allw] + clubs, key="f_club")
    pos_opts = ["GK", "DL", "DC", "DR", "WBL", "WBR", "DM", "ML", "MC", "MR",
                "AML", "AMC", "AMR", "STC"]
    pos = st.sidebar.selectbox(t["pos_contains"], [allw] + pos_opts,
                               key="f_pos")
    age_min, age_max = int(df["age"].min()), int(df["age"].max())
    st.session_state["_age_bounds"] = (age_min, age_max)
    age = st.sidebar.slider(t["age"], age_min, age_max, (age_min, age_max),
                            key="f_age")
    ca = st.sidebar.slider(t["min_ca"], 0, 200, 0, key="f_ca")
    pa = st.sidebar.slider(t["min_pa"], 0, 200, 0, key="f_pa")
    attr = st.sidebar.selectbox(t["attr_filter"],
                                [nonew] + [pretty(a) for a in ALL_ATTRS],
                                key="f_attr")
    attr_min = st.sidebar.slider(t["attr_min"], 1, 20, 15,
                                 key="f_attr_min")
    cat = catalog()
    role_attr_names = set()
    for r in cat:
        role_attr_names |= set(r["priority"]) | set(r["supporting"])
    in_roles = [r for r in cat if r["phase"] == "in"]
    oop_roles = [r for r in cat if r["phase"] == "out"]
    pick_in = st.sidebar.selectbox(
        "Filter role In possession",
        [nonew] + [r["name"] for r in in_roles], key="f_role_in")
    pick_out = st.sidebar.selectbox(
        "Filter role Out of possession",
        [nonew] + [r["name"] for r in oop_roles], key="f_role_out")
    role_min = st.sidebar.slider(t["role_min"], 0, 100, 60,
                                 key="f_role_min",
                                 help=t["role_min_help"])
    st.sidebar.caption(t["role_combine"])

    out = df.copy()
    if q:
        out = out[out["name"].str.contains(q, case=False, na=False)]
    if club != allw:
        out = out[out["club_name"] == club]
    if pos != allw:
        out = out[out["natural_positions"].str.contains(pos, na=False)]
    out = out[(out["age"] >= age[0]) & (out["age"] <= age[1])]
    out = out[out["ability_current"] >= ca]
    out = out[out["ability_potential"] >= pa]
    if attr != nonew:
        col = "attributes_" + attr.lower().replace(" ", "_")
        if col in out.columns:
            out = out[out[col] >= attr_min]
    chosen = []
    if pick_in != nonew:
        chosen.append(("fit_in", next(r for r in in_roles
                                      if r["name"] == pick_in)))
    if pick_out != nonew:
        chosen.append(("fit_out", next(r for r in oop_roles
                                       if r["name"] == pick_out)))
    role_active = bool(chosen)
    if role_active:
        sort_cols = []
        for colname, role_obj in chosen:
            scores = role_overalls(str(active), role_obj["phase"],
                                   role_obj["name"])
            out = out.assign(**{colname: scores.reindex(out.index)})
            out = out[out[colname].notna() & (out[colname] >= role_min)]
            sort_cols.append(colname)
        if len(sort_cols) == 2:
            out = out.assign(
                _fit_avg=(out["fit_in"] + out["fit_out"]) / 2)
            out = out.sort_values("_fit_avg", ascending=False)
            out = out.drop(columns="_fit_avg")
        else:
            out = out.sort_values(sort_cols[0], ascending=False)
    else:
        out = out.sort_values("ability_current", ascending=False)

    st.write(f"**{len(out):,} {t['players_word']}** {t['match_rest']}")
    show_cols = ["name", "age", "club_name", "natural_positions",
                 "ability_current", "ability_potential", "height_cm",
                 "transfer_value", "contract_wage", "contract_end"]
    if role_active:
        show_cols = ["name"] + [c for c, _ in chosen] + show_cols[1:]
    show_cols = [c for c in show_cols if c in out.columns]
    disp = out[show_cols].copy()
    if "natural_positions" in disp.columns:
        disp["natural_positions"] = disp["natural_positions"].str.replace(
            ";", ", ", regex=False)
    if "transfer_value" in disp.columns:
        disp["transfer_value"] = disp["transfer_value"].map(fmt_money)
    if "contract_wage" in disp.columns:
        disp["contract_wage"] = disp["contract_wage"].map(fmt_money)
    if "height_cm" in disp.columns:
        disp["height_cm"] = disp["height_cm"].map(fmt_height)
    labels = {"name": t["col_name"], "age": t["age"],
              "club_name": t["club"],
              "natural_positions": t["col_positions"],
              "ability_current": "CA", "ability_potential": "PA",
              "height_cm": t["col_height"],
              "transfer_value": t["col_value"],
              "contract_wage": t["col_wage"],
              "contract_end": t["col_contract"]}
    for colname, role_obj in chosen:
        labels[colname] = (f"{role_obj['name']} "
                           f"({'IP' if colname == 'fit_in' else 'OOP'})")
    disp = disp.rename(columns=labels)
    st.dataframe(disp, width="stretch", height=420, hide_index=True)

    # ---------- Player detail ----------
    st.header(t["profile_header"])
    if out.empty:
        st.info(t["no_players"])
        return
    names = out["name"].tolist()
    pick = st.selectbox(t["select_player"], names)
    row = out[out["name"] == pick].iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CA", int(row["ability_current"]))
    c2.metric("PA", int(row["ability_potential"]))
    c3.metric(t["age"], int(row["age"]))
    c4.metric(t["club"], row["club_name"] if pd.notna(row["club_name"]) else "-")

    gk_rating = 0
    if "positions_gk" in row and pd.notna(row["positions_gk"]):
        gk_rating = int(row["positions_gk"])
    show_groups = dict(GROUPS)
    if gk_rating < 15:
        # Not a goalkeeper, so the Goalkeeping group is hidden and
        # the Hidden group shifts into its place.
        show_groups.pop("Goalkeeping")
    cols = st.columns(len(show_groups))
    for col, (group, attrs) in zip(cols, show_groups.items()):
        with col:
            st.subheader(group)
            for a in attrs:
                key = f"attributes_{a}"
                if key in row and pd.notna(row[key]):
                    mark = " ⚠" if a in BAD_WHEN_HIGH else ""
                    st.write(f"{pretty(a)}: **{int(row[key])}**{mark}")
            if group == "Hidden":
                st.markdown(
                    '<hr style="border:none;border-top:2px solid '
                    '#7a7a7a;margin:0.5rem 0;">',
                    unsafe_allow_html=True)
                st.write(f"{t['feet_label']}: "
                         f"**{int(row['left_foot'])}/{int(row['right_foot'])}**")
                st.write(f"{t['col_height']}: "
                         f"**{fmt_height(row['height_cm'])}**")
    st.caption(t["warn_caption"])

    st.subheader("Personality")
    st.write(" · ".join(
        f"{p.title()}: **{int(row['personality_' + p])}**"
        f"{' ⚠' if p in BAD_WHEN_HIGH else ''}"
        for p in PERSONALITY
        if "personality_" + p in row and pd.notna(row["personality_" + p])))
    st.caption(t["personality_caption"])

    st.subheader(t["pos_ratings"])
    pos_parts = [
        f"{p.upper()}: **{int(row['positions_' + p])}**"
        for p in POSITIONS
        if "positions_" + p in row and pd.notna(row["positions_" + p])
        and int(row["positions_" + p]) > 1]
    st.write(" · ".join(pos_parts) if pos_parts
             else t["no_position"])

    # ---------- Best role per fase ----------
    st.subheader(t["best_role_header"])
    scored = score_player(row_attrs(row, role_attr_names),
                          row_positions(row), cat)
    phase_cols = st.columns(2)
    for pcol, phase, label in zip(phase_cols, ["in", "out"],
                                  ["In possession", "Out of possession"]):
        with pcol:
            st.markdown(f"**{label}**")
            ranked = sorted(
                (s for s in scored if s["phase"] == phase and s["eligible"]),
                key=lambda s: s["overall"], reverse=True)[:5]
            if ranked:
                best = ranked[0]
                st.metric(f"Best: {best['name']}", f"{best['overall']:.1f}",
                          help=t["metric_help"].format(
                               fit=f"{best['fit']:.1f}",
                               pos=best["position"],
                               r=best["position_rating"]))
                st.dataframe(pd.DataFrame([{
                    "Role": s["name"], "Overall": s["overall"],
                    "Fit": s["fit"], t["col_position"]: s["position"],
                } for s in ranked]), hide_index=True, width="stretch")
            else:
                st.info(t["no_role"])
    st.info(t["info_box"])
    st.caption(t["formula_caption"])
    with st.expander(t["expander_title"]):
        st.caption(t["expander_caption"])
        full = pd.DataFrame([{
            "Role": s["name"],
            t["col_phase"]: "In" if s["phase"] == "in" else "Out",
            "Fit": s["fit"], "Overall": s["overall"],
            "Position": s["position"],
        } for s in scored])
        st.dataframe(full.sort_values([t["col_phase"], "Fit"], ascending=[True, False]),
                     hide_index=True, width="stretch", height=400)

    _watch_newest_save()


if __name__ == "__main__":
    main()
