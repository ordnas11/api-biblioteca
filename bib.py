import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import mysql.connector
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="API Biblioteca")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # em projeto real, restrinja ao endereço do front
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------- regras
IDADE_MINIMA = 15      # prova: exclui quem tem MENOS de 15 anos
IDADE_BONUS = 25       # prova: bônus para MAIOR que 25 anos
PRAZO_PADRAO = 7       # dias (ajuste conforme o professor)
DIAS_BONUS = 10


# ---------------------------------------------------------------- banco
def get_conn():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "biblioteca"),
    )


@contextmanager
def db(dictionary=False):
    """Abre conexão, faz commit se der certo, rollback se der erro."""
    conn = get_conn()
    cur = conn.cursor(dictionary=dictionary)
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@app.exception_handler(mysql.connector.Error)
def erro_mysql(request, exc: mysql.connector.Error):
    mensagens = {
        1062: "Registro duplicado (CPF, RA, matrícula ou código já cadastrado).",
        1451: "Registro possui vínculos e não pode ser excluído.",
        1452: "Referência inválida: o registro relacionado não existe.",
        1644: exc.msg,  # mensagem do trigger (exemplar já emprestado)
    }
    return JSONResponse(
        status_code=409,
        content={"detail": mensagens.get(exc.errno, f"Erro no banco: {exc.msg}")},
    )


def calcular_idade(nasc: date) -> int:
    hoje = date.today()
    return hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))


# ---------------------------------------------------------------- modelos
class Aluno(BaseModel):
    cpf_aluno: str
    nome_aluno: str
    ra_aluno: str
    data_nascimento: date


class Atendente(BaseModel):
    cpf_atendente: str
    nome_atendente: str
    matricula: str
    telefone: str | None = None


class Livro(BaseModel):
    titulo_livro: str
    autor_livro: str
    editora: str | None = None
    ano_publicacao: int | None = None


class Exemplar(BaseModel):
    id_livro: int
    codigo_barras: str
    data_aquisicao: date | None = None


class Emprestimo(BaseModel):
    cpf_aluno: str
    id_exemplar: int
    cpf_atendente: str


# ---------------------------------------------------------------- front-end
BASE_DIR = Path(__file__).parent


@app.get("/", include_in_schema=False)
def raiz():
    """Entrega o index.html: API e front rodam juntos, no mesmo endereço."""
    return FileResponse(BASE_DIR / "index.html")


# ---------------------------------------------------------------- alunos
@app.post("/alunos", status_code=201)
def criar_aluno(aluno: Aluno):
    if calcular_idade(aluno.data_nascimento) < IDADE_MINIMA:
        raise HTTPException(400, f"Aluno precisa ter {IDADE_MINIMA} anos ou mais.")
    with db() as cur:
        cur.execute(
            "INSERT INTO aluno (CPF_ALUNO, NOME_ALUNO, RA_ALUNO, DATA_NASCIMENTO) "
            "VALUES (%s, %s, %s, %s)",
            (aluno.cpf_aluno, aluno.nome_aluno, aluno.ra_aluno, aluno.data_nascimento),
        )
    return {"mensagem": "Aluno cadastrado"}


@app.get("/alunos")
def listar_alunos():
    with db(dictionary=True) as cur:
        cur.execute("SELECT * FROM aluno")
        return cur.fetchall()


