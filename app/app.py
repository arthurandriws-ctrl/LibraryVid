try:
    from .db import db
    from .models import Video
except (ImportError, ValueError):
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from db import db
    from models import Video

from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"))
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://root:@localhost:3307/libraryvid"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

with app.app_context():
    db.create_all()
    
@app.route("/")
def homepage():
    return render_template("index.html")

# trabalhar no formulário de newvideo(70% pronto, falta só upload da imagem), e usar dados_video como variável para ia.py
@app.route("/newvideo", methods=["GET", "POST"])
def videonovo():
    if request.method == "POST":
        titulo = request.form.get("titulo")
        autor = request.form.get("autor")
        genero = request.form.get("genero")
        link = request.form.get("link")

        novo_video = Video(
            titulo=titulo,
            autor=autor,
            genero=genero,
            link=link,
        )

        db.session.add(novo_video)
        db.session.commit()
        return redirect(url_for("homepage"))

    return render_template("newvideo.html")

@app.route("/estatisticas")
def estatisticas():
    return render_template("estatistica.html")

if __name__ == '__main__':
    app.run(debug=True)