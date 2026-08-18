"""
O kyber-power: os quatro verbos de energia.

Roda inteiro num Mac e NÃO desliga o Mac: o servidor recebe o executor
por injeção, e a suíte injeta um que só anota o que teria rodado. É a
mesma disciplina do `--no-apply` do daemon — a peça que age tem que ter
um modo em que se observa o que ela faria.

O que estes testes fixam, e por que cada um:

  · a lista de verbos é FECHADA, e verbo fora dela é recusado COM a
    lista. Recusar sem dizer o que existe faz um cliente errado
    continuar errado;
  · rota errada e verbo errado são respostas DIFERENTES — 404 e 400. As
    duas juntas fariam "não é aqui" e "isso não existe" virarem a mesma
    tela;
  · nenhum campo do corpo entra na linha de comando. O comando é
    constante da tabela, e o teste prova isso mandando um corpo hostil;
  · falha do systemctl vira 502 com o motivo VERBATIM, e não 500. O erro
    não é deste processo, e a tela precisa mostrar "Interactive
    authentication required" em vez de "não deu";
  · a origem é exata e o preflight existe — mesmo par de propriedades do
    kyber-api, e pelo mesmo motivo mecânico.
"""

import json
import threading
import unittest
import urllib.error
import urllib.request

import kyberpower.__main__ as power
from kyberpower.__main__ import Servidor

ORIGEM = "http://127.0.0.1:8787"


class Executor:
    """O que teria rodado, e o que o systemctl teria respondido."""

    def __init__(self, falha=None):
        self.comandos = []
        self.falha = falha

    def __call__(self, comando):
        self.comandos.append(tuple(comando))
        return self.falha


class Base(unittest.TestCase):
    def setUp(self):
        original = power.log
        power.log = lambda *_: None
        self.addCleanup(lambda: setattr(power, "log", original))

        self.executor = Executor()
        # Porta efêmera: porta fixa num teste é como se descobre, no pior
        # momento, que a suíte não roda em paralelo.
        self.http = Servidor(("127.0.0.1", 0), ORIGEM, self.executor)
        self.addCleanup(self.http.server_close)
        self.porta = self.http.server_address[1]
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.shutdown)

    def pedir(self, metodo, caminho, corpo=None, tipo="application/json",
              cabecalhos=None):
        dados = json.dumps(corpo).encode() if corpo is not None else b""
        pedido = urllib.request.Request(
            f"http://127.0.0.1:{self.porta}{caminho}",
            data=dados if metodo != "OPTIONS" else None, method=metodo)
        if tipo:
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


class TestVerbos(Base):
    def test_os_quatro_verbos_rodam_o_comando_da_tabela(self):
        esperado = {
            "poweroff": ("systemctl", "poweroff"),
            "reboot": ("systemctl", "reboot"),
            "suspend": ("systemctl", "suspend"),
            "desktop": ("systemctl", "start", "kyber-session-desktop.service"),
        }
        for verbo, comando in esperado.items():
            with self.subTest(verbo=verbo):
                self.executor.comandos.clear()
                resposta = self.pedir("POST", f"/power/{verbo}", {})
                self.assertEqual(resposta[0], 200)
                corpo = self.json_de(resposta)
                self.assertTrue(corpo["ok"])
                self.assertEqual(corpo["cmd"], verbo)
                self.assertEqual(self.executor.comandos, [comando])

    def test_a_lista_e_fechada_e_a_recusa_traz_a_lista(self):
        resposta = self.pedir("POST", "/power/halt", {})
        self.assertEqual(resposta[0], 400)
        corpo = self.json_de(resposta)
        self.assertEqual(corpo["error"], "verbo_desconhecido")
        self.assertEqual(sorted(corpo["verbs"]),
                         ["desktop", "poweroff", "reboot", "suspend"])
        self.assertEqual(self.executor.comandos, [])

    def test_rota_errada_e_404_e_verbo_errado_e_400(self):
        # As duas dizem coisas diferentes: "não é aqui" e "é aqui e isso
        # não existe". Uma resposta só para os dois casos faria a tela
        # tratar erro de rota como vocabulário.
        self.assertEqual(self.pedir("POST", "/poweroff", {})[0], 404)
        self.assertEqual(self.pedir("POST", "/power/", {})[0], 404)
        self.assertEqual(self.pedir("POST", "/power/x/y", {})[0], 404)
        self.assertEqual(self.pedir("POST", "/power/halt", {})[0], 400)

    def test_nada_do_corpo_entra_na_linha_de_comando(self):
        # O corpo existe só para o preflight acontecer. Se um dia alguém
        # começar a ler campo daqui, este teste é quem avisa.
        self.pedir("POST", "/power/suspend",
                   {"cmd": "rm -rf /", "args": ["--now"], "verbo": "poweroff"})
        self.assertEqual(self.executor.comandos, [("systemctl", "suspend")])

    def test_verbo_com_travessura_de_caminho_nao_vira_comando(self):
        for caminho in ("/power/..%2Fpoweroff", "/power/suspend;poweroff",
                        "/power/systemctl"):
            with self.subTest(caminho=caminho):
                self.executor.comandos.clear()
                self.assertEqual(self.pedir("POST", caminho, {})[0], 400)
                self.assertEqual(self.executor.comandos, [])


