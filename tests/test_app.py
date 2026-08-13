Exit code: 0
Wall time: 0.3 seconds
Output:
import io
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

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
        chat = MagicMock(); chat.send_message.return_value.text = "Resposta salva"
        with patch.object(modulo.client.chats, "create", return_value=chat):
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


if __name__ == "__main__":
    unittest.main()

