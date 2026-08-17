"""
O kyber-api: HTTP de um lado, socket do outro.

Roda inteiro num Mac, com as duas peças de verdade — o servidor de
comando do daemon e o servidor HTTP — ligadas uma na outra por um socket
dentro de um diretório temporário. O que NÃO tem aqui é daemon: quem
aplica perfil é outro processo, e esta camada não sabe disso.

O que estes testes fixam, e que nenhuma outra suíte pega:

  · a origem é EXATA e o preflight existe
  · exigir application/json, que é o que força o preflight
  · daemon fora do ar vira 503 com motivo, e não 500 nem silêncio
  · o kyber-api não conhece o vocabulário: o `axes` vai verbatim e quem
    recusa é o outro lado
"""

import json
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from gameprofiled import config, control
from gameprofiled.fs import Fs

import kyberapi.__main__ as api
from kyberapi.__main__ import Servidor as ServidorHTTP

ORIGEM = "http://127.0.0.1:8787"


class Base(unittest.TestCase):
    DISPONIVEIS = {"governor": ["powersave", "performance"],
                   "gpuLevel": ["baixo", "auto", "alto"],
                   "fpsLimit": [], "priority": ["padrão", "alta"]}

    def setUp(self):
        # O log do kyber-api vai para stderr, que é onde o journal o quer
        # e onde a suíte não o quer: 170 testes com linha de HTTP no meio
        # escondem a falha de verdade.
        original = api.log
        api.log = self.registrar
        self.addCleanup(lambda: setattr(api, "log", original))
        self.linhas = []

        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.raiz = Path(self.dir.name)
        self.fs = Fs(self.raiz)
        self.log = []
        self.alvo = self.raiz / "var/lib/kyber/profiles.json"
        self.alvo.parent.mkdir(parents=True, exist_ok=True)
        self.alvo.write_text(json.dumps({"default": {"governor": "performance"},
                                         "games": {}}))
        self.config = config.Config(self.fs, log=self.log.append)

        self.socket_daemon = str(self.raiz / "control.sock")
        self.control = control.Servidor(
            self.fs, self.config, self.DISPONIVEIS.get,
            caminho="/control.sock", log=self.log.append)

        # O servidor HTTP em porta efêmera: porta fixa num teste é como se
        # descobre, no pior momento, que a suíte não roda em paralelo.
        self.http = ServidorHTTP(("127.0.0.1", 0), self.socket_daemon, ORIGEM)
        self.addCleanup(self.http.server_close)
        self.porta = self.http.server_address[1]
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.shutdown)

    def ligar_daemon(self):
        """Sobe o lado do socket e o mantém atendendo numa thread.

        O laço de publicação do daemon é quem chama `atender()` de
        verdade; aqui uma thread faz o papel dele."""
        self.assertTrue(self.control.abrir())
        self.addCleanup(self.control.fechar)
        vivo = threading.Event()
        vivo.set()
        self.addCleanup(vivo.clear)

        def bombear():
            while vivo.is_set():
                try:
                    self.control.atender(0.02)
                except OSError:
                    return
        threading.Thread(target=bombear, daemon=True).start()

    def registrar(self, mensagem):
        self.linhas.append(mensagem)

    # ------------------------------------------------------------------
    def pedir(self, metodo, caminho, corpo=None, tipo="application/json",
              cabecalhos=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        pedido = urllib.request.Request(
            f"http://127.0.0.1:{self.porta}{caminho}", data=dados, method=metodo)
        if dados is not None and tipo:
            pedido.add_header("Content-Type", tipo)
        pedido.add_header("Origin", ORIGEM)
        for chave, valor in (cabecalhos or {}).items():
            pedido.add_header(chave, valor)
        try:
            with urllib.request.urlopen(pedido, timeout=5) as resposta:
                return resposta.status, dict(resposta.headers), resposta.read()
        except urllib.error.HTTPError as erro:
            with erro:
                return erro.code, dict(erro.headers), erro.read()

    def json_de(self, resposta):
        return json.loads(resposta[2])

    def arquivo(self):
        return json.loads(self.alvo.read_text())


class TestEscrita(Base):
    def setUp(self):
        super().setUp()
        self.ligar_daemon()

    def test_post_valido_grava_e_devolve_200(self):
        resposta = self.pedir("POST", "/profile/553850",
                              {"axes": {"governor": "powersave"}})
        self.assertEqual(resposta[0], 200)
        self.assertTrue(self.json_de(resposta)["ok"])
        self.assertEqual(self.arquivo()["games"]["553850"],
                         {"governor": "powersave"})

    def test_recusa_do_daemon_chega_como_400_com_a_razao(self):
        # O kyber-api não sabe o que é schedutil. Quem recusa é o lado
        # root, e a razão atravessa inteira.
        resposta = self.pedir("POST", "/profile/553850",
                              {"axes": {"governor": "schedutil"}})
        self.assertEqual(resposta[0], 400)
        corpo = self.json_de(resposta)
        self.assertEqual(corpo["error"], "eixo_indisponivel")
        self.assertEqual(corpo["available"], ["powersave", "performance"])
        self.assertEqual(self.arquivo()["games"], {})

    def test_delete_limpa_o_titulo(self):
        self.pedir("POST", "/profile/1", {"axes": {"governor": "powersave"}})
        resposta = self.pedir("DELETE", "/profile/1")
        self.assertEqual(resposta[0], 200)
        self.assertEqual(self.arquivo()["games"], {})

    def test_appid_que_nao_e_numero_e_recusado_pelo_DAEMON(self):
        # A regra do appid mora num lugar só. Esta camada empurra o que
        # veio na rota e deixa o outro lado responder.
        resposta = self.pedir("POST", "/profile/..%2Fetc%2Fpasswd",
                              {"axes": {"governor": "powersave"}})
        self.assertEqual(resposta[0], 400)
        self.assertEqual(self.json_de(resposta)["error"], "appid_invalido")

    def test_axes_vai_verbatim(self):
        # Nenhuma filtragem aqui: a segunda lista de valores válidos é o
        # que este processo existe para não ter.
        resposta = self.pedir("POST", "/profile/1", {"axes": {"overclock": 9}})
        self.assertEqual(self.json_de(resposta)["error"], "eixo_desconhecido")


class TestOrigem(Base):
    def setUp(self):
        super().setUp()
        self.ligar_daemon()

    def test_preflight_responde_com_a_origem_exata(self):
        status, cabecalhos, _ = self.pedir("OPTIONS", "/profile/1")
        self.assertEqual(status, 204)
        self.assertEqual(cabecalhos["Access-Control-Allow-Origin"], ORIGEM)
        self.assertIn("POST", cabecalhos["Access-Control-Allow-Methods"])
        self.assertIn("Content-Type", cabecalhos["Access-Control-Allow-Headers"])

    def test_a_origem_nunca_e_asterisco(self):
        # `*` deixaria qualquer página do mundo falar com esta porta no
        # dia em que o console abrir um navegador comum.
        for metodo, caminho in (("OPTIONS", "/profile/1"), ("DELETE", "/profile/1")):
            _, cabecalhos, _ = self.pedir(metodo, caminho)
            self.assertEqual(cabecalhos["Access-Control-Allow-Origin"], ORIGEM)

    def test_sem_json_no_content_type_e_recusado(self):
        # É esta exigência que força o preflight numa requisição de outra
        # origem — e o preflight reprova na origem exata.
        resposta = self.pedir("POST", "/profile/1",
                              {"axes": {"governor": "powersave"}},
                              tipo="text/plain")
        self.assertEqual(resposta[0], 415)
        self.assertEqual(self.arquivo()["games"], {})

    def test_rota_desconhecida(self):
        for caminho in ("/", "/profile", "/profile/1/extra", "/state.json"):
            resposta = self.pedir("POST", caminho, {"axes": {}})
            self.assertEqual(resposta[0], 404, caminho)


class TestDaemonForaDoAr(Base):
    def test_sem_socket_responde_503_e_diz_por_que(self):
        # 503 e não 500: o launcher precisa distinguir "o daemon recusou"
        # de "o daemon não estava lá". São telas diferentes.
        resposta = self.pedir("POST", "/profile/1",
                              {"axes": {"governor": "powersave"}})
        self.assertEqual(resposta[0], 503)
        corpo = self.json_de(resposta)
        self.assertEqual(corpo["error"], "daemon_inalcancavel")
        self.assertIn("FileNotFoundError", corpo["note"])
        # O journal tem que dizer QUAL camada respondeu: é a única pista
        # que separa "o daemon recusou" de "o daemon não estava lá".
        self.assertTrue(any("inalcançável" in l for l in self.linhas), self.linhas)

    def test_a_resposta_de_erro_tambem_leva_cors(self):
        # Sem o cabeçalho, o navegador esconde a resposta e o launcher
        # não teria como mostrar o motivo da falha.
        _, cabecalhos, _ = self.pedir("POST", "/profile/1",
                                      {"axes": {"governor": "powersave"}})
        self.assertEqual(cabecalhos["Access-Control-Allow-Origin"], ORIGEM)


class TestCorpo(Base):
    def setUp(self):
        super().setUp()
        self.ligar_daemon()

    def test_corpo_maior_que_o_teto(self):
        resposta = self.pedir("POST", "/profile/1",
                              {"axes": {"governor": "x" * control.MAX_MENSAGEM}})
        self.assertEqual(resposta[0], 400)
        self.assertEqual(self.json_de(resposta)["error"], "corpo_invalido")

    def test_corpo_que_nao_e_json(self):
        pedido = urllib.request.Request(
            f"http://127.0.0.1:{self.porta}/profile/1", data=b"{nao json",
            method="POST")
        pedido.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(pedido, timeout=5) as r:
                status, corpo = r.status, r.read()
        except urllib.error.HTTPError as erro:
            with erro:
                status, corpo = erro.code, erro.read()
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(corpo)["error"], "corpo_invalido")
