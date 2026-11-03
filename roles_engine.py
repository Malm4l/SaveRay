"""SaveRay role engine (step 4).

Scores a player for every FM27 tactical role in the catalog
(roles_touchline.json), separately per possession phase.

Formula (verified against Touchline's published methodology and
recalculated scores, Nov 2026):
  attribute fit = (weighted average - 1) / 19 * 100
    priority attributes weigh 3, supporting attributes weigh 1
  overall fit   = attribute fit * (0.6 + 0.4 * position rating / 20)
A role is a "candidate" (eligible) only at positions rated >= 15.
Unlike Touchline's panel (one mixed top-3), results are ranked
per phase so a player's best in-possession role is never crowded
out by out-of-possession roles (the McGinn case).
"""

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))

# Touchline position groups -> FM position codes (fmsave positions_*).
GROUP_TO_POSITIONS = {
    "Goalkeeper": ["GK"],
    "Centre-back": ["DC"],
    "Wide centre-back": ["DC"],
    "Full-back": ["DL", "DR"],
    "Wing-back": ["WBL", "WBR"],
    "Defensive midfield": ["DM"],
    "Central midfield": ["MC"],
    "Attacking midfield": ["AMC"],
    "Wide midfield": ["ML", "MR"],
    "Wide attack": ["AML", "AMR"],
    "Striker": ["STC"],
}

MIN_POSITION_RATING = 15


def attr_key(attribute_name):
    """'Off the Ball' -> 'off_the_ball' (fmsave attribute column suffix)."""
    return attribute_name.strip().lower().replace(" ", "_")


def load_catalog(path=None):
    path = path or os.path.join(_HERE, "roles_touchline.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["roles"]


def attribute_fit(role, attrs):
    """attrs: {attribute display name: 1-20 value}. Returns 0-100 fit."""
    total = 0.0
    weight = 0
    for name in role["priority"]:
        total += 3 * attrs[name]
        weight += 3
    for name in role["supporting"]:
        total += 1 * attrs[name]
        weight += 1
    avg = total / weight
    return (avg - 1) / 19 * 100


def score_role(role, attrs, positions):
    """Score one role for one player.

    Returns dict: fit, overall (None when ineligible), position,
    position_rating, eligible.
    """
    fit = attribute_fit(role, attrs)
    codes = []
    for group in role["position_groups"]:
        codes.extend(GROUP_TO_POSITIONS[group])
    best = None
    for code in dict.fromkeys(codes):
        rating = positions.get(code, 1)
        if rating >= MIN_POSITION_RATING:
            overall = fit * (0.6 + 0.4 * rating / 20)
            if best is None or overall > best[0]:
                best = (overall, code, rating)
    return {
        "fit": round(fit, 1),
        "overall": round(best[0], 1) if best else None,
        "position": best[1] if best else None,
        "position_rating": best[2] if best else None,
        "eligible": best is not None,
    }


def score_player(attrs, positions, catalog=None):
    """Score every role for one player.

    attrs: {display name: value}; positions: {code: rating 1-20}.
    Returns a list of dicts: name, phase, fit, overall (best eligible
    position), position (code of that position), position_rating,
    eligible (bool). Overall is None when no mapped position >= 15.
    """
    catalog = catalog if catalog is not None else load_catalog()
    results = []
    for role in catalog:
        r = score_role(role, attrs, positions)
        results.append({"name": role["name"], "phase": role["phase"], **r})
    return results


def best_roles(attrs, positions, catalog=None, phase=None, top=5):
    """Eligible roles ranked by overall fit, optionally for one phase."""
    scored = [r for r in score_player(attrs, positions, catalog)
              if r["eligible"] and (phase is None or r["phase"] == phase)]
    scored.sort(key=lambda r: r["overall"], reverse=True)
    return scored[:top]
