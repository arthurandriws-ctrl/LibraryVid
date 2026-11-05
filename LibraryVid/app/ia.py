import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib import request
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")


def _get_api_key():
    return os.getenv("GEMINIAPIKEY") or os.getenv("GEMINI_API_KEY")


def _normalizar_analise(valor):
    if isinstance(valor, str):
        return valor.strip()
    if isinstance(valor, (dict, list, tuple)):
        return json.dumps(valor, ensure_ascii=False)
    return str(valor).strip() if valor is not None else "Análise indisponível."


def _extrair_video_id_youtube(link):
    if not link:
        return None

    try:
        parsed = urlparse(link)
    except Exception:
        return None

    host = parsed.netloc.lower()
    if "youtube.com" in host or "youtu.be" in host or "www.youtube.com" in host:
        if "youtu.be" in host:
            video_id = parsed.path.strip("/").split("/")[0]
            return video_id if re.fullmatch(r"[A-Za-z0-9_-]+", video_id) else None

        if parsed.query:
            query_params = parse_qs(parsed.query)
            if "v" in query_params and query_params["v"]:
                return query_params["v"][0]

        match = re.search(r"/(?:embed|shorts|live)/([^/?]+)", parsed.path)
        if match:
            return match.group(1)

    return None


def _extrair_legendas_youtube(link):
    video_id = _extrair_video_id_youtube(link)
    if not video_id:
        return ""

    try:
        page_url = f"https://www.youtube.com/watch?v={video_id}"
        page_request = request.Request(
            page_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            },
        )
        with request.urlopen(page_request, timeout=30) as resposta:
            pagina_html = resposta.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""

    padrao = r"ytInitialPlayerResponse\s*=\s*(\{.*?\})\s*;\s*(?:var|\n|</script>)"
    match = re.search(padrao, pagina_html, re.DOTALL)
    if not match:
        return ""

    try:
        player_data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return ""

    tracks = player_data.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
    if not tracks:
        return ""

    preferred_track = None
    for track in tracks:
        language = str(track.get("languageCode", "")).lower()
        name = str(track.get("name", {}).get("simpleText", "")).lower()
        if "pt" in language or "pt" in name:
            preferred_track = track
            break
    if preferred_track is None:
        preferred_track = tracks[0]

    caption_url = preferred_track.get("baseUrl")
    if not caption_url:
        return ""

    caption_request = request.Request(
        caption_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        },
    )

    try:
        with request.urlopen(caption_request, timeout=30) as resposta:
            xml_bytes = resposta.read()
    except Exception:
        return ""

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        try:
            root = ET.fromstring(xml_bytes.decode("utf-8", errors="ignore"))
        except ET.ParseError:
            return ""

    textos = []
    for node in root.iter("text"):
        valor = (node.text or "").strip()
        if valor:
            textos.append(valor)

    transcript = " ".join(textos)
    return re.sub(r"\s+", " ", transcript).strip()


def _montar_analise_youtube(video_data, transcript):
    dados = dict(video_data or {})
    dados["transcricao_legendas"] = transcript[:15000]
    return dados


def _finalizar_resposta_analise(d, is_youtube=False):
    if not isinstance(d, dict):
        return {
            "perfil": "Indefinido",
            "analise": "Análise indisponível."
        }

    if is_youtube:
        resumo = d.get("resumo") or d.get("analise") or d.get("tema") or "Resumo do vídeo não disponível."
        perfil = str(d.get("perfil") or d.get("tema") or "Indefinido")
        return {
            "perfil": perfil,
            "analise": str(resumo).strip(),
        }

    analise = d.get("analise")
    if isinstance(analise, str) and analise.strip():
        perfil = str(d.get("perfil") or d.get("tema") or "Indefinido")
        return {
            "perfil": perfil,
            "analise": analise.strip(),
        }

    tema = str(d.get("tema") or d.get("perfil") or "Indefinido")
    pontos = d.get("pontos_importantes") or d.get("pontos") or []
    sobre = d.get("sobre") or d.get("quem_se_trata") or "O conteúdo aborda o tema principal do vídeo."
    objetivo = d.get("objetivo") or "Comunicar a mensagem principal do vídeo de forma clara e útil para o público."
    indicacoes = d.get("indicacoes") or d.get("conteudos_semelhantes") or []

    linhas = [
        f"Tema: {tema}",
        f"Pontos importantes: { '; '.join(map(str, pontos)) if isinstance(pontos, (list, tuple)) and pontos else 'O vídeo estrutura a mensagem em ideias-chave e exemplos práticos.' }",
        f"Sobre: {sobre}",
        f"Objetivo: {objetivo}",
        f"Conteúdos semelhantes: { '; '.join(map(str, indicacoes)) if isinstance(indicacoes, (list, tuple)) and indicacoes else 'Sugestões de vídeos com abordagem temática parecida.' }",
    ]

    return {
        "perfil": tema,
        "analise": "\n".join(linhas),
    }


