# bingo-backend
This is the backend for bingo app. It is built with FastAPI and uses PostgreSQL as the database.
It also uses Alembic for database migrations and Docker for containerization.
Client didn't pay for this project, so it is open source now and free to use.
## alembic
### Init
```bash
docker compose -f docker-compose.dev.yaml exec api alembic -n {db} -t async {name}
```
```bash
docker compose -f docker-compose.dev.yaml exec api alembic -n {db} init -t async {name}
```
### makemigrations
```bash
docker compose -f docker-compose.dev.yaml exec api alembic -n {db} revision --autogenerate -m "Initial migration for second_db"
```

### migrate
```bash
docker compose -f docker-compose.dev.yaml exec api  alembic -n {db} upgrade head
```

## test
```bash
pytest --cov-report html:cov_html --cov-config=.coveragerc --cov=src src/tests/test_routers/test_user.py 
```

## utils cli
```bash
docker compose -f docker-compose.dev.yaml exec -T {db} psql -U postgres -d postgres -c "\dt" | awk '{if (NR>3) print $3}' | xargs -I {} docker compose -f docker-compose.dev.yaml exec -T {db} psql -U postgres -d postgres -c "\d {}"
```