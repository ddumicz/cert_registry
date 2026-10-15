import argparse
import csv
import os
import sys
from pathlib import Path

import psycopg


FIELDNAMES = ("parent_asset_key", "child_asset_key", "relation_type")


def import_relations(csv_path: Path) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        if reader.fieldnames != list(FIELDNAMES):
            raise ValueError(
                "Nieprawidlowy naglowek CSV. Oczekiwano: "
                + ";".join(FIELDNAMES)
            )

        with psycopg.connect() as connection:
            with connection.cursor() as cursor:
                for row in reader:
                    line_number = reader.line_num
                    if None in row:
                        raise ValueError(
                            f"Wiersz {line_number}: za duzo kolumn."
                        )
                    if all(
                        value is None or not value.strip()
                        for value in row.values()
                    ):
                        continue

                    parent_key = (row["parent_asset_key"] or "").strip()
                    child_key = (row["child_asset_key"] or "").strip()
                    relation_type = (row["relation_type"] or "").strip()
                    if not parent_key or not child_key or not relation_type:
                        raise ValueError(
                            f"Wiersz {line_number}: parent_asset_key, "
                            "child_asset_key i relation_type sa wymagane."
                        )
                    if parent_key == child_key:
                        raise ValueError(
                            f"Wiersz {line_number}: zasob nie moze byc "
                            "powiazany sam ze soba."
                        )

                    cursor.execute(
                        """
                        SELECT
                            (SELECT id FROM cert_registry.assets
                             WHERE asset_key = %s),
                            (SELECT id FROM cert_registry.assets
                             WHERE asset_key = %s)
                        """,
                        (parent_key, child_key),
                    )
                    parent_id, child_id = cursor.fetchone()
                    if parent_id is None:
                        raise ValueError(
                            f"Wiersz {line_number}: nie znaleziono zasobu "
                            f"parent_asset_key={parent_key!r}."
                        )
                    if child_id is None:
                        raise ValueError(
                            f"Wiersz {line_number}: nie znaleziono zasobu "
                            f"child_asset_key={child_key!r}."
                        )

                    cursor.execute(
                        """
                        INSERT INTO cert_registry.asset_relations
                            (parent_asset_id, child_asset_id, relation_type)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (
                            parent_asset_id, child_asset_id, relation_type
                        ) DO NOTHING
                        """,
                        (parent_id, child_id, relation_type),
                    )
                    if cursor.rowcount:
                        inserted += 1
                    else:
                        skipped += 1

    return inserted, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import relacji CMDB z pliku CSV rozdzielanego srednikami."
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        default=os.environ.get("RELATIONS_CSV_FILE", "/data/mdb_relations.csv"),
        type=Path,
        help=(
            "Sciezka do cmdb_relations.csv "
            "(domyslnie: /data/mdb_relations.csv)."
        ),
    )
    args = parser.parse_args()

    try:
        inserted, skipped = import_relations(args.csv_file)
    except (OSError, UnicodeError, csv.Error, psycopg.Error, ValueError) as error:
        print(f"Blad importu relacji: {error}", file=sys.stderr)
        return 1

    print(
        f"Dodano {inserted} relacji; pominięto {skipped} "
        "juz istniejacych."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