@app.delete("/alunos/{cpf}")
def excluir_aluno(cpf: str):
    with db() as cur:
        cur.execute("DELETE FROM aluno WHERE CPF_ALUNO = %s", (cpf,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Aluno não encontrado.")
    return {"mensagem": "Aluno excluído"}


# ---------------------------------------------------------------- atendentes
@app.post("/atendentes", status_code=201)
def criar_atendente(at: Atendente):
    with db() as cur:
        cur.execute(
            "INSERT INTO atendente (CPF_ATENDENTE, NOME_ATENDENTE, MATRICULA, TELEFONE) "
            "VALUES (%s, %s, %s, %s)",
            (at.cpf_atendente, at.nome_atendente, at.matricula, at.telefone),
        )
    return {"mensagem": "Atendente cadastrado"}


@app.get("/atendentes")
def listar_atendentes():
    with db(dictionary=True) as cur:
        cur.execute("SELECT * FROM atendente")
        return cur.fetchall()


# ---------------------------------------------------------------- livros
@app.post("/livros", status_code=201)
def criar_livro(livro: Livro):
    with db() as cur:
        cur.execute(
            "INSERT INTO livro (TITULO_LIVRO, AUTOR_LIVRO, EDITORA, ANO_PUBLICACAO) "
            "VALUES (%s, %s, %s, %s)",
            (livro.titulo_livro, livro.autor_livro, livro.editora, livro.ano_publicacao),
        )
        novo_id = cur.lastrowid
    return {"mensagem": "Livro cadastrado", "id_livro": novo_id}


@app.get("/livros")
def listar_livros():
    with db(dictionary=True) as cur:
        cur.execute("SELECT * FROM livro")
        return cur.fetchall()


# ---------------------------------------------------------------- exemplares
@app.post("/exemplares", status_code=201)
def criar_exemplar(ex: Exemplar):
    with db() as cur:
        cur.execute(
            "INSERT INTO exemplar (ID_LIVRO, CODIGO_BARRAS, DATA_AQUISICAO) "
            "VALUES (%s, %s, %s)",
            (ex.id_livro, ex.codigo_barras, ex.data_aquisicao),
        )
        novo_id = cur.lastrowid
    return {"mensagem": "Exemplar cadastrado", "id_exemplar": novo_id}


@app.get("/exemplares")
def listar_exemplares():
    with db(dictionary=True) as cur:
        cur.execute(
            "SELECT e.*, l.TITULO_LIVRO FROM exemplar e "
            "JOIN livro l ON l.ID_LIVRO = e.ID_LIVRO"
        )
        return cur.fetchall()


# ---------------------------------------------------------------- empréstimos
@app.post("/emprestimos", status_code=201)
def criar_emprestimo(emp: Emprestimo):
    with db(dictionary=True) as cur:
        cur.execute(
            "SELECT DATA_NASCIMENTO FROM aluno WHERE CPF_ALUNO = %s", (emp.cpf_aluno,)
        )
        aluno = cur.fetchone()
        if not aluno:
            raise HTTPException(404, "Aluno não encontrado.")

        cur.execute(
            "SELECT 1 FROM atendente WHERE CPF_ATENDENTE = %s", (emp.cpf_atendente,)
        )
        if not cur.fetchone():
            raise HTTPException(404, "Atendente não encontrado.")

        cur.execute(
            "SELECT 1 FROM exemplar WHERE ID_EXEMPLAR = %s", (emp.id_exemplar,)
        )
        if not cur.fetchone():
            raise HTTPException(404, "Exemplar não encontrado.")

        prazo = PRAZO_PADRAO
        if calcular_idade(aluno["DATA_NASCIMENTO"]) > IDADE_BONUS:
            prazo += DIAS_BONUS

        # o trigger trg_exemplar_unico barra exemplar já emprestado
        cur.execute(
            "INSERT INTO emprestimo (CPF_ALUNO, ID_EXEMPLAR, CPF_ATENDENTE, "
            "DATA_EMPRESTIMO, DATA_DEVOLUCAO) "
            "VALUES (%s, %s, %s, CURDATE(), DATE_ADD(CURDATE(), INTERVAL %s DAY))",
            (emp.cpf_aluno, emp.id_exemplar, emp.cpf_atendente, prazo),
        )
        id_emprestimo = cur.lastrowid
        cur.execute(
            "UPDATE exemplar SET STATUS_EXEMPLAR = 'EMPRESTADO' WHERE ID_EXEMPLAR = %s",
            (emp.id_exemplar,),
        )
    return {
        "mensagem": "Empréstimo registrado",
        "id_emprestimo": id_emprestimo,
        "prazo_dias": prazo,
    }


@app.get("/emprestimos")
def listar_emprestimos():
    with db(dictionary=True) as cur:
        cur.execute(
            "SELECT em.ID_EMPRESTIMO, a.NOME_ALUNO, l.TITULO_LIVRO, ex.CODIGO_BARRAS, "
            "at.NOME_ATENDENTE, em.DATA_EMPRESTIMO, em.DATA_DEVOLUCAO, em.DATA_ENTREGA "
            "FROM emprestimo em "
            "JOIN aluno a      ON a.CPF_ALUNO = em.CPF_ALUNO "
            "JOIN exemplar ex  ON ex.ID_EXEMPLAR = em.ID_EXEMPLAR "
            "JOIN livro l      ON l.ID_LIVRO = ex.ID_LIVRO "
            "JOIN atendente at ON at.CPF_ATENDENTE = em.CPF_ATENDENTE"
        )
        return cur.fetchall()


@app.put("/emprestimos/{id_emprestimo}/devolver")
def devolver(id_emprestimo: int):
    with db(dictionary=True) as cur:
        cur.execute(
            "SELECT ID_EXEMPLAR FROM emprestimo "
            "WHERE ID_EMPRESTIMO = %s AND DATA_ENTREGA IS NULL",
            (id_emprestimo,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Empréstimo não encontrado ou já devolvido.")

        cur.execute(
            "UPDATE emprestimo SET DATA_ENTREGA = CURDATE() WHERE ID_EMPRESTIMO = %s",
            (id_emprestimo,),
        )
        cur.execute(
            "UPDATE exemplar SET STATUS_EXEMPLAR = 'DISPONIVEL' WHERE ID_EXEMPLAR = %s",
            (row["ID_EXEMPLAR"],),
        )
    return {"mensagem": "Devolução registrada"}