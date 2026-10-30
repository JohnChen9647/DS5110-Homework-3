
import argparse
import csv
import datetime
import json
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"
TABLES = ("occupations", "users", "movies", "genres", "movie_genres", "ratings")


def parse_number(value, kind):
    """Convert valid numeric text and leave invalid text for SQLite to reject."""
    if value == "":
        return None
    try:
        return kind(value)
    except ValueError:
        return value


def record_rejection(rejected, source_file, line_number, table, raw_row, error):
    rejected.append(
        (
            source_file,
            line_number,
            table,
            json.dumps(raw_row, ensure_ascii=True),
            str(error),
        )
    )


def read_delimited(raw_dir, filename, delimiter, field_count, table, rejected):
    """Yield validly decoded, correctly shaped records; report malformed lines."""
    path = raw_dir / filename
    with path.open("rb") as source:
        for line_number, raw_line in enumerate(source, 1):
            raw_text = raw_line.decode("utf-8", errors="backslashreplace").rstrip("\r\n")
            try:
                text = raw_line.decode("utf-8")
            except UnicodeDecodeError as error:
                record_rejection(
                    rejected,
                    filename,
                    line_number,
                    table,
                    raw_text,
                    f"invalid UTF-8: {error}",
                )
                continue

            try:
                row = next(csv.reader([text], delimiter=delimiter))
            except csv.Error as error:
                record_rejection(
                    rejected,
                    filename,
                    line_number,
                    table,
                    raw_text,
                    f"invalid delimited row: {error}",
                )
                continue

            if not row:
                continue
            if len(row) != field_count:
                record_rejection(
                    rejected,
                    filename,
                    line_number,
                    table,
                    row,
                    f"expected {field_count} fields, found {len(row)}",
                )
                continue
            yield line_number, row


def required_field_error(row, fields):
    missing = [name for index, name in fields if row[index] == ""]
    if missing:
        return "empty required field(s): " + ", ".join(missing)
    return None


def release_date_error(value):
    if value == "":
        return None

    match = re.fullmatch(r"(\d{2})-([A-Za-z]{3})-(\d{4})", value)
    if match is None:
        return f"invalid release date {value!r}; expected DD-MMM-YYYY"

    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    month = months.get(match.group(2).lower())
    if month is None:
        return f"invalid release date {value!r}; expected an English month abbreviation"

    try:
        datetime.date(int(match.group(3)), month, int(match.group(1)))
    except ValueError as error:
        return f"invalid release date {value!r}: {error}"
    return None


def insert(con, rejected, table, values, raw_row, source_file, line_number):
    placeholders = ", ".join("?" for _ in values)
    try:
        con.execute(f"INSERT INTO {table} VALUES ({placeholders})", values)
    except sqlite3.Error as error:
        record_rejection(
            rejected, source_file, line_number, table, raw_row, error
        )
        return False
    return True


