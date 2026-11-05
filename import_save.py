"""Import an FM27 save (.fm) into a local SQLite snapshot.

Pipeline: the save is read in-process through the fmsave Python API
and written straight to SQLite. If the API route fails for any
reason, the importer falls back to the original route, fmsave CLI
export (players --all) -> CSV -> SQLite.

Usage (run with the venv python where fmsave is installed):
    python import_save.py <path-to-save.fm> [output.db]
    python import_save.py <path-to-players.csv> [output.db]   # reuse an export

The SQLite file gets two tables:
    players  - one row per player, numeric columns stored as numbers
    meta     - source file, import time, player count
"""
import csv
import datetime as _dt
import json
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def export_csv(save_path: Path, workdir: Path) -> Path:
    """Run the fmsave CLI (installed next to this python) to export players."""
    exe = Path(sys.executable).parent / ("fmsave.exe" if sys.platform == "win32" else "fmsave")
    cmd = [str(exe) if exe.exists() else "fmsave",
           "export", str(save_path), "players", "--all", "-o", "players.csv"]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=workdir, check=True)
    return workdir / "players.csv"


def looks_numeric(values) -> bool:
    seen = False
    for v in values:
        if v is None or v == "":
            continue
        seen = True
        try:
            float(v)
        except (TypeError, ValueError):
            return False
    return seen


def _write_meta(con, source_label: str, count: int,
                extra_meta: dict | None) -> None:
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    meta_rows = [
        ("source", source_label),
        ("imported_at", datetime.now().isoformat(timespec="seconds")),
        ("player_count", str(count)),
    ]
    if extra_meta:
        meta_rows += sorted(extra_meta.items())
    con.executemany("INSERT INTO meta VALUES (?, ?)", meta_rows)


def csv_to_sqlite(csv_path: Path, db_path: Path, source_label: str,
                  extra_meta: dict | None = None) -> int:
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        rows = list(reader)
    if not columns or not rows:
        raise SystemExit("CSV is empty - export failed?")

    numeric = {c: looks_numeric([r[c] for r in rows]) for c in columns}

    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    try:
        col_defs = ", ".join(
            f'"{c}" {"REAL" if numeric[c] else "TEXT"}' for c in columns)
        con.execute(f"CREATE TABLE players ({col_defs})")
        placeholders = ", ".join("?" for _ in columns)
        data = []
        for r in rows:
            data.append(tuple(
                (float(r[c]) if numeric[c] and r[c] not in (None, "") else
                 None if numeric[c] else r[c])
                for c in columns))
        con.executemany(
            f"INSERT INTO players VALUES ({placeholders})", data)
        _write_meta(con, source_label, len(rows), extra_meta)
        con.commit()
    finally:
        con.close()
    return len(rows)


def _csv_cell(value):
    """Text form of one flat value, mirroring fmsave's CSV writer.

    Keeps snapshots built through the API identical to snapshots
    built through the old CSV route (empty text for missing values,
    lowercase booleans, ISO dates, semicolon-joined tuples, compact
    JSON for tuples holding records).
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (_dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        if not value:
            return ""
        item_types = set(map(type, value))
        if item_types <= {str}:
            return ";".join(value)
        if item_types <= {int}:
            return ";".join(map(str, value))
        if any(isinstance(item, dict) for item in value):
            return json.dumps(list(value), ensure_ascii=False,
                              separators=(",", ":"), default=str)
        return ";".join(_csv_cell(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False,
                          separators=(",", ":"), default=str)
    return str(value)


def _column_is_numeric(values) -> bool:
    """True when every present value is a native int or float."""
    seen = False
    for v in values:
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        seen = True
    return seen


def save_to_sqlite_api(save_path: Path, db_path: Path, source_label: str,
                       extra_meta: dict | None = None) -> int:
    """Read the save through the fmsave API, skipping the CSV detour."""
    import fmsave
    from fmsave import export as _export
    from fmsave.models.players import Player

    with fmsave.open(save_path) as save:
        columns = _export.to_columns(save.players(), Player)
    names = list(columns.keys())
    if not names:
        raise SystemExit("No player columns - read failed?")
    count = len(columns[names[0]])
    numeric = [_column_is_numeric(columns[c]) for c in names]
    final = [columns[c] if numeric[i] else [_csv_cell(v) for v in columns[c]]
             for i, c in enumerate(names)]
    rows = list(zip(*final))

    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    try:
        col_defs = ", ".join(
            f'"{c}" {"REAL" if numeric[i] else "TEXT"}'
            for i, c in enumerate(names))
        con.execute(f"CREATE TABLE players ({col_defs})")
        placeholders = ", ".join("?" for _ in names)
        con.executemany(
            f"INSERT INTO players VALUES ({placeholders})", rows)
        _write_meta(con, source_label, count, extra_meta)
        con.commit()
    finally:
        con.close()
    return count


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = Path(sys.argv[1]).expanduser().resolve()
    db_path = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else HERE / "players.db"
    if not src.exists():
        raise SystemExit(f"Source not found: {src}")

    if src.suffix.lower() == ".csv":
        count = csv_to_sqlite(src, db_path, str(src))
    else:
        st = src.stat()
        extra = {"source_name": src.name,
                 "source_mtime": str(int(st.st_mtime)),
                 "source_size": str(st.st_size)}
        try:
            count = save_to_sqlite_api(src, db_path, str(src), extra)
        except Exception as exc:
            print(f"API import failed ({exc!r}), falling back to CLI export")
            with tempfile.TemporaryDirectory(dir=HERE) as tmp:
                csv_path = export_csv(src, Path(tmp))
                count = csv_to_sqlite(csv_path, db_path, str(src), extra)
    print(f"Done: {count} players -> {db_path}")


if __name__ == "__main__":
    main()
