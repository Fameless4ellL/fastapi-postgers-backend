# bingo-backend
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

## utils cli
```bash
docker compose -f docker-compose.dev.yaml exec -T {db} psql -U postgres -d postgres -c "\dt" | awk '{if (NR>3) print $3}' | xargs -I {} docker compose -f docker-compose.dev.yaml exec -T {db} psql -U postgres -d postgres -c "\d {}"
```