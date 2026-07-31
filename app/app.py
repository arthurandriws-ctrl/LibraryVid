try:
    from .db import db
    from .models import Video
except (ImportError, ValueError):
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from db import db
    from models import Video

from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
from sqlalchemy import or_, inspect, text
import os

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "..", "static")
)
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "..", "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["ALLOWED_IMAGE_EXTENSIONS"] = {"png", "jpg", "jpeg", "webp"}
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://root:@localhost:3307/libraryvid"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
db.init_app(app)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_IMAGE_EXTENSIONS"]

with app.app_context():
    db.create_all()
    inspector = inspect(db.engine)
    columns = [col["name"] for col in inspector.get_columns("video")]
    if "imagem" not in columns:
        db.session.execute(text("ALTER TABLE video ADD COLUMN imagem VARCHAR(255) NULL"))
        db.session.commit()

@app.route("/")
def homepage():
    videos = Video.query.order_by(Video.id.desc()).all()
    return render_template("index.html", videos=videos)

# usar dados_video como variável para ia.py

@app.route("/newvideo", methods=["GET", "POST"])
def videonovo():
    if request.method == "POST":
        imagem = request.files.get("imagem")
        imagem_filename = None

        if imagem and imagem.filename and allowed_file(imagem.filename):
            filename = secure_filename(imagem.filename)
            imagem.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            imagem_filename = filename

        titulo = request.form.get("titulo")
        autor = request.form.get("autor")
        genero = request.form.get("genero")
        link = request.form.get("link")

        novo_video = Video(
            titulo=titulo,
            autor=autor,
            genero=genero,
            link=link,
            imagem=imagem_filename
        )

        db.session.add(novo_video)
        db.session.commit()
        return redirect(url_for("homepage"))

    return render_template("newvideo.html")

@app.route("/estatisticas")
def estatisticas():
    return render_template("estatistica.html")


@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return redirect(url_for('homepage'))

    results = Video.query.filter(
        or_(
            Video.titulo.ilike(f"%{q}%"),
            Video.autor.ilike(f"%{q}%")
        )
    ).all()

    return render_template('resultados.html', query=q, results=results)


@app.route("/editar/<int:video_id>", methods=["GET", "POST"])
def editar_video(video_id):
    video = Video.query.get_or_404(video_id)
    
    if request.method == "POST":
        # Processar nova imagem se fornecida
        if "imagem" in request.files:
            imagem = request.files.get("imagem")
            if imagem and imagem.filename and allowed_file(imagem.filename):
                # Deletar imagem antiga se existir
                if video.imagem:
                    old_path = os.path.join(app.config["UPLOAD_FOLDER"], video.imagem)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                # Salvar nova imagem
                filename = secure_filename(imagem.filename)
                imagem.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                video.imagem = filename
        
        # Atualizar outros campos
        video.titulo = request.form.get("titulo")
        video.autor = request.form.get("autor")
        video.genero = request.form.get("genero")
        video.link = request.form.get("link")
        video.analise = request.form.get("analise")
        
        db.session.commit()
        return redirect(url_for("homepage"))
    
    return render_template("editar_video.html", video=video)


@app.route("/deletar/<int:video_id>", methods=["POST"])
def deletar_video(video_id):
    video = Video.query.get_or_404(video_id)
    
    # Deletar imagem se existir
    if video.imagem:
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], video.imagem)
        if os.path.exists(image_path):
            os.remove(image_path)
    
    db.session.delete(video)
    db.session.commit()
    return redirect(url_for("homepage"))

if __name__ == '__main__':
    app.run(debug=True)