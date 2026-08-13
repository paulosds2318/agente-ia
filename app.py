Exit code: 0
Wall time: 0.3 seconds
Total output lines: 1021
Output:
from flask import Flask, render_template, request, jsonify, g, send_file
from google import genai
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import pandas as pd
import os
import sqlite3
import json
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (accuracy_score, f1_score, precision_score, recall_score,
                             mean_absolute_error, mean_squared_error, r2_score,
                             confusion_matrix)
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold, KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

load_dotenv()

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
os.makedirs(app.instance_path, exist_ok=True)
BANCO_DADOS = os.path.join(app.instance_path, "conversas.db")

UPLOAD_FOLDER = os.path.abspath("uploads")
MODEL_FOLDER = os.path.join(app.instance_path, "modelos")
PREDICTION_FOLDER = os.path.join(app.instance_path, "previsoes")
EXTENSOES_PERMITIDAS = {"csv", "xlsx"}
TAMANHO_MAXIMO = 10 * 1024 * 1024

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = TAMANHO_MAXIMO

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MODEL_FOLDER, exist_ok=True)
os.makedirs(PREDICTION_FOLDER, exist_ok=True)
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="atlas-ml")

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


@app.after_request
def cabecalhos_seguranca(resposta):
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "SAMEORIGIN"
    resposta.headers["Referrer-Policy"] = "same-origin"
    resposta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return resposta

def obter_banco():
    if "banco" not in g:
        g.banco = sqlite3.connect(BANCO_DADOS)
        g.banco.row_factory = sqlite3.Row
        g.banco.execute("PRAGMA foreign_keys = ON")
    return g.banco


@app.teardown_appcontext
def fechar_banco(erro=None):
    banco = g.pop("banco", None)
    if banco is not None:
        banco.close()


def iniciar_banco():
    with app.app_context():
        banco = obter_banco()
        banco.executescript("""
            CREATE TABLE IF NOT EXISTS conversas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                criada_em TEXT NOT NULL,
                atualizada_em TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mensagens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversa_id INTEGER NOT NULL,
                autor TEXT NOT NULL CHECK (autor IN ('usuario', 'agente')),
                conteudo TEXT NOT NULL,
                criada_em TEXT NOT NULL,
                FOREIGN KEY (conversa_id) REFERENCES conversas(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_mensagens_conversa
                ON mensagens(conversa_id, id);
            CREATE TABLE IF NOT EXISTS arquivos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversa_id INTEGER NOT NULL,
                nome_original TEXT NOT NULL,
                caminho TEXT NOT NULL UNIQUE,
                extensao TEXT NOT NULL,
                tamanho INTEGER NOT NULL,
                linhas INTEGER NOT NULL,
                colunas INTEGER NOT NULL,
                resumo_json TEXT NOT NULL,
                criada_em TEXT NOT NULL,
                FOREIGN KEY (conversa_id) REFERENCES conversas(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS modelos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversa_id INTEGER NOT NULL,
                arquivo_id INTEGER NOT NULL,
                alvo TEXT NOT NULL,
                tipo TEXT NOT NULL,
                nome TEXT NOT NULL,
                caminho TEXT NOT NULL UNIQUE,
                recursos_json TEXT NOT NULL,
                metricas_json TEXT NOT NULL,
                criada_em TEXT NOT NULL,
                FOREIGN KEY (conversa_id) REFERENCES conversas(id) ON DELETE CASCADE,
                FOREIGN KEY (arquivo_id) REFERENCES arquivos(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS tarefas (
                id TEXT PRIMARY KEY,
                conversa_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                status TEXT NOT NULL,
                progresso INTEGER NOT NULL DEFAULT 0,
                resultado_json TEXT,
                erro TEXT,
                criada_em TEXT NOT NULL,
                atualizada_em TEXT NOT NULL,
                FOREIGN KEY (conversa_id) REFERENCES conversas(id) ON DELETE CASCADE
            );
        """)
        colunas_mensagens = {item[1] for item in banco.execute("PRAGMA table_info(mensagens)")}
        if "status" not in colunas_mensagens:
            banco.execute("ALTER TABLE mensagens ADD COLUMN status TEXT NOT NULL DEFAULT 'concluida'")
        if "erro" not in colunas_mensagens:
            banco.execute("ALTER TABLE mensagens ADD COLUMN erro TEXT")
        banco.commit()


def agora_iso():
    return datetime.now(timezone.utc).isoformat()


def salvar_mensagem(conversa_id, autor, conteudo, status="concluida", erro=None):
    banco = obter_banco()
    if banco.execute("SELECT id FROM conversas WHERE id = ?", (conversa_id,)).fetchone() is None:
        raise ValueError("Conversa não encontrada.")
    agora = agora_iso()
    cursor = banco.execute(
        "INSERT INTO mensagens (conversa_id, autor, conteudo, criada_em, status, erro) VALUES (?, ?, ?, ?, ?, ?)",
        (conversa_id, autor, conteudo, agora, status, erro)
    )
    banco.execute("UPDATE conversas SET atualizada_em = ? WHERE id = ?", (agora, conversa_id))
    banco.commit()
    return cursor.lastrowid


