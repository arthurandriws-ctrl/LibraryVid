try:
    from .db import db
except (ImportError, ValueError):
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from db import db



class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # imagem: definir como salvar a foto da capa do vídeo
    titulo = db.Column(db.String(255), nullable=True)
    autor = db.Column(db.String(255), nullable=True)
    genero = db.Column(db.String(100), nullable=True)
    link = db.Column(db.String(255), nullable=True)
    analise = db.Column(db.Text, nullable=True)