def read_occupations(raw_dir, con, rejected):
    path = raw_dir / "u.occupation"
    with path.open("rb") as source:
        for line_number, raw_line in enumerate(source, 1):
            raw_text = raw_line.decode("utf-8", errors="backslashreplace").rstrip("\r\n")
            try:
                occupation = raw_line.decode("utf-8").rstrip("\r\n")
            except UnicodeDecodeError as error:
                record_rejection(
                    rejected,
                    path.name,
                    line_number,
                    "occupations",
                    raw_text,
                    f"invalid UTF-8: {error}",
                )
                continue
            if occupation == "":
                record_rejection(
                    rejected,
                    path.name,
                    line_number,
                    "occupations",
                    occupation,
                    "empty required field: occupation",
                )
                continue
            insert(
                con,
                rejected,
                "occupations",
                (occupation,),
                occupation,
                path.name,
                line_number,
            )


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

    rejected = []
    con = sqlite3.connect(db_path)
    try:
        con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        con.execute("PRAGMA foreign_keys = ON")

        read_occupations(raw_dir, con, rejected)

        genres = {}
        for line_number, row in read_delimited(
            raw_dir, "u.genre", "|", 2, "genres", rejected
        ):
            if row == ["", ""]:
                continue
            error = required_field_error(row, ((0, "name"), (1, "genre_id")))
            if error:
                record_rejection(rejected, "u.genre", line_number, "genres", row, error)
                continue
            name, genre_id = row
            genre_id = parse_number(genre_id, int)
            inserted = insert(
                con,
                rejected,
                "genres",
                (genre_id, name),
                row,
                "u.genre",
                line_number,
            )
            if inserted and isinstance(genre_id, int):
                genres[genre_id] = name

        for line_number, row in read_delimited(
            raw_dir, "u.user", "|", 5, "users", rejected
        ):
            error = required_field_error(
                row,
                (
                    (0, "user_id"),
                    (1, "age"),
                    (2, "gender"),
                    (3, "occupation"),
                    (4, "zip"),
                ),
            )
            if error:
                record_rejection(rejected, "u.user", line_number, "users", row, error)
                continue

            user_id, age, gender, occupation, zip_code = row
            values = (
                parse_number(user_id, int),
                parse_number(age, int),
                gender,
                occupation,
                zip_code,
            )
            insert(
                con, rejected, "users", values, row, "u.user", line_number
            )

        for line_number, row in read_delimited(
            raw_dir, "u.item", "|", 24, "movies", rejected
        ):
            error = required_field_error(row, ((0, "movie_id"), (1, "title")))
            if error:
                record_rejection(rejected, "u.item", line_number, "movies", row, error)
                continue

            movie_id, title, release_date, video_release_date, imdb_url = row[:5]
            error = release_date_error(release_date)
            if error:
                record_rejection(rejected, "u.item", line_number, "movies", row, error)
                continue

            genre_flags = row[5:]
            if len(genre_flags) != len(genres):
                record_rejection(
                    rejected,
                    "u.item",
                    line_number,
                    "movies",
                    row,
                    f"expected {len(genres)} genre flags, found {len(genre_flags)}",
                )
                continue
            invalid_flag = next(
                (flag for flag in genre_flags if flag not in ("0", "1")), None
            )
            if invalid_flag is not None:
                record_rejection(
                    rejected,
                    "u.item",
                    line_number,
                    "movies",
                    row,
                    f"invalid genre flag {invalid_flag!r}; expected '0' or '1'",
                )
                continue

            movie_values = (
                parse_number(movie_id, int),
                title,
                release_date or None,
                video_release_date or None,
                imdb_url or None,
            )
            if not insert(
                con,
                rejected,
                "movies",
                movie_values,
                row,
                "u.item",
                line_number,
            ):
                continue

            for genre_id, flag in zip(sorted(genres), genre_flags):
                if flag == "1":
                    insert(
                        con,
                        rejected,
                        "movie_genres",
                        (parse_number(movie_id, int), genre_id),
                        row,
                        "u.item",
                        line_number,
                    )

        for line_number, row in read_delimited(
            raw_dir, "u.data", "\t", 4, "ratings", rejected
        ):
            error = required_field_error(
                row,
                (
                    (0, "user_id"),
                    (1, "movie_id"),
                    (2, "rating"),
                    (3, "timestamp"),
                ),
            )
            if error:
                record_rejection(rejected, "u.data", line_number, "ratings", row, error)
                continue

            user_id, movie_id, rating, timestamp = row
            values = (
                parse_number(user_id, int),
                parse_number(movie_id, int),
                parse_number(rating, int),
                parse_number(timestamp, int),
            )
            insert(
                con, rejected, "ratings", values, row, "u.data", line_number
            )

        con.commit()
        counts = {
            table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in TABLES
        }
    finally:
        con.close()

    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    with (output_dir / "rejected.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["source_file", "line_number", "table", "row", "error"])
        writer.writerows(rejected)

    for table, count in counts.items():
        print(f"{table:12s} {count} rows")
    print(f"{'rejected':12s} {len(rejected)} rows -> output/rejected.csv")


def main():
    parser = argparse.ArgumentParser(description="Build the MovieLens SQLite database.")
    parser.add_argument("raw_dir", type=Path, help="directory containing the u.* source files")
    parser.add_argument("db_path", type=Path, help="path for the generated SQLite database")
    args = parser.parse_args()
    load_database(args.raw_dir, args.db_path)


if __name__ == "__main__":
    main()
