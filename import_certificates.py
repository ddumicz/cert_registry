import argparse
import csv
import ipaddress
import os
import re
import sys
import tempfile
from datetime import date, datetime, time, timezone
from pathlib import Path

import psycopg


FIELDNAMES = ("ip_address", "sha256", "subject", "issuer", "valid_to")
ERROR_FIELDNAMES = ("line_number", *FIELDNAMES, "error")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def write_error_report(report_path: Path, errors: list[dict[str, str]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=report_path.parent,
            delete=False,
        ) as report_file:
            temporary_path = Path(report_file.name)
            writer = csv.DictWriter(
                report_file,
                fieldnames=ERROR_FIELDNAMES,
                delimiter=";",
            )
            writer.writeheader()
            writer.writerows(errors)
        temporary_path.replace(report_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def import_certificates(
    csv_path: Path, error_report_path: Path
) -> tuple[int, int, int]:
    if csv_path.resolve() == error_report_path.resolve():
        raise ValueError("Raport bledow nie moze nadpisac pliku wejsciowego.")

    linked = 0
    new_links = 0
    errors: list[dict[str, str]] = []
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
                    if all(
                        value is None
                        or isinstance(value, str)
                        and not value.strip()
                        or isinstance(value, list)
                        and not value
                        for value in row.values()
                    ):
                        continue

                    source_values = {
                        field: row.get(field) or "" for field in FIELDNAMES
                    }
                    problem = None
                    if None in row:
                        problem = "Za duzo kolumn."

                    ip_address = source_values["ip_address"].strip()
                    sha256 = source_values["sha256"].strip().lower()
                    subject = source_values["subject"].strip() or None
                    issuer = source_values["issuer"].strip() or None
                    valid_to_text = source_values["valid_to"].strip()

                    if problem is None and not ip_address:
                        problem = "Brak wymaganego adresu IP."
                    if problem is None:
                        try:
                            ip_address = str(ipaddress.ip_address(ip_address))
                        except ValueError:
                            problem = (
                                f"Nieprawidlowy adres IP "
                                f"{source_values['ip_address']!r}."
                            )
                    if problem is None and not SHA256_PATTERN.fullmatch(sha256):
                        problem = "SHA-256 musi zawierac dokladnie 64 znaki hex."
                    if problem is None and not valid_to_text:
                        problem = "Brak wymaganej daty valid_to."

                    valid_to = None
                    if problem is None:
                        try:
                            valid_to_date = date.fromisoformat(valid_to_text)
                            valid_to = datetime.combine(
                                valid_to_date,
                                time.min,
                                tzinfo=timezone.utc,
                            )
                        except ValueError:
                            problem = (
                                f"Nieprawidlowa data valid_to "
                                f"{valid_to_text!r}; oczekiwano YYYY-MM-DD."
                            )

                    asset_ids: list[int] = []
                    if problem is None:
                        cursor.execute(
                            """
                            SELECT id, asset_key
                            FROM cert_registry.assets
                            WHERE ip_address = %s::inet
                            ORDER BY id
                            LIMIT 2
                            """,
                            (ip_address,),
                        )
                        matched_assets = cursor.fetchall()
                        if not matched_assets:
                            problem = f"Brak zasobu z adresem IP {ip_address}."
                        elif len(matched_assets) > 1:
                            asset_keys = ", ".join(
                                asset_key for _, asset_key in matched_assets
                            )
                            problem = (
                                f"Adres IP {ip_address} pasuje do wielu zasobow; "
                                f"asset_key: {asset_keys}; wymaga uzgodnienia."
                            )

                    if problem is not None:
                        errors.append(
                            {
                                "line_number": str(line_number),
                                **source_values,
                                "error": problem,
                            }
                        )
                        continue

                    cursor.execute(
                        """
                        INSERT INTO cert_registry.certificates
                            (sha256, subject, issuer, valid_to)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (sha256) DO UPDATE
                        SET subject = EXCLUDED.subject,
                            issuer = EXCLUDED.issuer,
                            valid_to = EXCLUDED.valid_to
                        RETURNING id
                        """,
                        (sha256, subject, issuer, valid_to),
                    )
                    (certificate_id,) = cursor.fetchone()
                    cursor.execute(
                        """
                        INSERT INTO cert_registry.certificate_assets
                            (certificate_id, asset_id)
                        VALUES (%s, %s)
                        ON CONFLICT (certificate_id, asset_id) DO NOTHING
                        """,
                        (certificate_id, matched_assets[0][0]),
                    )
                    linked += 1
                    new_links += cursor.rowcount

            write_error_report(error_report_path, errors)

    return linked, new_links, len(errors)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Import wykryc certyfikatow Tenable SC i powiazan z zasobami CMDB."
        )
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        default=os.environ.get(
            "CERTIFICATES_CSV_FILE", "/data/tenable_certificates.csv"
        ),
        type=Path,
        help="Sciezka do tenable_certificates.csv.",
    )
    parser.add_argument(
        "--error-report",
        default=os.environ.get(
            "CERTIFICATE_ERROR_REPORT",
            str(
                Path(__file__).resolve().parent
                / "reports"
                / "tenable_certificates_errors.csv"
            ),
        ),
        type=Path,
        help="Sciezka raportu wierszy wymagajacych uzgodnienia.",
    )
    args = parser.parse_args()

    try:
        linked, new_links, error_count = import_certificates(
            args.csv_file, args.error_report
        )
    except (
        OSError,
        UnicodeError,
        csv.Error,
        psycopg.Error,
        ValueError,
    ) as error:
        print(f"Blad importu certyfikatow: {error}", file=sys.stderr)
        return 1

    print(
        f"Przetworzono {linked} wykryc, utworzono {new_links} nowych "
        f"powiazan; {error_count} wierszy wymaga uzgodnienia. "
        f"Raport: {args.error_report}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
