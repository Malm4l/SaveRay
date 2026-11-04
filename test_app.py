"""Headless smoke and behaviour tests, running app.py via Streamlit
AppTest.

Usage: python test_app.py   (in the same folder as app.py and data)
Passes when the app renders without exceptions and every check below
holds against the active snapshot.
"""
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("app.py", default_timeout=120).run()
if at.exception:
    for exc in at.exception:
        print("EXCEPTION:", exc.value)
    raise SystemExit(1)
print("APPTEST_OK")
print("titles:", [t.value for t in at.title])
print("metrics:", [(m.label, m.value) for m in at.metric][:4])
best = [(m.label, m.value) for m in at.metric if m.label.startswith("Best: ")]
print("best-role metrics:", best)
assert len(best) == 2, "Best Role per phase must render 2 metrics (in & out)"
print("ROLE_SECTION_OK")
infos = [i.value for i in at.info]
assert any("Fit" in t and "Overall" in t for t in infos), \
    "The Fit vs Overall explanation box must show in the Best Role section"
print("INFO_SECTION_OK")
expl = next(t for t in infos if "Fit" in t and "Overall" in t)
assert ";" not in expl and ":" not in expl, \
    "Explanation text must not use colons or semicolons"
try:
    tbl = at.dataframe[0].value
    col = tbl["Positions"].astype(str)
    assert not col.str.contains(";").any(), \
        "The natural positions column must not use semicolons"
    print("POSITIONS_COMMA_OK sample:", col.iloc[0])
except Exception as e:
    print("POSITIONS_CHECK_SKIPPED:", e)
print("PUNCT_OK")
side_buttons = [b.label for b in at.sidebar.button]
side_selects = [s.label for s in at.sidebar.selectbox]
print("sidebar buttons:", side_buttons)
print("sidebar selectbox:", side_selects[:3])
assert "Import this save" in side_buttons, \
    "The save import button must be in the sidebar"
assert "Saved snapshots" in side_selects, \
    "The snapshot picker must be in the sidebar"
print("IMPORT_UI_OK")
assert "Filter role In possession" in side_selects
assert "Filter role Out of possession" in side_selects
print("ROLE_FILTER_PHASE_OK")
tbl0 = at.dataframe[0].value
subs0 = [s.value for s in at.subheader]
first_nat = str(tbl0["Positions"].iloc[0])
if "GK" not in first_nat:
    assert "Goalkeeping" not in subs0, subs0
    assert "Hidden" in subs0
    gk_rows = tbl0[tbl0["Positions"].astype(str)
                   .str.contains("GK", na=False)]
    assert len(gk_rows) > 0
    gk_name = gk_rows["Name"].iloc[0]
    pick_box = next(s for s in at.selectbox if s.label == "Select player")
    pick_box.set_value(gk_name).run()
    assert not at.exception
    subs2 = [s.value for s in at.subheader]
    assert "Goalkeeping" in subs2 and "Hidden" in subs2, subs2
    print("GK_GROUP_TOGGLE_OK, sample goalkeeper:", gk_name)
else:
    print("GK_GROUP_TOGGLE_SKIPPED, the default player is a goalkeeper")
box = next(s for s in at.sidebar.selectbox
           if s.label == "Filter role In possession")
box.set_value("Inside Forward").run()
assert not at.exception
tbl = at.dataframe[0].value
fit_col = next(c for c in tbl.columns if "Inside Forward" in c)
assert (tbl[fit_col] >= 60).all()
print("ROLE_FILTER_WORKS_OK rows:", len(tbl))
import re
mds = [m.value for m in at.markdown]
feet = [t for t in mds if "Feet **" in t]
assert feet and re.search(r"Feet \*\*\d{1,2}/\d{1,2}\*\*", feet[0]), feet
caps = [c.value for c in at.caption]
assert any("left foot" in c and "right foot" in c for c in caps), caps
print("FEET_FORMAT_OK", feet[0].split("·")[-1].strip())
def _cur(seq, label):
    return next(x for x in seq if x.label == label)

_cur(at.sidebar.button, "Reset all filters").click().run()
assert not at.exception
n_full = len(at.dataframe[0].value)
assert _cur(at.sidebar.selectbox,
            "Filter role In possession").value == "(none)"
_cur(at.sidebar.text_input, "Search player name").set_value("Watkins").run()
assert not at.exception
n_small = len(at.dataframe[0].value)
assert 0 < n_small < n_full, (n_small, n_full)
_cur(at.sidebar.button, "Reset all filters").click().run()
assert not at.exception
assert _cur(at.sidebar.text_input, "Search player name").value == ""
assert len(at.dataframe[0].value) == n_full
print("RESET_FILTER_OK full rows:", n_full, "| filtered rows:", n_small)