def analisar_video(video_data):
    api_key = _get_api_key()
    if not api_key:
        return {
            "perfil": "Indefinido",
            "analise": (
                "Análise automática indisponível. "
                "Configure a variável GEMINIAPIKEY (ou GEMINI_API_KEY) "
                "para habilitar a análise de filmes."
            )
        }

    modelo = "gemini-2.5-flash"
    link = (video_data or {}).get("link", "") if isinstance(video_data, dict) else ""
    prompt_data = dict(video_data or {}) if isinstance(video_data, dict) else {}
    is_youtube = bool(_extrair_video_id_youtube(link))

    if is_youtube:
        transcript = _extrair_legendas_youtube(link)
        if transcript:
            prompt_data = _montar_analise_youtube(prompt_data, transcript)

    if is_youtube:
        prompt = f"""
        Você é um analista de conteúdo de vídeos do YouTube.
        Analise a transcrição e responda em JSON puro, com exatamente este formato:
        {{
          "tema": "tema principal do vídeo",
          "resumo": "resumo breve em 2 ou 3 frases do conteúdo do vídeo",
          "perfil": "descrição curta do público ou do vibe do vídeo"
        }}

        Regras:
        - Escreva em português.
        - Use a transcrição como base principal da análise.
        - O conteúdo deve ser um resumo breve, sem listas, sem pontos importantes e sem recomendações.
        - Não use markdown.

        Dados fornecidos do vídeo:
        {prompt_data}
        """
    else:
        prompt = f"""
        Você é um analista de conteúdo e vídeos.
        Analise o material informado e responda em JSON puro, com exatamente este formato:
        {{
          "tema": "tema principal do vídeo",
          "pontos_importantes": ["ponto 1", "ponto 2", "ponto 3"],
          "sobre": "quem ou qual público o vídeo se trata e o contexto geral",
          "objetivo": "objetivo principal do conteúdo",
          "indicacoes": ["sugestão 1", "sugestão 2", "sugestão 3"],
          "perfil": "descrição curta do público ou do vibe do vídeo"
        }}

        Regras:
        - Escreva em português.
        - Se houver transcrição de legendas, use-a como base principal para a análise.
        - Não use markdown.
        - Foque em tema, pontos importantes, público/quem se trata, objetivo e indicações de conteúdo semelhante.

        Dados fornecidos do vídeo:
        {prompt_data}
        """

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }).encode("utf-8")

    try:
        api_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{modelo}:generateContent?key={api_key}"
        )
        requisicao = request.Request(
            api_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(requisicao, timeout=60) as resposta:
            resposta_json = json.load(resposta)
        texto = resposta_json["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return {
            "perfil": "Indefinido",
            "analise": "Análise automática indisponível no momento. A API do Gemini retornou erro temporário; tente novamente mais tarde."
        }

    texto_puro = texto.replace("```json", "").replace("```", "").strip()

    try:
        d = json.loads(texto_puro)
        resultado = _finalizar_resposta_analise(d, is_youtube=is_youtube)
        return {
            "perfil": resultado["perfil"],
            "analise": _normalizar_analise(resultado["analise"])
        }
    except json.JSONDecodeError:
        return {
            "perfil": "Indefinido",
            "analise": _normalizar_analise(texto_puro)
        }