def obter_conversa(conversa_id, banco=None):
    banco = banco or obter_banco()
    return banco.execute("SELECT * FROM conversas WHERE id = ?", (conversa_id,)).fetchone()


def arquivo_da_conversa(conversa_id, banco=None):
    banco = banco or obter_banco()
    return banco.execute(
        "SELECT * FROM arquivos WHERE conversa_id = ? ORDER BY id DESC LIMIT 1", (conversa_id,)
    ).fetchone()


def modelo_da_conversa(conversa_id, banco=None):
    banco = banco or obter_banco()
    return banco.execute(
        "SELECT * FROM modelos WHERE conversa_id = ? ORDER BY id DESC LIMIT 1", (conversa_id,)
    ).fetchone()


def carregar_dataframe(registro):
    caminho = registro["caminho"]
    if not os.path.isfile(caminho):
        raise ValueError("O arquivo associado não está mais disponível.")
    return pd.read_csv(caminho) if registro["extensao"] == "csv" else pd.read_excel(caminho)


def remover_arquivo_seguro(caminho, pasta_permitida):
    alvo = Path(caminho).resolve()
    raiz = Path(pasta_permitida).resolve()
    if raiz not in alvo.parents or not alvo.is_file() or alvo.is_symlink():
        return
    alvo.unlink()


@app.route("/conversas", methods=["GET"])
def listar_conversas():
    linhas = obter_banco().execute("""
        SELECT c.id, c.titulo, c.criada_em, c.atualizada_em, COUNT(m.id) AS total_mensagens
        FROM conversas c LEFT JOIN mensagens m ON m.conversa_id = c.id
        GROUP BY c.id ORDER BY c.atualizada_em DESC
    """).fetchall()
    return jsonify([dict(linha) for linha in linhas])


@app.route("/conversas", methods=["POST"])
def criar_conversa():
    agora = agora_iso()
    banco = obter_banco()
    cursor = banco.execute(
        "INSERT INTO conversas (titulo, criada_em, atualizada_em) VALUES (?, ?, ?)",
        ("Nova conversa", agora, agora)
    )
    banco.commit()
    return jsonify({"id": cursor.lastrowid, "titulo": "Nova conversa"}), 201


@app.route("/conversas/<int:conversa_id>/mensagens", methods=["GET"])
def listar_mensagens(conversa_id):
    banco = obter_banco()
    conversa = banco.execute("SELECT id, titulo FROM conversas WHERE id = ?", (conversa_id,)).fetchone()
    if conversa is None:
        return jsonify({"erro": "Conversa não encontrada."}), 404
    mensagens = banco.execute(
        "SELECT id, autor, conteudo, criada_em, status, erro FROM mensagens WHERE conversa_id = ? ORDER BY id",
        (conversa_id,)
    ).fetchall()
    arquivo = arquivo_da_conversa(conversa_id, banco)
    modelo = modelo_da_conversa(conversa_id, banco)
    arquivo_publico = None
    if arquivo:
        arquivo_publico = {
            "id": arquivo["id"], "nome_original": arquivo["nome_original"],
            "tamanho": arquivo["tamanho"], "linhas": arquivo["linhas"],
            "colunas": arquivo["colunas"], "resumo_json": arquivo["resumo_json"],
            "criada_em": arquivo["criada_em"]
        }
    modelo_publico = None
    if modelo:
        modelo_publico = {
            "id": modelo["id"], "alvo": modelo["alvo"], "tipo": modelo["tipo"],
            "nome": modelo["nome"], "metricas_json": modelo["metricas_json"],
            "criada_em": modelo["criada_em"]
        }
    return jsonify({
        "conversa": dict(conversa),
        "mensagens": [dict(m) for m in mensagens],
        "arquivo": arquivo_publico,
        "modelo": modelo_publico
    })


@app.route("/conversas/<int:conversa_id>", methods=["DELETE"])
def excluir_conversa(conversa_id):
    banco = obter_banco()
    arquivos = banco.execute("SELECT caminho FROM arquivos WHERE conversa_id = ?", (conversa_id,)).fetchall()
    modelos = banco.execute("SELECT caminho FROM modelos WHERE conversa_id = ?", (conversa_id,)).fetchall()
    cursor = banco.execute("DELETE FROM conversas WHERE id = ?", (conversa_id,))
    banco.commit()
    if cursor.rowcount == 0:
        return jsonify({"erro": "Conversa não encontrada."}), 404
    for item in arquivos:
        remover_arquivo_seguro(item["caminho"], UPLOAD_FOLDER)
    for item in modelos:
        remover_arquivo_seguro(item["caminho"], MODEL_FOLDER)
    return "", 204


