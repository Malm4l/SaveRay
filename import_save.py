"""Import an FM27 save (.fm) into a local SQLite snapshot.

Pipeline: fmsave CLI export (players --all) -> CSV -> SQLite (players.db).

Usage (run with the venv python where fmsave is installed):
    python import_save.py <path-to-save.fm> [output.db]
    python import_save.py <path-to-players.csv> [output.db]   # reuse an export

The SQLite file gets two tables:
    players  - one row per player, numeric columns stored as numbers
    meta     - source file, import time, player count
"""
import csv
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


def csv_to_sqlite(csv_path: Path, db_path: Path, source_label: str) -> int:
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
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        con.executemany("INSERT INTO meta VALUES (?, ?)", [
            ("source", source_label),
            ("imported_at", datetime.now().isoformat(timespec="seconds")),
            ("player_count", str(len(rows))),
        ])
        con.commit()
    finally:
        con.close()
    return len(rows)


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
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            csv_path = export_csv(src, Path(tmp))
            count = csv_to_sqlite(csv_path, db_path, str(src))
    print(f"Done: {count} players -> {db_path}")


if __name__ == "__main__":
    main()
