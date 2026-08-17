"""
O socket de comando: o vocabulário fechado e o transporte.

Dois grupos, separados de propósito. `executar()` é puro — bytes entram,
resposta sai — e é onde a lista fechada inteira se exercita sem abrir
socket nenhum. O que sobra para o grupo do transporte é só o transporte:
permissão, teto de mensagem, e o arquivo sumindo ao fechar.

NENHUM TESTE AQUI PODE ALCANÇAR O SOCKET REAL. O caminho passa pelo
`Fs.path()` como o resto do daemon, então `--root` o move junto — a mesma
proteção que o sysfs já tem. A constante `/run/kyber/control.sock` só é
usada pelo `__main__`.
"""

import json
import os
import socket
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path

from gameprofiled import config, control, score
from gameprofiled.fs import Fs

from . import fakefs


class Base(unittest.TestCase):
    # O dev box: intel_pstate ativo, onde `schedutil` não existe. É a
    # máquina que torna a recusa por disponibilidade observável.
    DISPONIVEIS = {
        "governor": ["powersave", "performance"],
        "gpuLevel": ["baixo", "auto", "alto"],
        "fpsLimit": [],          # sem canal com o compositor
        "priority": ["padrão", "alta"],
    }

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.raiz = Path(self.dir.name)
        self.fs = Fs(self.raiz)
        self.log = []
        self.alvo = self.raiz / "var/lib/kyber/profiles.json"
        self.alvo.parent.mkdir(parents=True, exist_ok=True)
        self.alvo.write_text(json.dumps({
            "_comment": ["chave que o daemon não conhece"],
            "curve": {"wattsIdle": 22, "wattsPerPoint": 7, "calibrated": False},
            "default": {"governor": "performance"},
            "games": {},
        }))
        self.config = config.Config(self.fs, log=self.log.append)
        self.servidor = control.Servidor(
            self.fs, self.config, self.DISPONIVEIS.get,
            caminho="/run/kyber/control.sock", log=self.log.append)

    def manda(self, **campos):
        campos.setdefault("v", control.VERSAO)
        return self.servidor.executar(json.dumps(campos).encode())

    def arquivo(self):
        return json.loads(self.alvo.read_text())


