import os 
import json 
from google import genai
from google.genai import types

def analisar_video(video_data):
    client = genai.Client(api_key=os.getenv("GEMINIAPIKEY"))
    modelo = "gemini-2.5-flash"
    
    prompt = f"""
    Você é um analista de filmes. O seu trabalho é analisar o filme informado
    e descrever brevemente sobre a história, evitando spoilers críticos, e com
    nas críticas disponíveis no MetaCritic, você vai classificar conforme a nota 
    do filme, os motivos para assistir o filme caso a nota for boa, e motivos para
    não assistir caso a nota for ruim.
    
    Dados fornecidos do filme
    {video_data}
        
    Escreva em português, de forma empática e acessível, e evite Markdown.
    """
    
    response = client.models.generate_content(
        model = modelo,
        contents = prompt,
        config = types.GenerateContentConfig(
            response_mime_type = "aplication/json"
        )
    )
    
    texto = response.text.strip()
    texto_puro = texto.replace("```json", "").replace("```", "").strip()
    
    try:
        d = json.loads(texto_puro)
        return {
            "perfil": d.get("perfil", "Indefinido"),
            "analise": d.get("analise", texto_puro)
        }
    except json.JSONDecodeError:
        return {
            "perfil": "Indefinido",
            "analise": texto_puro
        }