import db

class video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    #imagem= definir como salvar a foto da capa do vídeo
    titulo = db.Column(db.String, nullable=True)
    autor = db.Column(db.String, nullable=True)
    genero = db.Column(db.String, nullable=True)
    link = db.Column(db.String, nullable=True)
    analise = db.Column(db.String, nullable=True)