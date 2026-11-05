try:
    from .db import db
except (ImportError, ValueError):
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from db import db


class Usuario(db.Model):
    __tablename__ = "usuario"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    senha_original = db.Column(db.String(255), nullable=True)
    foto_perfil = db.Column(db.String(255), nullable=True)
    criado_em = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    videos = db.relationship(
        "Video",
        backref="usuario",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Parceiro(db.Model):
    __tablename__ = "parceiro"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False)
    tipo = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="Ativo")
    site_url = db.Column(db.String(500), nullable=True)
    contato_url = db.Column(db.String(500), nullable=True)


class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=True, index=True)
    tipo = db.Column(db.String(16), nullable=False, default="video", server_default="video", index=True)
    imagem = db.Column(db.String(255), nullable=True)
    titulo = db.Column(db.String(255), nullable=True)
    autor = db.Column(db.String(255), nullable=True)
    genero = db.Column(db.String(100), nullable=True)
    link = db.Column(db.String(255), nullable=True)
    analise = db.Column(db.Text, nullable=True)
    avaliacoes = db.relationship(
        "Avaliacao",
        backref="video",
        lazy=True,
        cascade="all, delete-orphan"
    )

    @property
    def total_avaliacoes(self):
        return len(self.avaliacoes)

    @property
    def media_avaliacao(self):
        if not self.avaliacoes:
            return 0
        return sum(avaliacao.nota for avaliacao in self.avaliacoes) / len(self.avaliacoes)


class Avaliacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nota = db.Column(db.Integer, nullable=False)
    votante_id = db.Column(db.String(64), nullable=True)
    video_id = db.Column(db.Integer, db.ForeignKey("video.id"), nullable=False)