class TestVocabulario(Base):
    def test_set_profile_grava_o_titulo(self):
        r = self.manda(cmd="set-profile", appid=553850,
                       axes={"governor": "powersave", "gpuLevel": "baixo"})
        self.assertTrue(r["ok"])
        self.assertEqual(self.arquivo()["games"]["553850"],
                         {"governor": "powersave", "gpuLevel": "baixo"})

    def test_a_resposta_diz_gravado_e_nao_aplicado(self):
        # São afirmações diferentes: o socket sabe que escreveu o arquivo;
        # quem sabe o que a máquina fez é o state.json, um tick depois.
        r = self.manda(cmd="set-profile", appid=1, axes={"governor": "powersave"})
        self.assertIn("gravado", r["note"])
        self.assertIn("state.json", r["note"])

    def test_schedutil_num_intel_pstate_e_recusado_com_a_lista(self):
        # A recusa que a restrição 2 da arquitetura pede. O editor já risca
        # a opção, mas a leitura dele é tirada uma vez na montagem — e
        # interface não é fronteira.
        r = self.manda(cmd="set-profile", appid=553850,
                       axes={"governor": "schedutil"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "eixo_indisponivel")
        self.assertEqual(r["axis"], "governor")
        self.assertEqual(r["available"], ["powersave", "performance"])
        self.assertEqual(self.arquivo()["games"], {})

    def test_eixo_sem_nenhuma_opcao_aceita_com_aviso(self):
        # `available` vazio é "não sabe aplicar AGORA", e recusar por isso
        # transformaria sondagem falha em trabalho perdido. Pior: apagaria
        # o que a tela do grupo morto foi feita para mostrar.
        r = self.manda(cmd="set-profile", appid=553850, axes={"fpsLimit": "60"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["warnings"][0]["axis"], "fpsLimit")
        self.assertEqual(self.arquivo()["games"]["553850"], {"fpsLimit": "60"})

    def test_valor_fora_do_vocabulario_e_recusado(self):
        r = self.manda(cmd="set-profile", appid=1, axes={"governor": "turbo"})
        self.assertEqual(r["error"], "valor_fora_do_vocabulario")
        self.assertEqual(r["available"], score.options("governor"))

    def test_eixo_desconhecido_e_recusado_e_nao_descartado(self):
        # Descartar em silêncio é o que faz um cliente achar que gravou o
        # que não gravou.
        r = self.manda(cmd="set-profile", appid=1, axes={"overclock": "sim"})
        self.assertEqual(r["error"], "eixo_desconhecido")
        self.assertEqual(self.arquivo()["games"], {})

    def test_o_vocabulario_e_o_mesmo_do_score(self):
        # Uma segunda lista aqui seria a terceira fonte de verdade do
        # projeto, e a segunda já custou um NaN na régua.
        for eixo in score.AXES:
            for valor in score.options(eixo):
                self.assertIsNotNone(score.weight_of(eixo, valor))

    def test_appid_so_inteiro(self):
        for ruim in ("553850", 553850.0, True, 0, -1, None,
                     "../../etc/passwd", 2 ** 31):
            r = self.manda(cmd="set-profile", appid=ruim,
                           axes={"governor": "powersave"})
            self.assertEqual(r["error"], "appid_invalido", f"aceitou {ruim!r}")

    def test_versao_desconhecida_nao_vira_melhor_esforco(self):
        r = self.servidor.executar(json.dumps(
            {"v": 99, "cmd": "set-profile", "appid": 1,
             "axes": {"governor": "powersave"}}).encode())
        self.assertEqual(r["error"], "versao_desconhecida")

    def test_comando_fora_da_lista(self):
        for ruim in ("set-curve", "apply-now", "set-governor", None, 7):
            self.assertEqual(self.manda(cmd=ruim, appid=1)["error"],
                             "comando_desconhecido")

    def test_lixo_nao_derruba_nada(self):
        for ruim in (b"", b"{", b"[]", b"null", b'"oi"', b"\xff\xfe"):
            r = self.servidor.executar(ruim)
            self.assertFalse(r["ok"])
            self.assertEqual(r["error"], "mensagem_invalida")

    def test_axes_vazio_e_recusado(self):
        self.assertEqual(self.manda(cmd="set-profile", appid=1, axes={})["error"],
                         "mensagem_invalida")

    def test_set_substitui_a_entrada_em_vez_de_mesclar(self):
        self.manda(cmd="set-profile", appid=1,
                   axes={"governor": "powersave", "gpuLevel": "alto"})
        self.manda(cmd="set-profile", appid=1, axes={"gpuLevel": "baixo"})
        # Mesclar deixaria o governor antigo escondido embaixo, e "o que
        # está gravado" deixaria de ser o que o cliente mandou.
        self.assertEqual(self.arquivo()["games"]["1"], {"gpuLevel": "baixo"})

    def test_clear_profile_remove_e_e_idempotente(self):
        self.manda(cmd="set-profile", appid=1, axes={"governor": "powersave"})
        primeira = self.manda(cmd="clear-profile", appid=1)
        self.assertTrue(primeira["ok"])
        self.assertIn("removida", primeira["note"])
        self.assertEqual(self.arquivo()["games"], {})

        segunda = self.manda(cmd="clear-profile", appid=1)
        self.assertTrue(segunda["ok"])
        self.assertIn("já seguia o padrão", segunda["note"])

    def test_chaves_desconhecidas_sobrevivem_a_gravacao(self):
        # O `_comment` da semente é escrito para ser lido dentro do
        # arquivo, e uma versão futura pode pôr chaves que esta não
        # entende. Ler o documento inteiro e devolver o documento inteiro
        # é o que impede uma versão antiga de apagar as duas coisas.
        self.manda(cmd="set-profile", appid=1, axes={"governor": "powersave"})
        depois = self.arquivo()
        self.assertEqual(depois["_comment"], ["chave que o daemon não conhece"])
        self.assertEqual(depois["curve"]["wattsIdle"], 22)
        self.assertEqual(depois["default"], {"governor": "performance"})

    def test_teto_de_titulos(self):
        jogos = {str(i): {"governor": "powersave"}
                 for i in range(1, control.MAX_TITULOS + 1)}
        self.alvo.write_text(json.dumps({"games": jogos}))
        # Título que já existe continua gravável; é só o crescimento que
        # para, e o que ele protege é o /var de um console read-only.
        self.assertTrue(self.manda(cmd="set-profile", appid=1,
                                   axes={"governor": "performance"})["ok"])
        r = self.manda(cmd="set-profile", appid=999999,
                       axes={"governor": "performance"})
        self.assertEqual(r["error"], "limite_de_titulos")

    def test_arquivo_corrompido_nao_trava_o_editor_nem_some_com_o_que_havia(self):
        # Num console sem terminal, recusar gravar para sempre é beco sem
        # saída. Mas apagar em silêncio um arquivo de perfis que só perdeu
        # uma vírgula seria trocar problema visível por invisível.
        self.alvo.write_text('{"games": {"1": {"governor": "power')
        r = self.manda(cmd="set-profile", appid=2, axes={"governor": "powersave"})
        self.assertTrue(r["ok"])
        self.assertEqual(self.arquivo()["games"], {"2": {"governor": "powersave"}})
        guardado = self.alvo.parent / "profiles.json.corrompido"
        self.assertTrue(guardado.exists())
        self.assertIn("governor", guardado.read_text())
        self.assertTrue(any("ilegível" in l for l in self.log))


class TestTransporte(Base):
    """O transporte, com um cliente de verdade de um lado e o laço do
    daemon do outro.

    O cliente vai para uma thread e o `atender()` fica na principal,
    porque é essa a forma real: quem espera é o laço de publicação. Um
    teste que mandasse e lesse na mesma thread travaria os dois — o
    servidor só aceita quando o laço o chama."""

    def setUp(self):
        super().setUp()
        self.assertTrue(self.servidor.abrir())
        self.addCleanup(self.servidor.fechar)

    def _socket(self):
        return str(self.fs.path("/run/kyber/control.sock"))

    def conversa(self, bruto, espera=2.0):
        """Manda, deixa o laço atender, devolve a resposta (ou None).

        `bruto` vai como está, com a nova linha do protocolo incluída pelo
        chamador. O helper não a acrescenta de propósito: uma mensagem sem
        terminador é um caso de teste legítimo, e escondê-lo aqui faria a
        suíte provar um protocolo que ela mesma conserta."""
        saida = {}

        def cliente():
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(espera)
            try:
                s.connect(self._socket())
                s.sendall(bruto)
                resposta = b""
                while b"\n" not in resposta:
                    pedaco = s.recv(4096)
                    if not pedaco:
                        break
                    resposta += pedaco
                saida["resposta"] = json.loads(resposta) if resposta else None
            except (OSError, ValueError) as erro:
                saida["erro"] = erro
            finally:
                s.close()

        thread = threading.Thread(target=cliente)
        thread.start()
        fim = time.monotonic() + espera
        while thread.is_alive() and time.monotonic() < fim:
            self.servidor.atender(0.02)
        thread.join(espera)
        return saida.get("resposta")

    # ------------------------------------------------------------------
    def test_o_caminho_do_socket_mora_dentro_da_raiz(self):
        # A garantia que impede um teste de falar com o daemon da máquina:
        # o caminho passa pelo Fs, então o --root o move junto.
        caminho = self.fs.path("/run/kyber/control.sock")
        self.assertTrue(str(caminho).startswith(str(self.raiz)))
        self.assertTrue(caminho.is_socket())

    def test_ida_e_volta(self):
        r = self.conversa(json.dumps({
            "v": 1, "cmd": "set-profile", "appid": 553850,
            "axes": {"governor": "powersave"}}).encode() + b"\n")
        self.assertTrue(r["ok"])
        self.assertEqual(self.arquivo()["games"]["553850"],
                         {"governor": "powersave"})

    def test_a_recusa_volta_pelo_socket_com_a_razao(self):
        r = self.conversa(json.dumps({
            "v": 1, "cmd": "set-profile", "appid": 553850,
            "axes": {"governor": "schedutil"}}).encode() + b"\n")
        self.assertEqual(r["error"], "eixo_indisponivel")
        self.assertIn("performance", r["available"])
        self.assertEqual(self.arquivo()["games"], {})

    def test_duas_conversas_seguidas_na_mesma_rodada(self):
        # Conexão de uso único: a segunda não pode depender de a primeira
        # ter deixado alguma coisa aberta.
        self.conversa(json.dumps({"v": 1, "cmd": "set-profile", "appid": 1,
                                  "axes": {"governor": "powersave"}}).encode()
                      + b"\n")
        r = self.conversa(json.dumps({"v": 1, "cmd": "clear-profile",
                                      "appid": 1}).encode() + b"\n")
        self.assertTrue(r["ok"])
        self.assertEqual(self.arquivo()["games"], {})

    def test_sem_grupo_o_socket_fecha_em_vez_de_abrir(self):
        # Não há grupo kyber-api num Mac, e o chown para o root também não
        # é permitido. O que este teste fixa é que a falta do grupo NÃO
        # faz o socket cair para 0666 — falha fechada, não aberta.
        modo = stat.S_IMODE(os.stat(self._socket()).st_mode)
        self.assertEqual(modo & 0o007, 0, f"modo {modo:o} abre para outros")
        self.assertTrue(any("0600" in linha for linha in self.log))

    def test_mensagem_gigante_nao_vira_memoria_infinita(self):
        # A resposta pode não chegar: o servidor corta a leitura no teto e
        # fecha, e o cliente ainda está empurrando bytes. O que importa é
        # que ele recusou e não gravou — e isso o journal registra.
        self.conversa(b"x" * (control.MAX_MENSAGEM * 4) + b"\n", espera=1.0)
        self.assertTrue(any("RECUSADO mensagem_invalida" in l for l in self.log),
                        self.log)
        self.assertEqual(self.arquivo()["games"], {})

    def test_cliente_que_conecta_e_some_nao_prende_o_laco(self):
        # Cliente que abre e não fala é o que congelaria o `at`, e `at`
        # congelado é LEITURA PARADA num console vivo.
        mudo = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        mudo.connect(self._socket())
        self.addCleanup(mudo.close)
        inicio = time.monotonic()
        self.servidor.atender(0.02)
        self.assertLess(time.monotonic() - inicio, control.PRAZO_S * 4)

    def test_atender_sem_ninguem_na_fila_devolve_zero(self):
        self.assertEqual(self.servidor.atender(0.0), 0)

    def test_fechar_leva_o_arquivo_junto(self):
        self.servidor.fechar()
        self.assertFalse(self.fs.path("/run/kyber/control.sock").exists())


class TestDoSocketAoSysfs(unittest.TestCase):
    """A cadeia inteira: comando entra, ARQUIVO muda, tick seguinte aplica.

    É o teste que prova que não existe caminho paralelo. O servidor não
    conhece o ProfileManager e não fala com eixo nenhum — ele grava o
    arquivo, e o daemon descobre pelo mesmo mtime por onde descobre uma
    edição com o `vi`. Se algum dia alguém "otimizar" isso aplicando
    direto do handler, este teste continua passando e o de cima também;
    o que se perde é a propriedade, e é por isso que ela está escrita no
    topo do control.py e no README.
    """

    def setUp(self):
        from .test_state import Relogio
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.raiz = Path(self.dir.name)
        fakefs.intel_rx7600(self.raiz)
        fakefs.sessao_steam(self.raiz)
        self.log = []
        self.relogio = Relogio()

    def _daemon(self, *extra):
        from gameprofiled.__main__ import Daemon, parse_args
        from .test_axes import OpsFalso
        d = Daemon(parse_args(["--root", str(self.raiz), *extra]),
                   self.log.append, self.relogio, self.relogio)
        d.manager.ops = OpsFalso(self.raiz)
        d.manager.axes["priority"].ops = d.manager.ops
        self.addCleanup(d.shutdown)
        return d

    def _governor(self):
        return (self.raiz / "sys/devices/system/cpu/cpufreq/policy0"
                / "scaling_governor").read_text().strip()

    def _mandar(self, d, pedido, espera=2.0):
        saida = {}
        caminho = str(d.fs.path(d.opcoes.socket))

        def cliente():
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(espera)
            try:
                s.connect(caminho)
                s.sendall(json.dumps(pedido).encode() + b"\n")
                saida["resposta"] = json.loads(s.recv(4096))
            except (OSError, ValueError) as erro:
                saida["erro"] = erro
            finally:
                s.close()

        thread = threading.Thread(target=cliente)
        thread.start()
        fim = time.monotonic() + espera
        while thread.is_alive() and time.monotonic() < fim:
            d.control.atender(0.02)
        thread.join(espera)
        return saida.get("resposta")

    # ------------------------------------------------------------------
    def test_comando_no_socket_vira_escrita_em_sysfs_no_tick_seguinte(self):
        d = self._daemon()
        self.assertIsNotNone(d.control, "o daemon não abriu o socket")
        d.tick()
        self.assertEqual(self._governor(), "performance")

        resposta = self._mandar(d, {"v": 1, "cmd": "set-profile",
                                    "appid": 553850,
                                    "axes": {"governor": "powersave"}})
        self.assertTrue(resposta["ok"])
        # Gravou o arquivo e NADA mais: o sysfs só muda no próximo ciclo.
        self.assertEqual(self._governor(), "performance")

        self.relogio.avancar()
        d.tick()
        self.assertEqual(self._governor(), "powersave")
        eixo = json.loads((self.raiz / "run/kyber/state.json").read_text())
        self.assertEqual(eixo["profile"]["axes"]["governor"]["requested"],
                         "powersave")

    def test_clear_profile_devolve_o_titulo_ao_padrao(self):
        d = self._daemon()
        d.tick()
        self._mandar(d, {"v": 1, "cmd": "set-profile", "appid": 553850,
                         "axes": {"governor": "powersave"}})
        self.relogio.avancar()
        d.tick()
        self.assertEqual(self._governor(), "powersave")

        self._mandar(d, {"v": 1, "cmd": "clear-profile", "appid": 553850})
        self.relogio.avancar()
        d.tick()
        # O padrão embutido pede performance; sem entrada própria, o título
        # volta a segui-lo — e seguirá o padrão NOVO se a imagem mudar.
        self.assertEqual(self._governor(), "performance")

    def test_recusa_nao_muda_nada(self):
        d = self._daemon()
        d.tick()
        resposta = self._mandar(d, {"v": 1, "cmd": "set-profile",
                                    "appid": 553850,
                                    "axes": {"governor": "schedutil"}})
        self.assertEqual(resposta["error"], "eixo_indisponivel")
        self.relogio.avancar()
        d.tick()
        self.assertEqual(self._governor(), "performance")

    def test_no_socket_e_once_nao_escutam(self):
        self.assertIsNone(self._daemon("--no-socket").control)
        self.assertIsNone(self._daemon("--once").control)

    def test_a_espera_nunca_cede_o_instante_da_publicacao(self):
        """O laço cede tempo ao socket, nunca o horário da publicação.

        Duas coisas de uma vez: nenhuma fatia passa do teto — senão o
        SIGTERM ficaria preso até a próxima publicação, porque o `select`
        do Python é retomado depois de um sinal em vez de devolver — e
        nenhuma passa do que falta para publicar, porque `at` que atrasa é
        o que o launcher chama de LEITURA PARADA."""
        from gameprofiled.__main__ import FATIA_ESPERA_S

        class RelogioQueAnda:
            def __init__(self):
                self.agora = 0.0

            def __call__(self):
                self.agora += 0.1
                return self.agora

        d = self._daemon()
        fatias = []
        d.control.atender = fatias.append
        d.relogio = RelogioQueAnda()

        self.assertFalse(d.esperar(1.0, threading.Event()))
        self.assertTrue(fatias)
        self.assertLessEqual(max(fatias), FATIA_ESPERA_S)
        # A última fatia é o que sobrava, não o teto.
        self.assertLessEqual(fatias[-1], 0.1 + 1e-9)

    def test_pedido_de_parada_nao_espera_o_alvo(self):
        d = self._daemon()
        parar = threading.Event()
        parar.set()
        inicio = time.monotonic()
        self.assertTrue(d.esperar(self.relogio() + 3600, parar))
        self.assertLess(time.monotonic() - inicio, 0.5)
