import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from LibraryVid.app import ia
from LibraryVid.app.app import app, db
from LibraryVid.app.models import Usuario, Video


def create_user():
    usuario = Usuario(nome="Usuário", email="usuario@example.com", senha_hash="hash")
    db.session.add(usuario)
    db.session.flush()
    return usuario.id


def login_as(client, usuario_id):
    with client.session_transaction() as session_data:
        session_data["usuario_id"] = usuario_id


def test_homepage_renders_fab_action_menu():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario_id = create_user()

        with app.test_client() as client:
            login_as(client, usuario_id)
            response = client.get("/")

            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert "Adicionar vídeos" in html
            assert "Ver parceiros" in html
            assert "fab-toggle" in html


def test_analise_page_lists_similar_videos():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario_id = create_user()

        video_principal = Video(
            usuario_id=usuario_id,
            titulo="Filme Principal",
            autor="Diretor A",
            genero="Drama",
            link="https://example.com/a",
            analise="Análise principal"
        )
        video_similar = Video(
            usuario_id=usuario_id,
            titulo="Filme Similar",
            autor="Diretor B",
            genero="Drama",
            link="https://example.com/b",
            analise="Análise similar"
        )
        video_diferente = Video(
            usuario_id=usuario_id,
            titulo="Filme Diferente",
            autor="Diretor C",
            genero="Ação",
            link="https://example.com/c",
            analise="Análise diferente"
        )

        db.session.add_all([video_principal, video_similar, video_diferente])
        db.session.commit()

        with app.test_client() as client:
            login_as(client, usuario_id)
            response = client.get(f"/analise/{video_principal.id}")

            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert "Vídeos Similares" in html
            assert "Filme Similar" in html
            assert "Filme Diferente" not in html


def test_homepage_filters_videos_by_genre():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario_id = create_user()

        drama = Video(
            usuario_id=usuario_id,
            titulo="Filme Drama",
            autor="Diretor Drama",
            genero="Drama",
            link="https://example.com/drama",
            analise="Análise drama"
        )
        acao = Video(
            usuario_id=usuario_id,
            titulo="Filme Ação",
            autor="Diretor Ação",
            genero="Ação",
            link="https://example.com/acao",
            analise="Análise ação"
        )

        db.session.add_all([drama, acao])
        db.session.commit()

        with app.test_client() as client:
            login_as(client, usuario_id)
            response = client.get("/?genero=Drama")

            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert "Filme Drama" in html
            assert "Filme Ação" not in html


def test_analisar_video_usa_transcricao_do_youtube(monkeypatch):
    monkeypatch.setenv("GEMINIAPIKEY", "test-key")

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps({
                "candidates": [{
                    "content": {"parts": [{"text": '{"perfil": "Público curioso", "analise": "Resumo do vídeo."}' }]}
                }]
            }).encode("utf-8")

    def fake_urlopen(request_obj, **_):
        captured["payload"] = json.loads(request_obj.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(ia.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        ia,
        "_extrair_legendas_youtube",
        lambda _: "Este vídeo mostra como a sustentabilidade pode reduzir custos em empresas. Ele fala sobre energia limpa, planejamento e métricas de impacto ambiental.",
    )

    resultado = ia.analisar_video({
        "titulo": "Sustentabilidade para negócios",
        "autor": "Canal Exemplo",
        "genero": "Documentário",
        "link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    })

    assert resultado["perfil"] == "Público curioso"
    assert "Resumo do vídeo." in resultado["analise"]
    assert "Pontos importantes" not in resultado["analise"]
    assert "Conteúdos semelhantes" not in resultado["analise"]
    assert "pontos_importantes" not in captured["payload"]["contents"][0]["parts"][0]["text"].lower()
    assert "indicacoes" not in captured["payload"]["contents"][0]["parts"][0]["text"].lower()
    assert "youtube" in captured["payload"]["contents"][0]["parts"][0]["text"].lower()
    assert "sustentabilidade" in captured["payload"]["contents"][0]["parts"][0]["text"].lower()


def test_parceiros_page_does_not_include_old_names_and_has_empty_state():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario_id = create_user()

        with app.test_client() as client:
            login_as(client, usuario_id)
            response = client.get("/parceiros")

            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert "CineLab Studio" not in html
            assert "Framehouse" not in html
            assert "Nova Cena" not in html
            assert "Nenhum parceiro cadastrado" in html
