try:
    from .db import db
    from .db import get_database_uri
    from .models import Avaliacao, Parceiro, Usuario, Video
    from .ia import analisar_video
except (ImportError, ValueError):
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from db import db
    from db import get_database_uri
    from models import Avaliacao, Parceiro, Usuario, Video
    from ia import analisar_video

import json
import os
import urllib.request
import uuid
from functools import wraps

import click
from flask import Flask, abort, flash, render_template, request, redirect, session, url_for
from flask_migrate import Migrate
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import inspect, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from urllib.parse import urlparse

try:
    import cloudinary
    import cloudinary.uploader
except ImportError:  # pacote não instalado: usa disco local
    cloudinary = None

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "..", "static")
)

# Atrás do proxy do Render: garante que url_for(_external=True) gere https://
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# O Render define RENDER=true automaticamente
IS_PRODUCTION = bool(os.getenv("RENDER")) or os.getenv("FLASK_ENV") == "production"

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "..", "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["ALLOWED_IMAGE_EXTENSIONS"] = {"png", "jpg", "jpeg", "webp"}
app.config["SQLALCHEMY_DATABASE_URI"] = get_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Neon suspende o computo quando ocioso: evita erros com conexões antigas
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}

secret_key = os.getenv("SECRET_KEY")
if IS_PRODUCTION and not secret_key:
    raise RuntimeError("SECRET_KEY precisa ser configurada em produção")
app.config["SECRET_KEY"] = secret_key or "libraryvid-dev-key"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv(
    "SESSION_COOKIE_SECURE", "1" if IS_PRODUCTION else "0"
) == "1"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db.init_app(app)
migrate = Migrate(app, db)

# Cloudinary é configurado pela variável de ambiente CLOUDINARY_URL
USE_CLOUDINARY = cloudinary is not None and bool(os.getenv("CLOUDINARY_URL"))


@app.before_request
def ensure_authenticated_routes():
    if request.endpoint in {"login", "cadastro", "logout", "static", "esqueci_senha", "redefinir_senha"}:
        if request.endpoint in {"login", "cadastro"} and "usuario_id" in session:
            return redirect(url_for("homepage"))
        return None

    usuario_id = session.get("usuario_id")
    if usuario_id is None:
        return redirect(url_for("login", next=request.path))

    if db.session.get(Usuario, usuario_id) is None:
        session.clear()
        return redirect(url_for("login", next=request.path))

    return None


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


def _next_seguro(url):
    """Aceita apenas caminhos internos (evita open redirect)."""
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return None


def owned_videos_query():
    usuario_id = session.get("usuario_id")
    if usuario_id is None:
        return Video.query.filter(Video.usuario_id.is_(None))

    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        session.clear()
        return Video.query.filter(Video.usuario_id.is_(None))

    return Video.query.filter(Video.usuario_id == usuario_id)


def get_owned_video_or_404(video_id):
    return owned_videos_query().filter(Video.id == video_id).first_or_404()


TIPOS_CATALOGO = {"video", "livro"}


def catalog_type(value=None):
    tipo = value if value is not None else request.args.get("tipo", "video")
    if tipo not in TIPOS_CATALOGO:
        abort(400)
    return tipo


def owned_items_query(tipo):
    return owned_videos_query().filter(Video.tipo == tipo)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_IMAGE_EXTENSIONS"]


def salvar_imagem(arquivo, prefixo="img"):
    """Salva a imagem e devolve o valor a gravar no banco (URL ou nome do arquivo).
    Devolve None se o upload falhar."""
    try:
        if USE_CLOUDINARY:
            resultado = cloudinary.uploader.upload(
                arquivo.stream, folder="libraryvid", resource_type="image"
            )
            return resultado["secure_url"]

        filename = f"{prefixo}_{uuid.uuid4().hex}_{secure_filename(arquivo.filename)}"
        arquivo.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        return filename
    except Exception as exc:
        print(f"[IMAGEM] falha ao salvar: {exc}")
        return None


def remover_imagem(valor):
    """Remove uma imagem salva por salvar_imagem (URL do Cloudinary ou arquivo local)."""
    if not valor:
        return

    if valor.startswith("http"):
        if USE_CLOUDINARY and "/upload/" in valor:
            partes = valor.split("/upload/", 1)[1].split("/")
            if partes and partes[0].startswith("v") and partes[0][1:].isdigit():
                partes = partes[1:]  # descarta a versão (v123456)
            public_id = "/".join(partes).rsplit(".", 1)[0]
            try:
                cloudinary.uploader.destroy(public_id)
            except Exception as exc:
                print(f"[IMAGEM] falha ao remover {public_id}: {exc}")
        return

    caminho = os.path.join(app.config["UPLOAD_FOLDER"], valor)
    if os.path.exists(caminho):
        os.remove(caminho)


