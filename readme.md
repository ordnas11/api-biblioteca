# API Biblioteca
API em FastAPI + MySQL para empréstimo de livros.

## Como rodar
1. Rode o script SQL no MySQL.
2. `pip install -r requirements.txt`
3. Defina DB_USER e DB_PASSWORD
4. `uvicorn bib:app --reload`
5. Acesse http://127.0.0.1:8000/docs