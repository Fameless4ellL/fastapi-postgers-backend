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

