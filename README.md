# bingo-backend
## alembic
### Init
```bash
docker compose -f docker-compose.dev.yaml exec api alembic -c alembic_logs.ini init -t async alembic_logs
```
```bash
docker compose -f docker-compose.dev.yaml exec api alembic -c alembic.ini init -t async alembic
```
### makemigrations
```bash
docker compose -f docker-compose.dev.yaml exec api alembic -c alembic_logs.ini revision --autogenerate -m "Initial migration for second_db"
```

### migrate
```bash
docker compose -f docker-compose.dev.yaml exec api  alembic -c alembic_logs.ini upgrade head
```