@app.template_global()
def imagem_url(valor):
    """Use nos templates: <img src="{{ imagem_url(video.imagem) }}">"""
    if not valor:
        return None
    if valor.startswith("http"):
        return valor
    return url_for("static", filename=f"uploads/{valor}")


@app.cli.command("parceiro-add")
@click.option("--nome", required=True, help="Nome do parceiro.")
@click.option("--tipo", default="", help="Tipo ou categoria do parceiro.")
@click.option("--status", default="Ativo", show_default=True)
@click.option("--site", "site_url", default="", help="URL pública do site.")
@click.option("--contato", "contato_url", default="", help="URL de contato, mailto: ou tel:.")
def adicionar_parceiro(site_url, contato_url, nome, tipo, status):
    """Adiciona um parceiro sem disponibilizar edição no frontend."""
    parceiro = Parceiro(
        nome=nome.strip(),
        tipo=tipo.strip() or None,
        status=status.strip() or "Ativo",
        site_url=site_url.strip() or None,
        contato_url=contato_url.strip() or None,
    )
    db.session.add(parceiro)
    db.session.commit()
    click.echo(f"Parceiro '{parceiro.nome}' adicionado com ID {parceiro.id}.")


with app.app_context():
    db.create_all()
    inspector = inspect(db.engine)
    if inspector.has_table("video"):
        columns = {col["name"] for col in inspector.get_columns("video")}
        if "usuario_id" not in columns:
            db.session.execute(text("ALTER TABLE video ADD COLUMN usuario_id INTEGER"))
        if "imagem" not in columns:
            db.session.execute(text("ALTER TABLE video ADD COLUMN imagem VARCHAR(255)"))
        if "tipo" not in columns:
            db.session.execute(text("ALTER TABLE video ADD COLUMN tipo VARCHAR(16) NOT NULL DEFAULT 'video'"))
    if inspector.has_table("avaliacao"):
        avaliacao_columns = {col["name"] for col in inspector.get_columns("avaliacao")}
        if "votante_id" not in avaliacao_columns:
            db.session.execute(text("ALTER TABLE avaliacao ADD COLUMN votante_id VARCHAR(64)"))
    if inspector.has_table("usuario"):
        usuario_columns = {col["name"] for col in inspector.get_columns("usuario")}
        if "foto_perfil" not in usuario_columns:
            db.session.execute(text("ALTER TABLE usuario ADD COLUMN foto_perfil VARCHAR(255)"))
    db.session.commit()

RESET_SALT = "reset-senha"
RESET_MAX_AGE = 3600  # 1 hora


def _serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"])


def gerar_token_reset(usuario):
    # O trecho do hash faz o link parar de funcionar depois que a senha muda
    return _serializer().dumps({"id": usuario.id, "h": usuario.senha_hash[-12:]}, salt=RESET_SALT)


def validar_token_reset(token):
    try:
        dados = _serializer().loads(token, salt=RESET_SALT, max_age=RESET_MAX_AGE)
    except BadSignature:  # inclui SignatureExpired
        return None
    usuario = db.session.get(Usuario, dados.get("id"))
    if usuario is None or usuario.senha_hash[-12:] != dados.get("h"):
        return None
    return usuario


