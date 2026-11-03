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

import pandas as pd
import streamlit as st

from roles_engine import attr_key, load_catalog, score_player, score_role

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
        out.append((p, f"{src} · imported {m.get('imported_at', '?')}"))
    return out


def pretty(name: str) -> str:
    return name.replace("attributes_", "").replace("_", " ").title()


@st.cache_resource
def catalog():
    return load_catalog()


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
    st.session_state["f_club"] = "(all)"
    st.session_state["f_pos"] = "(all)"
    bounds = st.session_state.get("_age_bounds")
    if bounds:
        st.session_state["f_age"] = bounds
    st.session_state["f_ca"] = 0
    st.session_state["f_pa"] = 0
    st.session_state["f_attr"] = "(none)"
    st.session_state["f_attr_min"] = 15
    st.session_state["f_role_in"] = "(none)"
    st.session_state["f_role_out"] = "(none)"
    st.session_state["f_role_min"] = 60


def sidebar_save_section(active) -> None:
    st.sidebar.header("Save")
    saves = list_game_saves()
    if saves:
        labels = [
            f"{p.name} · modified {datetime.fromtimestamp(p.stat().st_mtime):%d %b %Y %H.%M}"
            f" · {p.stat().st_size / 1_000_000:.0f} MB"
            for p in saves]
        pick_label = st.sidebar.selectbox("Saves in the FM27 games folder", labels)
        if st.sidebar.button("Import this save"):
            src = saves[labels.index(pick_label)]
            target = SNAP_DIR / (slugify(src.stem) + ".db")
            try:
                with st.spinner(f"Importing {src.name}, please wait..."):
                    subprocess.run(
                        [sys.executable, str(HERE / "import_save.py"),
                         str(src), str(target)],
                        check=True, capture_output=True, text=True)
                set_active(target)
                st.cache_data.clear()
                st.rerun()
            except subprocess.CalledProcessError as e:
                st.sidebar.error("Import failed. " + (e.stderr or "")[-300:])
    else:
        st.sidebar.caption("The FM27 games folder was not found in its "
                           "standard location, so the save list cannot "
                           "be shown.")
    snaps = list_snapshots()
    if snaps:
        snap_labels = [label for _, label in snaps]
        current = next((label for p, label in snaps if p == active), None)
        idx = snap_labels.index(current) if current in snap_labels else 0
        chosen = st.sidebar.selectbox("Saved snapshots", snap_labels,
                                      index=idx)
        chosen_path = snaps[snap_labels.index(chosen)][0]
        if chosen_path != active and st.sidebar.button("Use this snapshot"):
            set_active(chosen_path)
            st.cache_data.clear()
            st.rerun()
    st.sidebar.divider()


