import os
from pathlib import Path

from flask_sqlalchemy import SQLAlchemy

# Instância do SQLAlchemy usada pelos modelos.
db = SQLAlchemy()


def get_database_uri():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        # Sem DATABASE_URL: usa SQLite local (desenvolvimento)
        project_root = Path(__file__).resolve().parents[2]
        instance_dir = project_root / "instance"
        instance_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(instance_dir / 'libraryvid.db').as_posix()}"

    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("mysql://"):
        return database_url.replace("mysql://", "mysql+pymysql://", 1)
    return database_url