import mysql.connector
from sqlalchemy import create_engine, text 
from sqlalchemy.orm import declarative_base, sessionmaker

def conectar():
    try: 
        return mysql.connector.connect(
            host="localhost",
            port=3307, 
            user="root", 
            password="",
            database="libraryvid",
        )
    except mysql.connector.Error:
        return None 