def extensao_permitida(nome):
    return (
        "." in nome
        and nome.rsplit(".", 1)[1].lower() in EXTENSOES_PERMITIDAS
    )


def gerar_resumo_dataframe(df):
    resumo = []

    resumo.append(f"Total de linhas: {len(df)}")
    resumo.append(f"Total de colunas: {len(df.columns)}")

    resumo.append(
        "Colunas: " + ", ".join(map(str, df.columns))
    )

    resumo.append("\nTipos das colunas:")

    for coluna, tipo in df.dtypes.items():
        resumo.append(
            f"- {coluna}: {tipo}"
        )

    resumo.append("\nValores nulos:")

    nulos = df.isnull().sum()

    for coluna, quantidade in nulos.items():
        if quantidade > 0:
            resumo.append(
                f"- {coluna}: {int(quantidade)}"
            )

    resumo.append(
        f"\nLinhas duplicadas: {int(df.duplicated().sum())}"
    )

    # Estatísticas das colunas numéricas
    numericas = df.select_dtypes(
        include="number"
    )

    if not numericas.empty:

        resumo.append(
            "\nEstatísticas das colunas numéricas:"
        )

        estatisticas = numericas.describe()

        resumo.append(
            estatisticas.to_string()
        )

    # Principais valores em colunas categóricas
    categoricas = df.select_dtypes(
        include=["object", "category"]
    )

    if not categoricas.empty:

        resumo.append(
            "\nPrincipais valores das colunas categóricas:"
        )

        for coluna in categoricas.columns:

            valores = (
                df[coluna]
                .value_counts(dropna=False)
                .head(10)
            )

            resumo.append(
                f"\nColuna: {coluna}"
            )

            resumo.append(
                valores.to_string()
            )

    return "\n".join(resumo)


def preparar_treinamento(df, alvo):
    if alvo not in df.columns:
        raise ValueError("A coluna-alvo selecionada não existe.")

    dados = df.dropna(subset=[alvo]).copy()
    if len(dados) < 20:
        raise ValueError("São necessárias pelo menos 20 linhas com valor na coluna-alvo.")

    # Evita que identificadores únicos e textos livres explodam a codificação.
    recursos = dados.drop(columns=[alvo])
    descartadas = []
    for coluna in recursos.columns:
        proporcao_unicos = recursos[coluna].nunique(dropna=True) / max(len(recursos), 1)
        if (
            pd.api.types.is_string_dtype(recursos[coluna])
            and proporcao_unicos > 0.8
        ):
            descartadas.append(coluna)
    recursos = recursos.drop(columns=descartadas)
    recursos = recursos.dropna(axis=1, how="all")
    if recursos.shape[1] == 0:
        raise ValueError("Não há colunas preditoras utilizáveis após a preparação.")

    alvo_dados = dados[alvo]
    unicos = alvo_dados.nunique(dropna=True)
    classificacao = (
        not pd.api.types.is_numeric_dtype(alvo_dados)
        or unicos <= min(30, max(2, int(len(alvo_dados) * 0.05)))
    )
    if classificacao and unicos < 2:
        raise ValueError("A coluna-alvo precisa ter pelo menos duas classes.")

    numericas = recursos.select_dtypes(include="number").columns.tolist()
    categoricas = [c for c in recursos.columns if c not in numericas]
    transformadores = []
    if numericas:
        transformadores.append(("numericas", Pipeline([
            ("imputar", SimpleImputer(strategy="median")),
            ("escalar", StandardScaler())
        ]), numericas))
    if categoricas:
        transformadores.append(("categoricas", Pipeline([
            ("imputar", SimpleImputer(strategy="most_frequent")),
            ("codificar", OneHotEncoder(handle_unknown="ignore", max_categories=50))
        ]), categoricas))

    return recursos, alvo_dados, ColumnTransformer(transformadores), classificacao, descartadas


