import logging
import mysql.connector
from flask_sqlalchemy import SQLAlchemy

# Instância do SQLAlchemy usada pelos modelos.
db = SQLAlchemy()


# Conexão direta com mysql.connector, caso precise usar cursor puro.
def conectar():
    try:
        return mysql.connector.connect(
            host="localhost",
            port=3307,
            user="root",
            password="",
            database="libraryvid",
        )
    except mysql.connector.Error as e:
        logging.exception("Falha na conexão MySQL")
        raise

