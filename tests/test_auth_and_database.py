import io
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from LibraryVid.app.app import app, db, enviar_email, gerar_token_reset
from LibraryVid.app.db import get_database_uri
from LibraryVid.app.models import Avaliacao, Parceiro, Usuario, Video
from werkzeug.security import check_password_hash


@pytest.fixture(autouse=True)
def clean_database():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield
        db.session.remove()


def test_cadastro_armazena_apenas_hash_e_encaminha_para_login():
    with app.test_client() as client:
        response = client.post(
            "/cadastro",
            data={"nome": "Ana", "email": "ANA@example.com", "senha": "senha-segura"},
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")
        login_page = client.get("/login")
        login_html = login_page.get_data(as_text=True)
        assert "border-emerald-300 bg-emerald-100 text-emerald-800" in login_html
        assert "Cadastro concluído" in login_html

        duplicate_response = client.post(
            "/cadastro",
            data={"nome": "Ana", "email": "ana@example.com", "senha": "senha-segura"},
        )
        duplicate_html = duplicate_response.get_data(as_text=True)
        assert "border-red-300 bg-red-100 text-red-800" in duplicate_html
        assert "Este e-mail já está cadastrado." in duplicate_html

        with app.app_context():
            usuario = Usuario.query.one()
            assert usuario.email == "ana@example.com"
            assert usuario.senha_hash != "senha-segura"
            assert usuario.senha_hash.startswith("scrypt:")

        with client.session_transaction() as session_data:
            assert "usuario_id" not in session_data

        login_response = client.post(
            "/login",
            data={"email": "ana@example.com", "senha": "senha-segura"},
        )
        assert login_response.headers["Location"].endswith("/")


def test_operacao_protegida_redireciona_usuario_anonimo():
    with app.test_client() as client:
        homepage = client.get("/")
        response = client.get("/newvideo")

        assert homepage.status_code == 302
        assert "/login" in homepage.headers["Location"]
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_envio_de_recuperacao_falha_sem_configuracao_brevo(monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("MAIL_DEFAULT_SENDER", raising=False)

    with app.app_context():
        usuario = Usuario(nome="Diana", email="diana@example.com", senha_hash="hash", senha_original="senha-segura")
        db.session.add(usuario)
        db.session.commit()

        assert enviar_email(
            usuario.email,
            usuario.nome,
            "Redefinição de senha",
            "Link de redefinição",
        ) is False


def test_telas_de_autenticacao_e_resposta_generica_para_email_desconhecido():
    with app.test_client() as client:
        for path in ("/login", "/cadastro", "/esqueci-senha"):
            assert client.get(path).status_code == 200

        response = client.post(
            "/esqueci-senha",
            data={"email": "naoexiste@example.com"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert "Se o e-mail estiver cadastrado" in response.get_data(as_text=True)


def test_biblioteca_e_estatisticas_sao_isoladas_por_usuario():
    with app.app_context():
        ana = Usuario(nome="Ana", email="ana@example.com", senha_hash="hash")
        bruno = Usuario(nome="Bruno", email="bruno@example.com", senha_hash="hash")
        db.session.add_all([ana, bruno])
        db.session.flush()
        video_ana = Video(usuario_id=ana.id, titulo="Vídeo da Ana", genero="Drama")
        video_bruno = Video(usuario_id=bruno.id, titulo="Vídeo do Bruno", genero="Ação")
        db.session.add_all([video_ana, video_bruno])
        db.session.commit()
        ana_id = ana.id
        video_ana_id = video_ana.id
        video_bruno_id = video_bruno.id
        bruno_id = bruno.id

    with app.test_client() as client:
        with client.session_transaction() as session_data:
            session_data["usuario_id"] = ana_id

        homepage = client.get("/")
        stats = client.get("/estatisticas")
        other_video = client.get(f"/analise/{video_bruno_id}")

        assert "Vídeo da Ana" in homepage.get_data(as_text=True)
        assert "Vídeo do Bruno" not in homepage.get_data(as_text=True)
        assert "Vídeo da Ana" in stats.get_data(as_text=True)
        assert "Vídeo do Bruno" not in stats.get_data(as_text=True)
        assert other_video.status_code == 404

        with client.session_transaction() as session_data:
            session_data["usuario_id"] = bruno_id
        assert client.get(f"/editar/{video_ana_id}").status_code == 404


def test_estatisticas_exibe_avaliacao_individual_de_cada_filme():
    with app.app_context():
        usuario = Usuario(nome="Ana", email="ana@example.com", senha_hash="hash")
        db.session.add(usuario)
        db.session.flush()
        filme_avaliado = Video(usuario_id=usuario.id, titulo="Filme avaliado", genero="Drama")
        filme_sem_avaliacao = Video(usuario_id=usuario.id, titulo="Filme sem nota", genero="Drama")
        db.session.add_all([filme_avaliado, filme_sem_avaliacao])
        db.session.flush()
        db.session.add_all([
            Avaliacao(video_id=filme_avaliado.id, votante_id="user-1", nota=5),
            Avaliacao(video_id=filme_avaliado.id, votante_id="user-2", nota=3),
        ])
        usuario_id = usuario.id
        db.session.commit()

    with app.test_client() as client:
        with client.session_transaction() as session_data:
            session_data["usuario_id"] = usuario_id

        response = client.get("/estatisticas")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Filme avaliado" in html
        assert "Média 4.0 de 5, 2 votos" in html
        assert "Filme sem nota" in html
        assert "Sem avaliações" in html


def test_catalogos_de_livros_e_videos_sao_independentes():
    with app.app_context():
        usuario = Usuario(nome="Ana", email="ana@example.com", senha_hash="hash")
        db.session.add(usuario)
        db.session.flush()
        video = Video(
            usuario_id=usuario.id,
            tipo="video",
            titulo="Documentário de ciência",
            autor="Canal Ciência",
            genero="Drama",
            link="https://example.com/video",
            analise="Resumo do documentário",
        )
        video_similar = Video(
            usuario_id=usuario.id,
            tipo="video",
            titulo="Outro documentário",
            autor="Canal 2",
            genero="Drama",
            link="https://example.com/video-2",
        )
        livro = Video(
            usuario_id=usuario.id,
            tipo="livro",
            titulo="Livro de ciência",
            autor="Autora",
            genero="Drama",
            link="https://example.com/livro",
            analise="Resumo do livro",
        )
        livro_similar = Video(
            usuario_id=usuario.id,
            tipo="livro",
            titulo="Outro livro de ciência",
            autor="Outro autor",
            genero="Drama",
            link="https://example.com/livro-2",
        )
        db.session.add_all([video, video_similar, livro, livro_similar])
        db.session.commit()
        usuario_id = usuario.id
        video_id = video.id
        livro_id = livro.id

    with app.test_client() as client:
        with client.session_transaction() as session_data:
            session_data["usuario_id"] = usuario_id

        videos_page = client.get("/")
        books_page = client.get("/?tipo=livro")
        videos_stats = client.get("/estatisticas")
        books_stats = client.get("/estatisticas?tipo=livro")
        book_search = client.get("/search?q=livro&tipo=livro")
        video_analysis = client.get(f"/analise/{video_id}")
        book_analysis = client.get(f"/analise/{livro_id}")
        book_edit_page = client.get(f"/editar/{livro_id}")

        assert "Documentário de ciência" in videos_page.get_data(as_text=True)
        assert "Livro de ciência" not in videos_page.get_data(as_text=True)
        assert "Livro de ciência" in books_page.get_data(as_text=True)
        assert "Documentário de ciência" not in books_page.get_data(as_text=True)
        assert "Total de Vídeos" in videos_stats.get_data(as_text=True)
        assert "Total de Livros" in books_stats.get_data(as_text=True)
        assert "Livro de ciência" in book_search.get_data(as_text=True)
        assert "Documentário de ciência" not in book_search.get_data(as_text=True)
        assert "Outro documentário" in video_analysis.get_data(as_text=True)
        assert "Livro de ciência" not in video_analysis.get_data(as_text=True)
        assert "Livros Similares" in book_analysis.get_data(as_text=True)
        assert "Outro livro de ciência" in book_analysis.get_data(as_text=True)
        assert "Outro documentário" not in book_analysis.get_data(as_text=True)
        assert book_edit_page.status_code == 200
        assert "Editar livro" in book_edit_page.get_data(as_text=True)

        book_edit = client.post(
            f"/editar/{livro_id}",
            data={
                "tipo": "livro",
                "titulo": "Livro de ciência atualizado",
                "autor": "Autora",
                "genero": "Drama",
                "link": "https://example.com/livro-atualizado",
            },
        )
        assert book_edit.status_code == 302
        assert book_edit.headers["Location"].endswith("/?tipo=livro")

        book_rating = client.post(
            f"/avaliar/{livro_id}",
            data={"tipo": "livro", "nota": "5"},
        )
        wrong_catalog_rating = client.post(
            f"/avaliar/{livro_id}",
            data={"tipo": "video", "nota": "1"},
        )
        rated_book_stats = client.get("/estatisticas?tipo=livro").get_data(as_text=True)

        assert book_rating.status_code == 302
        assert wrong_catalog_rating.status_code == 404
        assert "Média 5.0 de 5, 1 voto" in rated_book_stats


def test_cadastro_de_livro_nao_chama_analise_de_video(monkeypatch):
    import LibraryVid.app.app as app_module

    def fail_if_called(_):
        raise AssertionError("A análise de vídeo não deve ser chamada para livros.")

    monkeypatch.setattr(app_module, "analisar_video", fail_if_called)
    with app.app_context():
        usuario = Usuario(nome="Ana", email="ana@example.com", senha_hash="hash")
        db.session.add(usuario)
        db.session.commit()
        usuario_id = usuario.id

    with app.test_client() as client:
        with client.session_transaction() as session_data:
            session_data["usuario_id"] = usuario_id

        response = client.post(
            "/newvideo",
            data={
                "tipo": "livro",
                "titulo": "Livro de teste",
                "autor": "Autora de teste",
                "genero": "Ficção",
                "link": "https://example.com/livro",
            },
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/analise/1")
        with app.app_context():
            livro = Video.query.filter_by(tipo="livro").one()
            assert livro.titulo == "Livro de teste"
            assert "Autora de teste" in livro.analise


def test_perfil_exibe_rankings_separados_e_expansiveis():
    with app.app_context():
        usuario = Usuario(nome="Ana", email="ana@example.com", senha_hash="hash")
        db.session.add(usuario)
        db.session.flush()
        videos = [
            Video(usuario_id=usuario.id, tipo="video", titulo=f"Vídeo {indice}")
            for indice in range(1, 5)
        ]
        livros = [
            Video(usuario_id=usuario.id, tipo="livro", titulo=f"Livro {indice}")
            for indice in range(1, 6)
        ]
        db.session.add_all(videos + livros)
        db.session.commit()
        usuario_id = usuario.id

    with app.test_client() as client:
        with client.session_transaction() as session_data:
            session_data["usuario_id"] = usuario_id

        response = client.get("/perfil")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Top vídeos" in html
        assert "Top livros" in html
        assert "Vídeos salvos" in html
        assert "Livros salvos" in html
        assert html.count('data-ranking-item="video"') == 4
        assert html.count('data-ranking-item="livro"') == 5
        assert html.count('data-ranking-toggle="video"') == 1
        assert html.count('data-ranking-toggle="livro"') == 1


def test_novo_video_persiste_a_analise_gerada(monkeypatch):
    monkeypatch.setattr(
        "LibraryVid.app.app.analisar_video",
        lambda _: {
            "perfil": "Drama contemplativo",
            "analise": "Uma análise gerada para o vídeo.",
        },
    )

    with app.test_client() as client:
        client.post(
            "/cadastro",
            data={"nome": "Clara", "email": "clara@example.com", "senha": "senha-segura"},
        )
        client.post(
            "/login",
            data={"email": "clara@example.com", "senha": "senha-segura"},
        )
        response = client.post(
            "/newvideo",
            data={
                "titulo": "Vídeo privado",
                "autor": "Clara",
                "genero": "Drama",
                "link": "https://example.com/video",
            },
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/analise/1")
        with app.app_context():
            video = Video.query.one()
            assert video.usuario.email == "clara@example.com"
            assert video.analise == "Uma análise gerada para o vídeo."


def test_parceiro_e_adicionado_pelo_backend_e_exibido_com_links():
    resultado = app.test_cli_runner().invoke(
        args=[
            "parceiro-add",
            "--nome", "Estúdio Horizonte",
            "--tipo", "Produção",
            "--site", "https://horizonte.example",
            "--contato", "mailto:contato@horizonte.example",
        ]
    )

    assert resultado.exit_code == 0
    with app.app_context():
        parceiro = Parceiro.query.one()
        parceiro_id = parceiro.id

    with app.test_client() as client:
        client.post(
            "/cadastro",
            data={"nome": "Diego", "email": "diego@example.com", "senha": "senha-segura"},
        )
        client.post(
            "/login",
            data={"email": "diego@example.com", "senha": "senha-segura"},
        )
        response = client.get("/parceiros")
        html = response.get_data(as_text=True)

        assert parceiro_id
        assert response.status_code == 200
        assert "Estúdio Horizonte" in html
        assert 'href="https://horizonte.example"' in html
        assert 'href="mailto:contato@horizonte.example"' in html
        assert "Adicionar parceiro" not in html


def test_tela_de_perfil_exibe_nome_top10_e_nao_expoe_dados_sensiveis():
    with app.app_context():
        usuario = Usuario(nome="Renata", email="renata@example.com", senha_hash="hash")
        db.session.add(usuario)
        db.session.commit()
        usuario_id = usuario.id
        for i in range(12):
            db.session.add(
                Video(
                    usuario_id=usuario_id,
                    titulo=f"Filme {i}",
                    genero="Drama",
                    analise=f"Analise {i}",
                )
            )
        db.session.commit()

    with app.test_client() as client:
        with client.session_transaction() as session_data:
            session_data["usuario_id"] = usuario_id

        profile_response = client.get("/perfil")
        assert profile_response.status_code == 200
        html = profile_response.get_data(as_text=True)
        assert "Renata" in html
        assert "12" in html
        assert "Filme 11" in html
        assert "renata@example.com" not in html
        assert "hash" not in html

        profile_upload = client.post(
            "/perfil",
            data={"foto_perfil": (io.BytesIO(b"fake-image-content"), "avatar.png")},
            content_type="multipart/form-data",
        )
        assert profile_upload.status_code == 302
        with app.app_context():
            updated_user = db.session.get(Usuario, usuario_id)
            assert updated_user.foto_perfil is not None
            assert updated_user.email == "renata@example.com"


def test_tela_de_perfil_exporta_pdf_em_vez_de_json():
    with app.app_context():
        usuario = Usuario(nome="Renata", email="renata@example.com", senha_hash="hash")
        db.session.add(usuario)
        db.session.commit()
        usuario_id = usuario.id
        db.session.add(
            Video(
                usuario_id=usuario_id,
                titulo="Filme com link",
                link="https://example.com/filmes/1",
            )
        )
        db.session.commit()

    with app.test_client() as client:
        with client.session_transaction() as session_data:
            session_data["usuario_id"] = usuario_id

        response = client.get("/perfil")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "jspdf" in html
        assert "libraryvid-perfil.pdf" in html
        assert "https://example.com/filmes/1" in html
        assert "doc.link(" in html
        assert "application/json" not in html


def test_navegacao_alinha_sair_antes_do_card_em_todas_as_telas():
    with app.app_context():
        usuario = Usuario(nome="Renata", email="renata@example.com", senha_hash="hash")
        db.session.add(usuario)
        db.session.flush()
        video = Video(usuario_id=usuario.id, titulo="Filme de teste", link="https://example.com")
        db.session.add(video)
        db.session.commit()
        usuario_id = usuario.id
        video_id = video.id

    paths = [
        "/",
        "/estatisticas",
        "/perfil",
        "/search?q=Filme",
        "/newvideo",
        f"/editar/{video_id}",
        "/parceiros",
    ]

    with app.test_client() as client:
        with client.session_transaction() as session_data:
            session_data["usuario_id"] = usuario_id

        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, path
            html = response.get_data(as_text=True)
            nav_position = html.index('<nav class="flex shrink-0 bg-surface rounded-md border border-surfaceBorder p-1">')
            assert html.index("Sair") < nav_position, path
            assert html.index("Biblioteca", nav_position) >= nav_position, path
            nav_links = html[nav_position:html.index("</nav>", nav_position)]
            assert nav_links.count("nav-link") == 2, path


def test_tela_de_perfil_exibe_preview_e_controles_de_zoom_ao_selecionar_foto():
    with app.app_context():
        usuario = Usuario(nome="Renata", email="renata@example.com", senha_hash="hash")
        db.session.add(usuario)
        db.session.commit()
        usuario_id = usuario.id

    with app.test_client() as client:
        with client.session_transaction() as session_data:
            session_data["usuario_id"] = usuario_id

        response = client.get("/perfil")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "profile-photo-editor" in html
        assert "zoom" in html.lower()
        assert "crop" in html.lower()
        assert 'id="cancel-photo-selection"' in html


def test_tela_de_perfil_permite_remover_foto_atual():
    with app.app_context():
        usuario = Usuario(nome="Renata", email="renata@example.com", senha_hash="hash")
        db.session.add(usuario)
        db.session.commit()
        usuario_id = usuario.id

    with app.test_client() as client:
        with client.session_transaction() as session_data:
            session_data["usuario_id"] = usuario_id

        upload_response = client.post(
            "/perfil",
            data={"foto_perfil": (io.BytesIO(b"fake-image-content"), "avatar.png")},
            content_type="multipart/form-data",
        )
        assert upload_response.status_code == 302

        with app.app_context():
            usuario = db.session.get(Usuario, usuario_id)
            arquivo_foto = os.path.join(app.config["UPLOAD_FOLDER"], usuario.foto_perfil)
            assert os.path.exists(arquivo_foto)

        remove_response = client.post("/perfil", data={"acao": "remover_foto"})
        assert remove_response.status_code == 302
        with app.app_context():
            usuario = db.session.get(Usuario, usuario_id)
            assert usuario.foto_perfil is None
            assert not os.path.exists(arquivo_foto)


def test_tela_de_perfil_redireciona_quando_sessao_tem_usuario_invalido():
    with app.test_client() as client:
        with client.session_transaction() as session_data:
            session_data["usuario_id"] = 999999

        response = client.get("/perfil")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert "next=/perfil" in response.headers["Location"]


def test_fluxo_de_recuperacao_de_senha_usa_token_temporario():
    with app.app_context():
        usuario = Usuario(
            nome="Renata",
            email="renata@example.com",
            senha_hash="hash",
        )
        db.session.add(usuario)
        db.session.commit()
        token = gerar_token_reset(usuario)

    with app.test_client() as client:
        response = client.get(f"/redefinir-senha/{token}")
        assert response.status_code == 200
        assert "nova_senha" in response.get_data(as_text=True)

        recovery = client.post(
            f"/redefinir-senha/{token}",
            data={
                "nova_senha": "nova-senha-segura",
                "confirmar_senha": "nova-senha-segura",
            },
            follow_redirects=True,
        )
        assert recovery.status_code == 200
        with app.app_context():
            usuario = Usuario.query.filter_by(email="renata@example.com").one()
            assert check_password_hash(usuario.senha_hash, "nova-senha-segura")


def test_urls_de_banco_sao_normalizadas(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host/db")
    assert get_database_uri().startswith("postgresql+psycopg://")

    monkeypatch.setenv("DATABASE_URL", "mysql://user:pass@host/db")
    assert get_database_uri().startswith("mysql+pymysql://")
