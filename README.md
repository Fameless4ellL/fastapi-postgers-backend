# bingo-backend
## alembic
### Init
```bash
docker compose -f docker-compose.dev.yaml exec api alembic -n {} -t async {name}
```
```bash
docker compose -f docker-compose.dev.yaml exec api alembic -n {} init -t async {name}
```
### makemigrations
```bash
docker compose -f docker-compose.dev.yaml exec api alembic -n {} revision --autogenerate -m "Initial migration for second_db"
```

### migrate
```bash
docker compose -f docker-compose.dev.yaml exec api  alembic -n {} upgrade head
```