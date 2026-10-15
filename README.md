# cert_registry

## Połączenie z PostgreSQL

Skrypty importu (`import_certificates.py`, `import_registry.py`, `import_relations.py`) nie mają zahardkodowanych danych połączenia. Wywołują `psycopg.connect()` bez argumentów, więc libpq pobiera parametry ze standardowych zmiennych środowiskowych:

| Zmienna      | Znaczenie        |
|--------------|------------------|
| `PGHOST`     | host bazy        |
| `PGDATABASE` | nazwa bazy       |
| `PGUSER`     | użytkownik       |
| `PGPASSWORD` | hasło            |

Zmienne te są ustawiane w:

- [compose.yaml](compose.yaml) – `PGHOST: db`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` (z `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`). Przed `docker compose up` trzeba ustawić `POSTGRES_PASSWORD` (zmienna środowiskowa lub plik `.env`).
- [.devcontainer/docker-compose.yml](.devcontainer/docker-compose.yml) – to samo dla devcontainera (hasło `devcontainer`).

Parametry samego serwera bazy (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`) są w usłudze `db` w tych samych plikach. [Dockerfile](Dockerfile) instaluje tylko `postgresql-client` (`psql`).

Aby zmienić dane połączenia, zmień powyższe zmienne albo przekaż parametry wprost, np. `psycopg.connect("postgresql://user:pass@host/db")`.
