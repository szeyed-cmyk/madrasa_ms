Runtime data folder. Only .gitkeep and this README ship here.

The app creates this folder on start if it is missing (app/config.py: mkdir(parents=True, exist_ok=True)).
At runtime it holds madrasa.db (SQLite, plus -wal/-shm), backups/ and .secret_key (generated session key
when SECRET_KEY is empty). These files are ignored by .gitignore/.dockerignore and are never shipped.
If a .secret_key was ever shared, delete it (a new one is generated) or set SECRET_KEY; all sessions end.
