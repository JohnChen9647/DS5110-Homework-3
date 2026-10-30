
import argparse
import csv
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"
TABLES = ("occupations", "users", "movies", "genres", "movie_genres", "ratings")


def read_delimited(raw_dir, filename, delimiter, field_count):
    """Yield each nonblank source row, validating its expected number of fields."""
    path = raw_dir / filename
    with path.open(encoding="latin-1", newline="") as source:
        for line_number, row in enumerate(csv.reader(source, delimiter=delimiter), 1):
            if not row:
                continue
            if len(row) != field_count:
                raise ValueError(
                    f"{path}:{line_number}: expected {field_count} fields, "
                    f"found {len(row)}"
                )
            yield line_number, row


def load_database(raw_dir, db_path):
    if sqlite3.sqlite_version_info < (3, 37, 0):
        sys.exit(
            f"Python uses SQLite {sqlite3.sqlite_version}; "
            f"STRICT tables need SQLite 3.37 or newer.\n"
            f"Python in use: {sys.executable}"
        )

    raw_dir = raw_dir.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)

    con = sqlite3.connect(db_path)
    try:
        con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        con.execute("PRAGMA foreign_keys = ON")

        occupations_path = raw_dir / "u.occupation"
        with occupations_path.open(encoding="latin-1") as source:
            occupations = [line.rstrip("\r\n") for line in source if line.rstrip("\r\n")]
        con.executemany(
            "INSERT INTO occupations VALUES (?)",
            ((occupation,) for occupation in occupations),
        )

        genres = {}
        for _, row in read_delimited(raw_dir, "u.genre", "|", 2):
            if row == ["", ""]:
                continue
            name, genre_id = row
            genre_id = int(genre_id)
            con.execute(
                "INSERT INTO genres VALUES (?, ?)",
                (genre_id, name),
            )
            genres[genre_id] = name

        for _, row in read_delimited(raw_dir, "u.user", "|", 5):
            user_id, age, gender, occupation, zip_code = row
            con.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                (int(user_id), int(age), gender, occupation, zip_code),
            )

        for line_number, row in read_delimited(raw_dir, "u.item", "|", 24):
            movie_id, title, release_date, video_release_date, imdb_url = row[:5]
            movie_id = int(movie_id)
            con.execute(
                "INSERT INTO movies VALUES (?, ?, ?, ?, ?)",
                (
                    movie_id,
                    title,
                    release_date or None,
                    video_release_date or None,
                    imdb_url or None,
                ),
            )

            genre_flags = row[5:]
            if len(genre_flags) != len(genres):
                raise ValueError(
                    f"u.item:{line_number}: expected {len(genres)} genre flags, "
                    f"found {len(genre_flags)}"
                )
            for genre_id, flag in zip(sorted(genres), genre_flags):
                if flag not in ("0", "1"):
                    raise ValueError(
                        f"u.item:{line_number}: invalid genre flag {flag!r}"
                    )
                if flag == "1":
                    con.execute(
                        "INSERT INTO movie_genres VALUES (?, ?)",
                        (movie_id, genre_id),
                    )

        for _, row in read_delimited(raw_dir, "u.data", "\t", 4):
            user_id, movie_id, rating, timestamp = row
            con.execute(
                "INSERT INTO ratings VALUES (?, ?, ?, ?)",
                (int(user_id), int(movie_id), int(rating), int(timestamp)),
            )

        counts = {
            table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in TABLES
        }
        con.commit()
    finally:
        con.close()

    for table, count in counts.items():
        print(f"{table:12s} {count} rows")
    print("rejected.csv unchanged; this reload does not write a rejection report")


def main():
    parser = argparse.ArgumentParser(
        description="Clear and reload the MovieLens database from all raw files."
    )
    parser.add_argument("raw_dir", type=Path, help="directory containing the u.* files")
    parser.add_argument("db_path", type=Path, help="path for the rebuilt SQLite database")
    args = parser.parse_args()
    load_database(args.raw_dir, args.db_path)


if __name__ == "__main__":
    main()