def treinar_legado():
    global modelo_atual

    if df_atual is None:
        return jsonify({"erro": "Envie uma base antes de treinar um modelo."}), 400

    dados = request.get_json(silent=True) or {}
    alvo = str(dados.get("alvo", "")).strip()
    if not alvo:
        return jsonify({"erro": "Selecione a coluna que deseja prever."}), 400

    try:
        x, y, preparador, classificacao, descartadas = preparar_treinamento(df_atual, alvo)
        estratificar = y if classificacao and y.value_counts().min() >= 2 else None
        x_treino, x_teste, y_treino, y_teste = train_test_split(
            x, y, test_size=0.2, random_state=42, stratify=estratificar
        )

        if classificacao:
            modelos = {
                "Regressão logística": LogisticRegression(max_iter=1000),
                "Floresta aleatória": RandomForestClassifier(
                    n_estimators=150, random_state=42, n_jobs=-1, class_weight="balanced"
                )
            }
        else:
            modelos = {
                "Regressão linear": LinearRegression(),
                "Floresta aleatória": RandomForestRegressor(
                    n_estimators=150, random_state=42, n_jobs=-1
                )
            }

        resultados = []
        melhor_pipeline = None
        melhor_pontuacao = float("-inf")
        for nome, estimador in modelos.items():
            pipeline = Pipeline([("preparacao", preparador), ("modelo", estimador)])
            pipeline.fit(x_treino, y_treino)
            previsoes = pipeline.predict(x_teste)
            if classificacao:
                metricas = {
                    "acuracia": round(float(accuracy_score(y_teste, previsoes)), 4),
                    "f1": round(float(f1_score(y_teste, previsoes, average="weighted", zero_division=0)), 4)
                }
                pontuacao = metricas["f1"]
            else:
                metricas = {
                    "r2": round(float(r2_score(y_teste, previsoes)), 4),
                    "mae": round(float(mean_absolute_error(y_teste, previsoes)), 4)
                }
                pontuacao = metricas["r2"]
            resultados.append({"modelo": nome, "metricas": metricas})
            if pontuacao > melhor_pontuacao:
                melhor_pontuacao = pontuacao
                melhor_pipeline = pipeline

        resultados.sort(
            key=lambda item: item["metricas"].get("f1", item["metricas"].get("r2", -999)),
            reverse=True
        )
        modelo_atual = melhor_pipeline
        return jsonify({
            "tipo": "classificação" if classificacao else "regressão",
            "alvo": alvo,
            "linhas_treino": len(x_treino),
            "linhas_teste": len(x_teste),
            "recursos": x.shape[1],
            "colunas_descartadas": descartadas,
            "melhor_modelo": resultados[0]["modelo"],
            "resultados": resultados
        })
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400
    except Exception as erro:
        print("Erro no treinamento:", erro)
        return jsonify({"erro": "Não foi possível treinar os modelos com esta base."}), 500


@app.route("/")
def inicio():
    return render_template("index.html")


