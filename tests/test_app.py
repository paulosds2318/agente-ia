import io
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import app as modulo


class AtlasTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        modulo.BANCO_DADOS = os.path.join(self.temp.name, "teste.db")
        modulo.UPLOAD_FOLDER = os.path.join(self.temp.name, "uploads")
        modulo.MODEL_FOLDER = os.path.join(self.temp.name, "modelos")
        modulo.PREDICTION_FOLDER = os.path.join(self.temp.name, "previsoes")
        for pasta in (modulo.UPLOAD_FOLDER, modulo.MODEL_FOLDER, modulo.PREDICTION_FOLDER):
            os.makedirs(pasta)
        modulo.app.config.update(TESTING=True, UPLOAD_FOLDER=modulo.UPLOAD_FOLDER)
        modulo.rate_limiter = modulo.InMemoryRateLimiter(10_000)
        modulo.iniciar_banco()
        self.cliente = modulo.app.test_client()
        self.conversa = self.cliente.post("/conversas").get_json()["id"]

    def tearDown(self):
        self.temp.cleanup()

    def csv_treino(self, n=80):
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "idade": rng.integers(18, 70, n),
            "renda": rng.normal(5000, 900, n),
            "cidade": rng.choice(["Recife", "Natal"], n),
            "comprou": np.where(rng.integers(18, 70, n) > 40, "sim", "nao")
        })
        return io.BytesIO(df.to_csv(index=False).encode("utf-8"))

    def enviar_base(self):
        return self.cliente.post("/upload", data={
            "conversa_id": str(self.conversa),
            "arquivo": (self.csv_treino(), "clientes.csv")
        }, content_type="multipart/form-data")

    def test_historico_persistente(self):
        with patch.object(modulo.ai, "send_message", return_value="Resposta salva"):
            resposta = self.cliente.post("/perguntar", json={
                "conversa_id": self.conversa, "mensagem": "Analise esta base"
            })
        self.assertEqual(resposta.status_code, 200)
        mensagens = self.cliente.get(f"/conversas/{self.conversa}/mensagens").get_json()["mensagens"]
        self.assertEqual([m["autor"] for m in mensagens], ["usuario", "agente"])

    def test_upload_fica_associado_a_conversa(self):
        resposta = self.enviar_base()
        self.assertEqual(resposta.status_code, 200)
        detalhes = self.cliente.get(f"/conversas/{self.conversa}/mensagens").get_json()
        self.assertEqual(detalhes["arquivo"]["nome_original"], "clientes.csv")

    def test_treinamento_e_previsao(self):
        self.assertEqual(self.enviar_base().status_code, 200)
        inicio = self.cliente.post("/treinar", json={"conversa_id": self.conversa, "alvo": "comprou"})
        self.assertEqual(inicio.status_code, 202)
        tarefa_id = inicio.get_json()["tarefa_id"]
        for _ in range(120):
            tarefa = self.cliente.get(f"/tarefas/{tarefa_id}").get_json()
            if tarefa["status"] in ("concluida", "falhou"): break
            time.sleep(.1)
        self.assertEqual(tarefa["status"], "concluida", tarefa.get("erro"))
        previsao = self.cliente.post("/prever", data={
            "conversa_id": str(self.conversa),
            "arquivo": (self.csv_treino(10), "novos.csv")
        }, content_type="multipart/form-data")
        self.assertEqual(previsao.status_code, 200, previsao.get_json())

    def test_rejeita_conversa_invalida(self):
        resposta = self.cliente.post("/upload", data={
            "conversa_id": "999999", "arquivo": (self.csv_treino(), "base.csv")
        }, content_type="multipart/form-data")
        self.assertEqual(resposta.status_code, 400)

    def test_saude_nao_expoe_chave(self):
        resposta = self.cliente.get("/saude")
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("api_key", resposta.get_data(as_text=True).lower())

    def test_cabecalhos_de_seguranca(self):
        resposta = self.cliente.get("/")
        self.assertEqual(resposta.headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", resposta.headers["Content-Security-Policy"])

    def test_chat_sem_chave_retorna_503(self):
        configuracao = modulo.settings
        modulo.settings = type(configuracao)(**{
            **configuracao.__dict__, "gemini_api_key": None
        })
        try:
            resposta = self.cliente.post("/perguntar", json={
                "conversa_id": self.conversa, "mensagem": "Olá"
            })
        finally:
            modulo.settings = configuracao
        self.assertEqual(resposta.status_code, 503)

    def test_rejeita_extensao_invalida(self):
        resposta = self.cliente.post("/upload", data={
            "conversa_id": str(self.conversa),
            "arquivo": (io.BytesIO(b"conteudo"), "dados.txt")
        }, content_type="multipart/form-data")
        self.assertEqual(resposta.status_code, 400)

    def test_rejeita_csv_vazio(self):
        resposta = self.cliente.post("/upload", data={
            "conversa_id": str(self.conversa),
            "arquivo": (io.BytesIO(b""), "vazio.csv")
        }, content_type="multipart/form-data")
        self.assertEqual(resposta.status_code, 400)

    def test_aceita_csv_cp1252_com_ponto_e_virgula(self):
        conteudo = "cidade;valor\nSão Paulo;10\nRecife;20\n".encode("cp1252")
        resposta = self.cliente.post("/upload", data={
            "conversa_id": str(self.conversa),
            "arquivo": (io.BytesIO(conteudo), "dados.csv")
        }, content_type="multipart/form-data")
        self.assertEqual(resposta.status_code, 200, resposta.get_json())
        self.assertEqual(resposta.get_json()["colunas"], ["cidade", "valor"])

    def test_previsao_rejeita_coluna_ausente(self):
        self.assertEqual(self.enviar_base().status_code, 200)
        inicio = self.cliente.post("/treinar", json={"conversa_id": self.conversa, "alvo": "comprou"})
        tarefa_id = inicio.get_json()["tarefa_id"]
        for _ in range(120):
            tarefa = self.cliente.get(f"/tarefas/{tarefa_id}").get_json()
            if tarefa["status"] in ("concluida", "falhou"):
                break
            time.sleep(.1)
        arquivo = io.BytesIO(b"idade\n30\n")
        resposta = self.cliente.post("/prever", data={
            "conversa_id": str(self.conversa), "arquivo": (arquivo, "novos.csv")
        }, content_type="multipart/form-data")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("Faltam colunas", resposta.get_json()["erro"])


if __name__ == "__main__":
    unittest.main()