class TestFalha(Base):
    def test_recusa_do_systemctl_vira_502_com_o_motivo_verbatim(self):
        self.executor.falha = ("comando_falhou",
                               "Interactive authentication required.")
        resposta = self.pedir("POST", "/power/poweroff", {})
        # 502 e não 500: o erro é do lado que decide, não deste processo.
        self.assertEqual(resposta[0], 502)
        corpo = self.json_de(resposta)
        self.assertFalse(corpo["ok"])
        self.assertEqual(corpo["error"], "comando_falhou")
        self.assertEqual(corpo["note"], "Interactive authentication required.")
        self.assertEqual(corpo["cmd"], "poweroff")

    def test_executar_de_verdade_relata_binario_ausente(self):
        # O executor real, sem servidor no meio. Um comando que não existe
        # é o caso que separa "recusou" de "nem estava lá".
        falha = power.executar(("kyber-nao-existe-mesmo",))
        self.assertEqual(falha[0], "comando_ausente")

    def test_executar_de_verdade_pega_o_stderr_do_comando(self):
        falha = power.executar(
            ("sh", "-c", "echo 'motivo de verdade' >&2; exit 3"))
        self.assertEqual(falha, ("comando_falhou", "motivo de verdade"))

    def test_executar_de_verdade_devolve_none_no_sucesso(self):
        self.assertIsNone(power.executar(("sh", "-c", "exit 0")))

    def test_executar_de_verdade_tem_prazo(self):
        falha = power.executar(("sh", "-c", "sleep 5"), prazo=0.2)
        self.assertEqual(falha[0], "comando_travou")


class TestOrigem(Base):
    def test_a_origem_volta_exata_e_nunca_asterisco(self):
        resposta = self.pedir("POST", "/power/suspend", {})
        self.assertEqual(resposta[1]["Access-Control-Allow-Origin"], ORIGEM)
        self.assertEqual(resposta[1]["Vary"], "Origin")

    def test_o_preflight_responde_e_lista_so_o_que_existe(self):
        resposta = self.pedir("OPTIONS", "/power/poweroff", tipo=None)
        self.assertEqual(resposta[0], 204)
        self.assertEqual(resposta[1]["Access-Control-Allow-Origin"], ORIGEM)
        self.assertEqual(resposta[1]["Access-Control-Allow-Methods"],
                         "POST, OPTIONS")
        self.assertEqual(self.executor.comandos, [])

    def test_sem_json_no_content_type_e_415(self):
        # Exigir application/json é o que força o preflight, que é o que
        # dá à origem exata a chance de reprovar.
        resposta = self.pedir("POST", "/power/poweroff", {},
                              tipo="text/plain")
        self.assertEqual(resposta[0], 415)
        self.assertEqual(self.executor.comandos, [])


if __name__ == "__main__":
    unittest.main()