def upload_legado():

    global df_atual
    global nome_arquivo_atual

    if "arquivo" not in request.files:
        return jsonify({
            "erro": "Nenhum arquivo foi enviado."
        }), 400

    arquivo = request.files["arquivo"]

    if arquivo.filename == "":
        return jsonify({
            "erro": "Selecione um arquivo."
        }), 400

    if not extensao_permitida(arquivo.filename):
        return jsonify({
            "erro": "Formato inválido. Envie somente CSV ou XLSX."
        }), 400

    nome_seguro = secure_filename(
        arquivo.filename
    )

    caminho = os.path.join(
        app.config["UPLOAD_FOLDER"],
        nome_seguro
    )

    try:

        arquivo.save(caminho)

        if nome_seguro.lower().endswith(".csv"):

            df = pd.read_csv(
                caminho
            )

        else:

            df = pd.read_excel(
                caminho
            )

        if df.empty:
            return jsonify({
                "erro": "O arquivo está vazio."
            }), 400

        df_atual = df
        nome_arquivo_atual = nome_seguro

        total_linhas = len(df)
        total_colunas = len(df.columns)

        total_nulos = int(
            df.isnull().sum().sum()
        )

        total_celulas = (
            total_linhas
            * total_colunas
        )

        percentual_nulos = 0

        if total_celulas > 0:
            percentual_nulos = round(
                (
                    total_nulos
                    / total_celulas
                ) * 100,
                2
            )

        duplicados = int(
            df.duplicated().sum()
        )

        colunas_vazias = [
            coluna
            for coluna in df.columns
            if df[coluna].isnull().all()
        ]

        tipos_colunas = {
            coluna: str(tipo)
            for coluna, tipo
            in df.dtypes.items()
        }

        nulos_por_coluna = {
            coluna: int(valor)
            for coluna, valor
            in df.isnull().sum().items()
            if valor > 0
        }

        return jsonify({

            "mensagem":
                f"Arquivo {nome_seguro} validado e carregado com sucesso!",

            "linhas":
                total_linhas,

            "colunas":
                list(df.columns),

            "qualidade": {

                …141 tokens truncated…rn jsonify({
            "erro": "O arquivo não possui dados válidos."
        }), 400

    except Exception as erro:

        print(
            "Erro no upload:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível processar o arquivo."
        }), 500


def perguntar_legado():

    global df_atual
    global nome_arquivo_atual

    dados = request.get_json(
        silent=True
    )

    if not dados:
        return jsonify({
            "erro": "Requisição inválida."
        }), 400

    mensagem = dados.get(
        "mensagem",
        ""
    ).strip()

    conversa_id = dados.get("conversa_id")

    if not isinstance(conversa_id, int):
        return jsonify({"erro": "Conversa inválida."}), 400

    if not mensagem:
        return jsonify({
            "erro": "Digite uma mensagem."
        }), 400

    if len(mensagem) > 3000:
        return jsonify({
            "erro": "Sua mensagem é muito grande."
        }), 400

    contexto = mensagem

    # Se existe uma planilha carregada,
    # geramos um resumo da base inteira.
    if df_atual is not None:

        resumo = gerar_resumo_dataframe(
            df_atual
        )

        contexto = f"""
Você é um assistente especializado em análise de dados.

Existe uma base carregada chamada:
{nome_arquivo_atual}

As informações abaixo foram calculadas pelo Python usando a base completa.

RESUMO DA BASE:

{resumo}

PERGUNTA DO USUÁRIO:

{mensagem}

Regras:

1. Use as informações calculadas pelo Python para responder.
2. Não invente valores que não aparecem no resumo.
3. Se a pergunta exigir um cálculo específico que não esteja no resumo, diga que é necessário calcular esse indicador.
4. Responda em português.
5. Seja claro, direto e didático.
"""

    try:

        salvar_mensagem(conversa_id, "usuario", mensagem)

        historico = obter_banco().execute(
            "SELECT autor, conteudo FROM mensagens WHERE conversa_id = ? ORDER BY id DESC LIMIT 12",
            (conversa_id,)
        ).fetchall()

        historico_texto = "\n".join(
            f"{'Usuário' if item['autor'] == 'usuario' else 'Assistente'}: {item['conteudo']}"
            for item in reversed(historico)
        )

        contexto = (
            f"Histórico desta conversa:\n{historico_texto}"
            f"\n\nContexto e solicitação atual:\n{contexto}"
        )

        conversa_chat = client.chats.create(
            model="gemini-3.6-flash"
        )

        resposta = conversa_chat.send_message(
            contexto
        )

        if not resposta.text:
            return jsonify({
                "erro":
                    "A IA não retornou uma resposta."
            }), 500

        salvar_mensagem(conversa_id, "agente", resposta.text)

        banco = obter_banco()
        total = banco.execute(
            "SELECT COUNT(*) FROM mensagens WHERE conversa_id = ?", (conversa_id,)
        ).fetchone()[0]
        titulo = None
        if total == 2:
            titulo = mensagem[:55] + ("…" if len(mensagem) > 55 else "")
            banco.execute("UPDATE conversas SET titulo = ? WHERE id = ?", (titulo, conversa_id))
            banco.commit()

        return jsonify({
            "resposta":
                resposta.text,
            "titulo": titulo
        })

    except Exception as erro:

        print(
            "Erro Gemini:",
            erro
        )

        return jsonify({
            "erro":
                "Não foi possível obter resposta da IA."
        }), 500


def diagnostico_qualidade(df):
    total_linhas, total_colunas = len(df), len(df.columns)
    total_nulos = int(df.isnull().sum().sum())
    total_celulas = total_linhas * total_colunas
    return {
        "total_colunas": total_colunas,
        "total_nulos": total_nulos,
        "percentual_nulos": round(total_nulos / total_celulas * 100, 2) if total_celulas else 0,
        "duplicados": int(df.duplicated().sum()),
        "colunas_vazias": [str(c) for c in df.columns if df[c].isnull().all()],
        "nulos_por_coluna": {str(c): int(v) for c, v in df.isnull().sum().items() if v > 0},
        "tipos": {str(c): str(t) for c, t in df.dtypes.items()}
    }


@app.route("/upload", methods=["POST"])
def upload():
    conversa_id = request.form.get("conversa_id", type=int)
    if not conversa_id or obter_conversa(conversa_id) is None:
        return jsonify({"erro": "Conversa inválida."}), 400
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify({"erro": "Selecione um arquivo."}), 400
    if not extensao_permitida(arquivo.filename):
        return jsonify({"erro": "Formato inválido. Envie somente CSV ou XLSX."}), 400

    nome_original = arquivo.filename
    extensao = secure_filename(nome_original).rsplit(".", 1)[1].lower()
    caminho = os.path.join(UPLOAD_FOLDER, f"{conversa_id}_{uuid.uuid4().hex}.{extensao}")
    try:
        arquivo.save(caminho)
        df = pd.read_csv(caminho) if extensao == "csv" else pd.read_excel(caminho)
        if df.empty:
            raise ValueError("O arquivo está vazio.")
        if len(df) > 1_000_000 or len(df.columns) > 1_000:
            raise ValueError("A base excede o limite de 1 milhão de linhas ou 1.000 colunas.")
        qualidade = diagnostico_qualidade(df)
        banco = obter_banco()
        antigos = banco.execute("SELECT caminho FROM arquivos WHERE conversa_id = ?", (conversa_id,)).fetchall()
        modelos = banco.execute("SELECT caminho FROM modelos WHERE conversa_id = ?", (conversa_id,)).fetchall()
        banco.execute("DELETE FROM arquivos WHERE conversa_id = ?", (conversa_id,))
        cursor = banco.execute("""
            INSERT INTO arquivos (conversa_id, nome_original, caminho, extensao, tamanho,
                                  linhas, colunas, resumo_json, criada_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (conversa_id, nome_original, caminho, extensao, os.path.getsize(caminho),
              len(df), len(df.columns), json.dumps(qualidade, ensure_ascii=False), agora_iso()))
        banco.commit()
        for item in antigos:
            if item["caminho"] != caminho:
                remover_arquivo_seguro(item["caminho"], UPLOAD_FOLDER)
        for item in modelos:
            remover_arquivo_seguro(item["caminho"], MODEL_FOLDER)
        return jsonify({"mensagem": f"Arquivo {nome_original} carregado com sucesso!",
                        "arquivo_id": cursor.lastrowid, "linhas": len(df),
                        "colunas": [str(c) for c in df.columns], "qualidade": qualidade})
    except (ValueError, pd.errors.EmptyDataError) as erro:
        if os.path.isfile(caminho): os.remove(caminho)
        return jsonify({"erro": str(erro) or "O arquivo não possui dados válidos."}), 400
    except Exception as erro:
        if os.path.isfile(caminho): os.remove(caminho)
        print("Erro no upload:", erro)
        return jsonify({"erro": "Não foi possível processar o arquivo."}), 500


def executar_treinamento(tarefa_id, conversa_id, alvo):
    with app.app_context():
        banco = obter_banco()
        try:
            banco.execute("UPDATE tarefas SET status='processando', progresso=10, atualizada_em=? WHERE id=?",
                          (agora_iso(), tarefa_id)); banco.commit()
            arquivo = arquivo_da_conversa(conversa_id, banco)
            if arquivo is None: raise ValueError("Envie uma base antes de treinar.")
            df = carregar_dataframe(arquivo)
            x, y, preparador, classificacao, descartadas = preparar_treinamento(df, alvo)
            contagens = y.value_counts()
            avisos = []
            if len(y) < 100: avisos.append("Base pequena: interprete as métricas com cautela.")
            if classificacao and contagens.min() / contagens.max() < .25:
                avisos.append("Classes desbalanceadas detectadas.")
            estratificar = y if classificacao and contagens.min() >= 2 else None
            x_tr, x_te, y_tr, y_te = train_test_split(x, y, test_size=.2, random_state=42, stratify=estratificar)
            modelos = ({
                "Regressão logística": LogisticRegression(max_iter=1500, class_weight="balanced"),
                "Floresta aleatória": RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1, class_weight="balanced")
            } if classificacao else {
                "Regressão linear": LinearRegression(),
                "Floresta aleatória": RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1)
            })
            resultados, melhor, melhor_nome, melhor_score = [], None, None, float("-inf")
            for indice, (nome, estimador) in enumerate(modelos.items()):
                pipeline = Pipeline([("preparacao", preparador), ("modelo", estimador)])
                pipeline.fit(x_tr, y_tr); previsto = pipeline.predict(x_te)
                folds = min(5, int(contagens.min()) if classificacao else len(y) // 5)
                folds = max(2, folds)
                cv = StratifiedKFold(folds, shuffle=True, random_state=42) if classificacao else KFold(folds, shuffle=True, random_state=42)
                scoring = "f1_weighted" if classificacao else "r2"
                cv_scores = cross_val_score(pipeline, x, y, cv=cv, scoring=scoring, n_jobs=1)
                if classificacao:
                    metricas = {"acuracia": accuracy_score(y_te, previsto),
                                "f1": f1_score(y_te, previsto, average="weighted", zero_division=0),
                                "precisao": precision_score(y_te, previsto, average="weighted", zero_division=0),
                                "recall": recall_score(y_te, previsto, average="weighted", zero_division=0),
                                "matriz_confusao": confusion_matrix(y_te, previsto).tolist(),
                                "validacao_cruzada": float(cv_scores.mean())}
                    score = metricas["f1"]
                else:
                    metricas = {"r2": r2_score(y_te, previsto), "mae": mean_absolute_error(y_te, previsto),
                                "rmse": mean_squared_error(y_te, previsto) ** .5,
                                "validacao_cruzada": float(cv_scores.mean())}
                    score = metricas["r2"]
                metricas = {k: (round(float(v), 4) if not isinstance(v, list) else v) for k, v in metricas.items()}
                resultados.append({"modelo": nome, "metricas": metricas})
                if score > melhor_score: melhor, melhor_nome, melhor_score = pipeline, nome, score
                banco.execute("UPDATE tarefas SET progresso=?, atualizada_em=? WHERE id=?",
                              (45 + indice * 35, agora_iso(), tarefa_id)); banco.commit()
            resultados.sort(key=lambda r: r["metricas"].get("f1", r["metricas"].get("r2", -999)), reverse=True)
            caminho_modelo = os.path.join(MODEL_FOLDER, f"{conversa_id}_{uuid.uuid4().hex}.joblib")
            pacote = {"pipeline": melhor, "colunas": list(x.columns), "alvo": alvo,
                      "tipo": "classificação" if classificacao else "regressão"}
            joblib.dump(pacote, caminho_modelo)
            resultado = {"tipo": pacote["tipo"], "alvo": alvo, "linhas_treino": len(x_tr),
                         "linhas_teste": len(x_te), "recursos": x.shape[1], "avisos": avisos,
                         "colunas_descartadas": descartadas, "melhor_modelo": melhor_nome,
                         "resultados": resultados}
            antigos = banco.execute("SELECT caminho FROM modelos WHERE conversa_id=?", (conversa_id,)).fetchall()
            banco.execute("DELETE FROM modelos WHERE conversa_id=?", (conversa_id,))
            banco.execute("""INSERT INTO modelos (conversa_id, arquivo_id, alvo, tipo, nome, caminho,
                              recursos_json, metricas_json, criada_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (conversa_id, arquivo["id"], alvo, pacote["tipo"], melhor_nome, caminho_modelo,
                           json.dumps(list(x.columns), ensure_ascii=False), json.dumps(resultado, ensure_ascii=False), agora_iso()))
            banco.execute("UPDATE tarefas SET status='concluida', progresso=100, resultado_json=?, atualizada_em=? WHERE id=?",
                          (json.dumps(resultado, ensure_ascii=False), agora_iso(), tarefa_id)); banco.commit()
            for item in antigos: remover_arquivo_seguro(item["caminho"], MODEL_FOLDER)
        except Exception as erro:
            banco.execute("UPDATE tarefas SET status='falhou', erro=?, atualizada_em=? WHERE id=?",
                          (str(erro), agora_iso(), tarefa_id)); banco.commit()


@app.route("/treinar", methods=["POST"])
def treinar():
    dados = request.get_json(silent=True) or {}; conversa_id = dados.get("conversa_id"); alvo = str(dados.get("alvo", "")).strip()
    if not isinstance(conversa_id, int) or obter_conversa(conversa_id) is None:
        return jsonify({"erro": "Conversa inválida."}), 400
    if not alvo: return jsonify({"erro": "Selecione a coluna que deseja prever."}), 400
    if arquivo_da_conversa(conversa_id) is None: return jsonify({"erro": "Envie uma base antes de treinar."}), 400
    tarefa_id = uuid.uuid4().hex; agora = agora_iso(); banco = obter_banco()
    banco.execute("INSERT INTO tarefas (id, conversa_id, tipo, status, progresso, criada_em, atualizada_em) VALUES (?,?,'treinamento','pendente',0,?,?)",
                  (tarefa_id, conversa_id, agora, agora)); banco.commit()
    executor.submit(executar_treinamento, tarefa_id, conversa_id, alvo)
    return jsonify({"tarefa_id": tarefa_id, "status": "pendente"}), 202


@app.route("/tarefas/<tarefa_id>")
def consultar_tarefa(tarefa_id):
    tarefa = obter_banco().execute("SELECT * FROM tarefas WHERE id=?", (tarefa_id,)).fetchone()
    if tarefa is None: return jsonify({"erro": "Tarefa não encontrada."}), 404
    dados = dict(tarefa); dados["resultado"] = json.loads(dados.pop("resultado_json")) if dados["resultado_json"] else None
    return jsonify(dados)


@app.route("/prever", methods=["POST"])
def prever():
    conversa_id = request.form.get("conversa_id", type=int); arquivo = request.files.get("arquivo")
    if not conversa_id or obter_conversa(conversa_id) is None: return jsonify({"erro": "Conversa inválida."}), 400
    modelo = modelo_da_conversa(conversa_id)
    if modelo is None or not os.path.isfile(modelo["caminho"]): return jsonify({"erro": "Treine um modelo antes de prever."}), 400
    if not arquivo or not extensao_permitida(arquivo.filename): return jsonify({"erro": "Envie um CSV ou XLSX válido."}), 400
    try:
        entrada = pd.read_csv(arquivo) if arquivo.filename.lower().endswith(".csv") else pd.read_excel(arquivo)
        pacote = joblib.load(modelo["caminho"]); ausentes = [c for c in pacote["colunas"] if c not in entrada.columns]
        if ausentes: return jsonify({"erro": "Faltam colunas: " + ", ".join(map(str, ausentes))}), 400
        previsoes = pacote["pipeline"].predict(entrada[pacote["colunas"]]); saida = entrada.copy()
        saida[f"previsao_{pacote['alvo']}"] = previsoes
        if pacote["tipo"] == "classificação" and hasattr(pacote["pipeline"], "predict_proba"):
            probabilidades = pacote["pipeline"].predict_proba(entrada[pacote["colunas"]])
            saida["confianca_previsao"] = probabilidades.max(axis=1)
        token = uuid.uuid4().hex; caminho = os.path.join(PREDICTION_FOLDER, f"{token}.csv")
        saida.to_csv(caminho, index=False, encoding="utf-8-sig")
        return jsonify({"mensagem": f"{len(saida)} previsões geradas.", "download": f"/previsoes/{token}"})
    except Exception as erro:
        print("Erro na previsão:", erro); return jsonify({"erro": "Não foi possível gerar as previsões."}), 500


@app.route("/previsoes/<token>")
def baixar_previsao(token):
    if not token.isalnum(): return jsonify({"erro": "Arquivo inválido."}), 400
    caminho = os.path.join(PREDICTION_FOLDER, f"{token}.csv")
    if not os.path.isfile(caminho): return jsonify({"erro": "Previsão não encontrada."}), 404
    return send_file(caminho, as_attachment=True, download_name="previsoes.csv")


@app.route("/perguntar", methods=["POST"])
def perguntar():
    dados = request.get_json(silent=True) or {}; mensagem = str(dados.get("mensagem", "")).strip(); conversa_id = dados.get("conversa_id")
    if not isinstance(conversa_id, int) or obter_conversa(conversa_id) is None: return jsonify({"erro": "Conversa inválida."}), 400
    if not mensagem: return jsonify({"erro": "Digite uma mensagem."}), 400
    if len(mensagem) > 3000: return jsonify({"erro": "Sua mensagem é muito grande."}), 400
    mensagem_id = salvar_mensagem(conversa_id, "usuario", mensagem, "processando")
    try:
        registro = arquivo_da_conversa(conversa_id); contexto_dados = ""
        if registro:
            df = carregar_dataframe(registro)
            contexto_dados = f"\nBase carregada: {registro['nome_original']}\n{gerar_resumo_dataframe(df)}\n"
        historico = obter_banco().execute("SELECT autor, conteudo FROM mensagens WHERE conversa_id=? ORDER BY id DESC LIMIT 12", (conversa_id,)).fetchall()
        contexto = "Você é um assistente de análise de dados. Responda em português, sem inventar valores.\n" + contexto_dados
        contexto += "\nHistórico:\n" + "\n".join(f"{m['autor']}: {m['conteudo']}" for m in reversed(historico))
        resposta = client.chats.create(model="gemini-3.6-flash").send_message(contexto)
        if not resposta.text: raise RuntimeError("A IA retornou uma resposta vazia.")
        salvar_mensagem(conversa_id, "agente", resposta.text)
        banco = obter_banco(); banco.execute("UPDATE mensagens SET status='concluida', erro=NULL WHERE id=?", (mensagem_id,))
        total = banco.execute("SELECT COUNT(*) FROM mensagens WHERE conversa_id=?", (conversa_id,)).fetchone()[0]; titulo = None
        if total == 2:
            titulo = mensagem[:55] + ("…" if len(mensagem) > 55 else ""); banco.execute("UPDATE conversas SET titulo=? WHERE id=?", (titulo, conversa_id))
        banco.commit(); return jsonify({"resposta": resposta.text, "titulo": titulo})
    except Exception as erro:
        texto = str(erro); codigo = 500; mensagem_erro = "Não foi possível obter resposta da IA."
        if "429" in texto or "RESOURCE_EXHAUSTED" in texto: codigo, mensagem_erro = 429, "Limite da IA atingido. Aguarde e tente novamente."
        elif "401" in texto or "API_KEY" in texto: codigo, mensagem_erro = 503, "A chave da IA está inválida ou ausente."
        elif "timeout" in texto.lower(): codigo, mensagem_erro = 504, "A IA demorou demais para responder. Tente novamente."
        banco = obter_banco(); banco.execute("UPDATE mensagens SET status='falhou', erro=? WHERE id=?", (mensagem_erro, mensagem_id)); banco.commit()
        print("Erro Gemini:", erro); return jsonify({"erro": mensagem_erro, "mensagem_id": mensagem_id}), codigo


@app.route("/mensagens/<int:mensagem_id>/tentar-novamente", methods=["POST"])
def tentar_novamente(mensagem_id):
    item = obter_banco().execute("SELECT conversa_id, conteudo, status FROM mensagens WHERE id=? AND autor='usuario'", (mensagem_id,)).fetchone()
    if item is None: return jsonify({"erro": "Mensagem não encontrada."}), 404
    obter_banco().execute("DELETE FROM mensagens WHERE id=?", (mensagem_id,)); obter_banco().commit()
    with app.test_request_context(json={"conversa_id": item["conversa_id"], "mensagem": item["conteudo"]}):
        return perguntar()


@app.errorhandler(413)
def arquivo_muito_grande(erro):

    return jsonify({
        "erro":
            "Arquivo muito grande. O limite é 10 MB."
    }), 413


iniciar_banco()


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")