def main() -> None:
    st.title("SaveRay — FM27 Save Reader")
    st.caption("X-ray your FM27 save. Every player, every attribute, "
               "including the hidden ones.")
    ensure_snapshots()
    active = get_active_db()
    sidebar_save_section(active)
    if active is None:
        st.info("No snapshot yet. Import one of your saves from the "
                "Save menu in the left sidebar.")
        st.stop()

    df = load(str(active))
    info = meta(str(active))
    st.caption(f"Save: {info.get('source', '?')} · Imported: {info.get('imported_at', '?')} "
               f"· {len(df):,} players")

    # ---------- Sidebar filters ----------
    st.sidebar.header("Filter")
    st.sidebar.button("Reset all filters", on_click=reset_filters,
                      help="Return every filter below to its "
                           "default value.")
    q = st.sidebar.text_input("Search player name", key="f_q")
    clubs = sorted(x for x in df["club_name"].dropna().unique() if x)
    club = st.sidebar.selectbox("Club", ["(all)"] + clubs, key="f_club")
    pos_opts = ["GK", "DL", "DC", "DR", "WBL", "WBR", "DM", "ML", "MC", "MR",
                "AML", "AMC", "AMR", "STC"]
    pos = st.sidebar.selectbox("Natural position contains",
                               ["(all)"] + pos_opts, key="f_pos")
    age_min, age_max = int(df["age"].min()), int(df["age"].max())
    st.session_state["_age_bounds"] = (age_min, age_max)
    age = st.sidebar.slider("Age", age_min, age_max, (age_min, age_max),
                            key="f_age")
    ca = st.sidebar.slider("Minimum CA", 0, 200, 0, key="f_ca")
    pa = st.sidebar.slider("Minimum PA", 0, 200, 0, key="f_pa")
    attr = st.sidebar.selectbox("Attribute filter",
                                ["(none)"] + [pretty(a) for a in ALL_ATTRS],
                                key="f_attr")
    attr_min = st.sidebar.slider("Minimum attribute value", 1, 20, 15,
                                 key="f_attr_min")
    cat = catalog()
    role_attr_names = set()
    for r in cat:
        role_attr_names |= set(r["priority"]) | set(r["supporting"])
    in_roles = [r for r in cat if r["phase"] == "in"]
    oop_roles = [r for r in cat if r["phase"] == "out"]
    pick_in = st.sidebar.selectbox(
        "Filter role In possession",
        ["(none)"] + [r["name"] for r in in_roles], key="f_role_in")
    pick_out = st.sidebar.selectbox(
        "Filter role Out of possession",
        ["(none)"] + [r["name"] for r in oop_roles], key="f_role_out")
    role_min = st.sidebar.slider("Minimum role score", 0, 100, 60,
                                 key="f_role_min",
                                 help="Uses the Overall score, the final "
                                      "value after the position factor "
                                      "(explained in the player profile).")
    st.sidebar.caption("Pick one role filter or both. When both are "
                       "picked, a player must pass the minimum score "
                       "in both roles at the same time.")

    out = df.copy()
    if q:
        out = out[out["name"].str.contains(q, case=False, na=False)]
    if club != "(all)":
        out = out[out["club_name"] == club]
    if pos != "(all)":
        out = out[out["natural_positions"].str.contains(pos, na=False)]
    out = out[(out["age"] >= age[0]) & (out["age"] <= age[1])]
    out = out[out["ability_current"] >= ca]
    out = out[out["ability_potential"] >= pa]
    if attr != "(none)":
        col = "attributes_" + attr.lower().replace(" ", "_")
        if col in out.columns:
            out = out[out[col] >= attr_min]
    chosen = []
    if pick_in != "(none)":
        chosen.append(("fit_in", next(r for r in in_roles
                                      if r["name"] == pick_in)))
    if pick_out != "(none)":
        chosen.append(("fit_out", next(r for r in oop_roles
                                       if r["name"] == pick_out)))
    role_active = bool(chosen)
    if role_active:
        sort_cols = []
        for colname, role_obj in chosen:
            fits = []
            for _, r in out.iterrows():
                s = score_role(role_obj, row_attrs(r, role_attr_names),
                               row_positions(r))
                fits.append(s["overall"] if s["eligible"] else None)
            out = out.assign(**{colname: fits})
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

    st.write(f"**{len(out):,} players** match the current filters")
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
    st.dataframe(disp, width="stretch", height=420, hide_index=True)

    # ---------- Player detail ----------
    st.header("Player profile")
    if out.empty:
        st.info("No players match the current filters.")
        return
    names = out["name"].tolist()
    pick = st.selectbox("Select player", names)
    row = out[out["name"] == pick].iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CA", int(row["ability_current"]))
    c2.metric("PA", int(row["ability_potential"]))
    c3.metric("Age", int(row["age"]))
    c4.metric("Club", row["club_name"] if pd.notna(row["club_name"]) else "-")
    st.write(f"Natural positions: "
             f"**{str(row['natural_positions']).replace(';', ', ')}** · "
             f"Feet **{int(row['left_foot'])}/{int(row['right_foot'])}**")
    st.caption("Feet are written as left/right. For example 15/20 means "
               "a left foot of 15 and a right foot of 20. Each foot is "
               "rated 1 to 20 and the bigger number is the player's "
               "stronger foot.")

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
    st.caption("⚠ = an attribute where higher is worse, not better "
               "(in the Hidden group, Dirtiness and Injury Proneness).")

    st.subheader("Personality")
    st.write(" · ".join(
        f"{p.title()}: **{int(row['personality_' + p])}**"
        f"{' ⚠' if p in BAD_WHEN_HIGH else ''}"
        for p in PERSONALITY
        if "personality_" + p in row and pd.notna(row["personality_" + p])))
    st.caption("Every personality attribute is better when higher, "
               "except Controversy ⚠, where higher is worse because "
               "the player courts controversy and trouble with the "
               "media.")

    st.subheader("Position ratings (1–20)")
    pos_parts = [
        f"{p.upper()}: **{int(row['positions_' + p])}**"
        for p in POSITIONS
        if "positions_" + p in row and pd.notna(row["positions_" + p])
        and int(row["positions_" + p]) > 1]
    st.write(" · ".join(pos_parts) if pos_parts
             else "No position is rated above 1.")

    # ---------- Best role per fase ----------
    st.subheader("Best Role (split by phase)")
    st.info(
        "**How to read these two numbers.**\n\n"
        "- **Fit** measures how well the player's *attributes* suit "
        "the role. It is pure skill and ignores position.\n"
        "- **Overall** is the final score after *position* is taken "
        "into account. Fit is reduced when the role sits away from "
        "the positions the player is comfortable in.\n\n"
        "When the role sits on a natural position rated 20 out of 20, "
        "there is no reduction and Overall equals Fit. The less "
        "comfortable the position, the bigger the reduction, so "
        "Overall never exceeds Fit. Best role lists are ranked by "
        "**Overall** because that is what is realistic on the pitch. "
        "A role is only rated at positions of 15 or higher. Below "
        "that, the player is treated as unable to play there.")
    st.caption("Formula detail. Fit = (weighted average of the role "
               "attributes − 1) ÷ 19 × 100, with priority attributes "
               "weighted ×3 and supporting ×1. "
               "Overall = Fit × (0.6 + 0.4 × position rating ÷ 20).")
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
                          help=f"Attribute fit {best['fit']:.1f} · "
                               f"at {best['position']} "
                               f"({best['position_rating']}/20)")
                st.dataframe(pd.DataFrame([{
                    "Role": s["name"], "Overall": s["overall"],
                    "Fit": s["fit"], "Position": s["position"],
                } for s in ranked]), hide_index=True, width="stretch")
            else:
                st.info("No role qualifies, because no position is "
                        "rated 15 or higher.")
    with st.expander("All roles (79) — full list per phase"):
        st.caption("A blank Overall means the role sits on a position "
                   "rated below 15, so it is not scored.")
        full = pd.DataFrame([{
            "Role": s["name"],
            "Phase": "In" if s["phase"] == "in" else "Out",
            "Fit": s["fit"], "Overall": s["overall"],
            "Position": s["position"],
        } for s in scored])
        st.dataframe(full.sort_values(["Phase", "Fit"], ascending=[True, False]),
                     hide_index=True, width="stretch", height=400)


if __name__ == "__main__":
    main()
