import argparse
import csv
import ipaddress
import os
import sys
from pathlib import Path

import psycopg


FIELDNAMES = ("asset_key", "asset_name", "asset_type", "ip_address")


def import_assets(csv_path: Path) -> int:
    imported = 0
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

                    asset_key = (row["asset_key"] or "").strip()
                    asset_name = (row["asset_name"] or "").strip()
                    asset_type = (row["asset_type"] or "").strip()
                    ip_address = (row["ip_address"] or "").strip() or None

                    if not asset_key or not asset_name or not asset_type:
                        raise ValueError(
                            f"Wiersz {line_number}: asset_key, asset_name "
                            "i asset_type sa wymagane."
                        )
                    if ip_address is not None:
                        try:
                            ipaddress.ip_address(ip_address)
                        except ValueError as error:
                            raise ValueError(
                                f"Wiersz {line_number}: nieprawidlowy adres IP "
                                f"{ip_address!r}."
                            ) from error

                    cursor.execute(
                        """
                        INSERT INTO cert_registry.assets
                            (asset_key, asset_name, asset_type, ip_address)
                        VALUES (%s, %s, %s, %s::inet)
                        ON CONFLICT (asset_key) DO UPDATE
                        SET asset_name = EXCLUDED.asset_name,
                            asset_type = EXCLUDED.asset_type,
                            ip_address = EXCLUDED.ip_address,
                            updated_at = now()
                        """,
                        (asset_key, asset_name, asset_type, ip_address),
                    )
                    imported += 1
    return imported


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import zasobow CMDB z pliku CSV rozdzielanego srednikami."
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        default=os.environ.get("CSV_FILE", "/data/cmdb_assets.csv"),
        type=Path,
        help="Sciezka do cmdb_assets.csv (domyslnie: /data/cmdb_assets.csv).",
    )
    args = parser.parse_args()

    try:
        imported = import_assets(args.csv_file)
    except (OSError, UnicodeError, csv.Error, psycopg.Error, ValueError) as error:
        print(f"Blad importu: {error}", file=sys.stderr)
        return 1

    print(f"Zaimportowano lub zaktualizowano {imported} zasobow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