def enviar_email(destinatario, nome, assunto, texto):
    """Envia e-mail por API HTTPS (o Render grátis bloqueia SMTP).
    Usa a API da Brevo; para trocar de provedor, altere só esta função."""
    api_key = (os.getenv("BREVO_API_KEY") or "").strip()
    remetente = (os.getenv("MAIL_DEFAULT_SENDER") or "").strip()
    if not api_key or not remetente:
        print("[EMAIL] Defina BREVO_API_KEY e MAIL_DEFAULT_SENDER.")
        return False

    payload = {
        "sender": {"name": "LibraryVid", "email": remetente},
        "to": [{"email": destinatario, "name": nome}],
        "subject": assunto,
        "textContent": texto,
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": api_key,
            "content-type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        print(f"[EMAIL] falha ao enviar para {destinatario}: {exc}")
        return False


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if "usuario_id" in session:
        return redirect(url_for("homepage"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not nome or not email or len(senha) < 8:
            flash("Informe nome, e-mail e uma senha com pelo menos 8 caracteres.", "error")
            return render_template("cadastro.html")
        if Usuario.query.filter_by(email=email).first():
            flash("Este e-mail já está cadastrado.", "error")
            return render_template("cadastro.html")

        usuario = Usuario(
            nome=nome,
            email=email,
            senha_hash=generate_password_hash(senha),
        )
        db.session.add(usuario)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Este e-mail já está cadastrado.", "error")
            return render_template("cadastro.html")

        flash("Cadastro concluído. Entre para acessar sua biblioteca.", "success")
        return redirect(url_for("login"))

    return render_template("cadastro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "usuario_id" in session:
        return redirect(url_for("homepage"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        usuario = Usuario.query.filter_by(email=email).first()

        if not usuario or not check_password_hash(usuario.senha_hash, senha):
            flash("E-mail ou senha inválidos.", "error")
            return render_template("login.html", next=request.form.get("next"))

        session.clear()
        session["usuario_id"] = usuario.id
        next_url = _next_seguro(request.form.get("next") or request.args.get("next"))
        return redirect(next_url or url_for("homepage"))

    return render_template("login.html", next=request.args.get("next"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        usuario = Usuario.query.filter_by(email=email).first() if email else None

        if usuario is not None:
            link = url_for("redefinir_senha", token=gerar_token_reset(usuario), _external=True)
            enviar_email(
                usuario.email,
                usuario.nome,
                "Redefinição de senha do LibraryVid",
                f"Olá {usuario.nome},\n\n"
                f"Para criar uma nova senha, acesse o link abaixo (válido por 1 hora):\n{link}\n\n"
                "Se você não pediu isso, ignore este e-mail.\n\n"
                "Equipe LibraryVid",
            )

        # Mesma resposta exista o e-mail ou não (não revela quem tem cadastro)
        flash("Se o e-mail estiver cadastrado, enviaremos um link para redefinir a senha.", "success")
        return redirect(url_for("login"))

    return render_template("esqueci_senha.html")


@app.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def redefinir_senha(token):
    usuario = validar_token_reset(token)
    if usuario is None:
        flash("Link inválido ou expirado. Solicite um novo.", "error")
        return redirect(url_for("esqueci_senha"))

    if request.method == "POST":
        nova_senha = request.form.get("nova_senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")

        if len(nova_senha) < 8:
            flash("A nova senha precisa ter pelo menos 8 caracteres.", "error")
            return render_template("recuperar_senha.html")
        if nova_senha != confirmar_senha:
            flash("As senhas não conferem. Digite novamente.", "error")
            return render_template("recuperar_senha.html")

        usuario.senha_hash = generate_password_hash(nova_senha)
        db.session.commit()
        flash("Senha alterada com sucesso. Faça login com a nova senha.", "success")
        return redirect(url_for("login"))

    return render_template("recuperar_senha.html")


@app.route("/")
@login_required
def homepage():
    tipo = catalog_type()
    genero = request.args.get("genero", "").strip()
    query = owned_items_query(tipo)

    if genero:
        query = query.filter(Video.genero == genero)

    videos = query.order_by(Video.id.desc()).all()
    generos = [
        genero_item[0]
        for genero_item in owned_items_query(tipo).with_entities(Video.genero)
        .filter(Video.genero.isnot(None))
        .distinct()
        .order_by(Video.genero)
        .all()
    ]

    return render_template(
        "index.html",
        videos=videos,
        generos=generos,
        genero_selecionado=genero,
        tipo=tipo
    )

# usar dados_video como variável para ia.py

@app.route("/newvideo", methods=["GET", "POST"])
@login_required
def videonovo():
    tipo = catalog_type(request.form.get("tipo") if request.method == "POST" else None)
    if request.method == "POST":
        titulo = request.form.get("titulo", "").strip()
        autor = request.form.get("autor", "").strip()
        genero = request.form.get("genero", "").strip()
        link = request.form.get("link", "").strip()
        parsed_link = urlparse(link)
        if not titulo or not autor or parsed_link.scheme not in {"http", "https"} or not parsed_link.netloc:
            flash("Informe título, autor e um link válido iniciado por http:// ou https://.", "error")
            return render_template("newvideo.html", tipo=tipo)

        imagem = request.files.get("imagem")
        imagem_valor = None

        if imagem and imagem.filename and allowed_file(imagem.filename):
            imagem_valor = salvar_imagem(imagem)

        novo_video = Video(
            usuario_id=session["usuario_id"],
            tipo=tipo,
            titulo=titulo,
            autor=autor,
            genero=genero,
            link=link,
            imagem=imagem_valor
        )

        db.session.add(novo_video)
        db.session.commit()

        video_data = {
            "titulo": novo_video.titulo,
            "autor": novo_video.autor,
            "genero": novo_video.genero,
            "link": novo_video.link,
            "imagem": novo_video.imagem
        }

        if tipo == "video":
            analise_result = analisar_video(video_data)
            novo_video.analise = str(analise_result.get("analise", ""))
        else:
            novo_video.analise = (
                f"Livro cadastrado por {novo_video.autor}. "
                f"Gênero: {novo_video.genero or 'não informado'}. "
                "Use o link para acessar a obra."
            )
        db.session.commit()

        return redirect(url_for("exibir_analise", video_id=novo_video.id))

    return render_template("newvideo.html", tipo=tipo)


@app.route("/estatisticas")
@login_required
def estatisticas():
    tipo = catalog_type()
    videos = owned_items_query(tipo).options(selectinload(Video.avaliacoes)).all()
    total_votos = sum(video.total_avaliacoes for video in videos)
    total_notas = sum(avaliacao.nota for video in videos for avaliacao in video.avaliacoes)
    generos = {}

    for video in videos:
        genero = video.genero or "Sem gênero"
        dados = generos.setdefault(genero, {"videos": 0, "votos": 0, "soma_notas": 0, "filmes": []})
        dados["videos"] += 1
        dados["votos"] += video.total_avaliacoes
        dados["soma_notas"] += sum(avaliacao.nota for avaliacao in video.avaliacoes)
        dados["filmes"].append(video)

    generos = sorted(
        generos.items(),
        key=lambda item: item[1]["soma_notas"] / item[1]["votos"] if item[1]["votos"] else 0,
        reverse=True
    )
    for _, dados in generos:
        dados["media"] = dados["soma_notas"] / dados["votos"] if dados["votos"] else 0
        dados["volume"] = (dados["votos"] / total_votos * 100) if total_votos else 0

    return render_template(
        "estatistica.html",
        tipo=tipo,
        total_videos=len(videos),
        total_votos=total_votos,
        media_global=total_notas / total_votos if total_votos else 0,
        generos=generos
    )


@app.route("/avaliar/<int:video_id>", methods=["POST"])
@login_required
def avaliar_video(video_id):
    video = get_owned_video_or_404(video_id)
    tipo = catalog_type(request.form.get("tipo", video.tipo))
    if video.tipo != tipo:
        abort(404)
    try:
        nota = int(request.form.get("nota", "-1"))
    except ValueError:
        nota = -1

    if 0 <= nota <= 5:
        votante_id = str(session["usuario_id"])

        avaliacao = Avaliacao.query.filter_by(video_id=video.id, votante_id=votante_id).first()
        if avaliacao:
            avaliacao.nota = nota
        else:
            db.session.add(Avaliacao(video=video, nota=nota, votante_id=votante_id))
        db.session.commit()

    return redirect(request.referrer or url_for("homepage", tipo=tipo))


@app.route("/search")
@login_required
def search():
    q = request.args.get("q", "").strip()
    tipo = catalog_type()
    if not q:
        return redirect(url_for("homepage", tipo=tipo))

    results = owned_items_query(tipo).filter(
        or_(
            Video.titulo.ilike(f"%{q}%"),
            Video.autor.ilike(f"%{q}%")
        )
    ).all()

    return render_template("resultados.html", query=q, results=results, tipo=tipo)


@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    usuario = db.session.get(Usuario, session.get("usuario_id"))
    if usuario is None:
        session.clear()
        return redirect(url_for("login", next=request.path))

    if request.method == "POST":
        if request.form.get("acao") == "remover_foto":
            if not usuario.foto_perfil:
                flash("Você não possui uma foto de perfil para remover.", "error")
            else:
                remover_imagem(usuario.foto_perfil)
                usuario.foto_perfil = None
                db.session.commit()
                flash("Foto de perfil removida com sucesso.", "success")
            return redirect(url_for("perfil"))

        foto = request.files.get("foto_perfil")
        if foto and foto.filename and allowed_file(foto.filename):
            nova_foto = salvar_imagem(foto, prefixo=f"perfil_{usuario.id}")
            if nova_foto:
                remover_imagem(usuario.foto_perfil)
                usuario.foto_perfil = nova_foto
                db.session.commit()
                flash("Foto de perfil atualizada com sucesso.", "success")
            else:
                flash("Não foi possível salvar a imagem. Tente novamente.", "error")
        else:
            flash("Formato de imagem inválido. Use PNG, JPG, JPEG ou WEBP.", "error")
        return redirect(url_for("perfil"))

    videos = owned_items_query("video").order_by(Video.id.desc()).all()
    livros = owned_items_query("livro").order_by(Video.id.desc()).all()
    top_videos = sorted(
        videos,
        key=lambda video: (video.media_avaliacao or 0, video.total_avaliacoes, video.id),
        reverse=True,
    )[:10]
    top_livros = sorted(
        livros,
        key=lambda livro: (livro.media_avaliacao or 0, livro.total_avaliacoes, livro.id),
        reverse=True,
    )[:10]

    profile_data = {
        "nome": usuario.nome,
        "total_filmes": len(videos),
        "total_livros": len(livros),
        "top_10": [
            {
                "titulo": video.titulo or "Sem título",
                "genero": video.genero or "Sem gênero",
                "nota_media": round(video.media_avaliacao or 0, 2),
                "link": video.link or None,
            }
            for video in top_videos
        ],
        "top_10_livros": [
            {
                "titulo": livro.titulo or "Sem título",
                "genero": livro.genero or "Sem gênero",
                "nota_media": round(livro.media_avaliacao or 0, 2),
                "link": livro.link or None,
            }
            for livro in top_livros
        ],
    }

    return render_template(
        "perfil.html",
        usuario=usuario,
        total_videos=len(videos),
        total_livros=len(livros),
        top_videos=top_videos,
        top_livros=top_livros,
        profile_data=profile_data,
    )


@app.route("/parceiros")
@login_required
def parceiros():
    lista_parceiros = Parceiro.query.order_by(Parceiro.nome.asc()).all()
    return render_template("parceiros.html", parceiros=lista_parceiros)


@app.route("/editar/<int:video_id>", methods=["GET", "POST"])
@login_required
def editar_video(video_id):
    video = get_owned_video_or_404(video_id)
    tipo = catalog_type(request.form.get("tipo", video.tipo) if request.method == "POST" else video.tipo)
    if video.tipo != tipo:
        abort(404)

    if request.method == "POST":
        imagem = request.files.get("imagem")
        if imagem and imagem.filename and allowed_file(imagem.filename):
            nova_imagem = salvar_imagem(imagem)
            if nova_imagem:
                remover_imagem(video.imagem)
                video.imagem = nova_imagem

        video.titulo = request.form.get("titulo")
        video.autor = request.form.get("autor")
        video.genero = request.form.get("genero")
        video.link = request.form.get("link")
        if tipo == "livro":
            video.analise = (
                f"Livro cadastrado por {video.autor}. "
                f"Gênero: {video.genero or 'não informado'}. "
                "Use o link para acessar a obra."
            )

        db.session.commit()
        return redirect(url_for("homepage", tipo=tipo))

    return render_template("editar_video.html", video=video, tipo=tipo)


@app.route("/deletar/<int:video_id>", methods=["POST"])
@login_required
def deletar_video(video_id):
    video = get_owned_video_or_404(video_id)
    tipo = catalog_type(request.form.get("tipo", video.tipo))
    if video.tipo != tipo:
        abort(404)

    remover_imagem(video.imagem)

    db.session.delete(video)
    db.session.commit()
    return redirect(url_for("homepage", tipo=tipo))


@app.route("/analise/<int:video_id>")
@login_required
def exibir_analise(video_id):
    video = get_owned_video_or_404(video_id)
    videos_similares = []
    tipo = catalog_type(request.args.get("tipo", video.tipo))
    if video.tipo != tipo:
        abort(404)

    if video.genero:
        videos_similares = (
            owned_items_query(tipo)
            .filter(Video.genero == video.genero, Video.id != video.id)
            .order_by(Video.id.desc())
            .limit(4)
            .all()
        )

    return render_template("analise.html", video=video, videos_similares=videos_similares, tipo=tipo)


if __name__ == "__main__":
    app.run(debug=True)