# LibraryVid

Aplicação Flask para organizar, avaliar e analisar uma biblioteca pessoal de
vídeos e livros.

## Executar localmente

Requer Python e `pip`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m flask --app LibraryVid.app.app run
```

Edite `.env` e defina uma `SECRET_KEY` aleatória. A aplicação usa um banco
SQLite em `instance/` por padrão. Para análise de vídeos, configure
`GEMINI_API_KEY`. Para e-mails de recuperação de senha, configure
`BREVO_API_KEY` e `MAIL_DEFAULT_SENDER`.

## Deploy

Configure as variáveis de ambiente no provedor de hospedagem, sem adicioná-las
ao Git. Use uma `SECRET_KEY` forte, um banco PostgreSQL gerenciado em
`DATABASE_URL` e as chaves de API necessárias. O `Procfile` inicia a aplicação
com Gunicorn. Configure Cloudinary se os uploads precisarem persistir entre
deploys.

## Testes

```powershell
python -m pytest -q
```
