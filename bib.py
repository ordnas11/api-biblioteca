from datetime import date
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import mysql.connector

app = FastAPI(title="API Biblioteca")

def get_conn():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="SUA_SENHA",
        database="biblioteca",
    )

class Aluno(BaseModel):
    cpf_aluno: str
    nome_aluno: str
    ra_aluno: str
    data_nascimento: date

def calcular_idade(nasc: date) -> int:
    hoje = date.today()
    return hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))

@app.post("/alunos", status_code=201)
def criar_aluno(aluno: Aluno):
    if calcular_idade(aluno.data_nascimento) <= 15:
        raise HTTPException(400, "Aluno precisa ter 16 anos ou mais.")

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO aluno (CPF_ALUNO, NOME_ALUNO, RA_ALUNO, DATA_NASCIMENTO) "
            "VALUES (%s, %s, %s, %s)",
            (aluno.cpf_aluno, aluno.nome_aluno, aluno.ra_aluno, aluno.data_nascimento),
        )
        conn.commit()
    except mysql.connector.IntegrityError:
        raise HTTPException(409, "CPF ou RA já cadastrado.")
    finally:
        conn.close()
    return {"mensagem": "Aluno cadastrado"}

@app.get("/alunos")
def listar_alunos():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM aluno")
    dados = cur.fetchall()
    conn.close()
    return dados

@app.delete("/alunos/{cpf}")
def excluir_aluno(cpf: str):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM aluno WHERE CPF_ALUNO = %s", (cpf,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Aluno não encontrado.")
    except mysql.connector.IntegrityError:
        raise HTTPException(409, "Aluno possui empréstimos e não pode ser excluído.")
    finally:
        conn.close()
    return {"mensagem": "Aluno excluído"}