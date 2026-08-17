"""
Montagem e publicação do state.json.

Dois testes aqui valem mais que o resto: o da escrita atômica e o da fase
travada. Os dois protegem contra falhas que não produzem erro nenhum — um
devolve JSON truncado ao launcher, o outro faz o console saudável se
declarar parado.
"""

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from gameprofiled import config, games, profile, score, sensors, state
from gameprofiled.__main__ import Daemon, parse_args
from gameprofiled.fs import Fs

from . import fakefs
from .test_axes import OpsFalso
from .test_session import RunnerFalso


class Relogio:
    """Relógio de mentira. O daemon publica em X,5 s de tempo de parede, e
    testar isso com o relógio de verdade seria esperar de verdade.

    Serve de parede E de cronômetro: avançar um move os dois, que é o
    comportamento das duas fontes reais quando ninguém mexe no horário."""

    def __init__(self, inicio=1786969940.0, passo=1.0):
        self.agora = inicio
        self.passo = passo

    def __call__(self):
        return self.agora

    def avancar(self, quanto=None):
        self.agora += self.passo if quanto is None else quanto
        return self.agora


class TestFaseTravada(unittest.TestCase):
    def test_publicacao_ancora_no_meio_do_segundo(self):
        self.assertEqual(state.next_publish(10.0), 10.5)
        self.assertEqual(state.next_publish(10.4), 10.5)
        self.assertEqual(state.next_publish(10.5), 11.5)
        self.assertEqual(state.next_publish(10.99), 11.5)

    def test_duas_publicacoes_nunca_caem_no_mesmo_segundo_inteiro(self):
        # Esta é a armadilha do If-Modified-Since: o darkhttpd compara data
        # de modificação como string, com um segundo de granularidade. Duas
        # escritas no mesmo segundo fazem o cliente receber 304, servir o
        # corpo em cache, ver o mesmo `at` e declarar LEITURA PARADA.
        instante, segundos = 0.0, []
        for _ in range(20):
            instante = state.next_publish(instante)
            segundos.append(int(instante))
            instante += 0.37  # atraso de escalonamento entre uma e outra
        self.assertEqual(len(segundos), len(set(segundos)))


class TestEscritaAtomica(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.raiz = Path(self.dir.name)
        self.fs = Fs(self.raiz)
        self.pub = state.Publisher(self.fs, "/run/kyber/state.json")

    def test_o_arquivo_final_e_sempre_json_completo(self):
        self.pub.publish({"a": 1})
        destino = self.raiz / "run/kyber/state.json"
        self.assertEqual(json.loads(destino.read_text()), {"a": 1})

    def test_o_temporario_nao_sobra(self):
        self.pub.publish({"a": 1})
        self.assertFalse((self.raiz / "run/kyber/state.json.tmp").exists())

    def test_quem_ja_abriu_le_o_arquivo_antigo_inteiro(self):
        # É o que o rename(2) garante e o que o darkhttpd depende: ele abre
        # o inode e faz sendfile sem lock. Sem a troca atômica, uma leitura
        # no meio da escrita devolve JSON truncado.
        self.pub.publish({"versao": "antiga", "enchimento": "x" * 4096})
        destino = self.raiz / "run/kyber/state.json"
        with open(destino) as aberto:
            self.pub.publish({"versao": "nova"})
            self.assertEqual(json.loads(aberto.read())["versao"], "antiga")
        self.assertEqual(json.loads(destino.read_text())["versao"], "nova")

    def test_o_arquivo_e_legivel_por_nobody(self):
        # Quem serve é o darkhttpd rodando como nobody.
        self.pub.publish({"a": 1})
        modo = (self.raiz / "run/kyber/state.json").stat().st_mode & 0o777
        self.assertEqual(modo, 0o644)

    def test_remover_apaga_os_dois(self):
        self.pub.publish({"a": 1})
        self.pub.remove()
        self.assertFalse((self.raiz / "run/kyber/state.json").exists())


class TestFonteDeWatts(unittest.TestCase):
    def test_curva_nao_calibrada_diz_que_e_chute(self):
        fonte = state.watts_source(
            {"wattsIdle": 22, "wattsPerPoint": 7, "calibrated": False}, 64, None)
        self.assertEqual(fonte["kind"], "estimated")
        self.assertIn("NÃO calibrada", fonte["note"])
        self.assertIn("chute do protótipo", fonte["note"])

    def test_a_soma_medida_aparece_ao_lado_do_estimado(self):
        # O pedido explícito: não dá para se acostumar com um número que
        # ninguém conferiu se o número conferível está do lado.
        fonte = state.watts_source(
            {"wattsIdle": 22, "wattsPerPoint": 7, "calibrated": False}, 64, 135.2)
        self.assertIn("64 W", fonte["note"])
        self.assertIn("135.2 W", fonte["note"])
        self.assertIn("perda da fonte", fonte["note"])

    def test_calibrada_continua_estimativa(self):
        # A calibração melhora a CONSTANTE; o valor publicado continua
        # saindo de um modelo, e nenhum sensor mede o console.
        fonte = state.watts_source(
            {"wattsIdle": 19, "wattsPerPoint": 6, "calibrated": True}, 55, None)
        self.assertEqual(fonte["kind"], "estimated")
        self.assertIn("calibrada", fonte["note"])


class DaemonBase(unittest.TestCase):
    """Montagem comum. Sem caso de teste próprio de propósito: herdar a
    suíte inteira entre fixtures diferentes faria as asserções do dev box
    rodarem contra o console, onde o governor de partida é outro."""

    montar = staticmethod(fakefs.intel_rx7600)

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.raiz = Path(self.dir.name)
        self.montar(self.raiz)
        self.log = []
        self.relogio = Relogio()

    runner = None

    def daemon(self, *extra):
        # `--no-socket` por padrão: abrir um socket de verdade é efeito
        # colateral que nenhum destes testes pediu, e o transporte tem
        # suíte própria em test_control.py.
        opcoes = parse_args(["--root", str(self.raiz), "--no-socket", *extra])
        d = Daemon(opcoes, self.log.append, self.relogio, self.relogio,
                   runner=self.runner)
        d.manager.ops = OpsFalso(self.raiz)
        d.manager.axes["priority"].ops = d.manager.ops
        return d

    def publicado(self):
        return json.loads((self.raiz / "run/kyber/state.json").read_text())

    def fs_read(self, rel):
        return (self.raiz / rel).read_text().strip()

    def governor(self):
        return self.fs_read("sys/devices/system/cpu/cpufreq/policy0/scaling_governor")


class TestDaemonDevBox(DaemonBase):
    """i5-13400F + RX 7600. intel_pstate ativo, sensores completos."""

    montar = staticmethod(fakefs.intel_rx7600)

    def test_repouso_publica_medicao_e_nao_aplica_nada(self):
        d = self.daemon()
        d.tick()
        doc = self.publicado()

        self.assertEqual(doc["schema"], 1)
        self.assertEqual(doc["cpuTemp"], 61)
        self.assertEqual(doc["gpuTemp"], 68)
        self.assertEqual(doc["gpuWatts"], 96.8)
        self.assertIsNone(doc["runningGame"])
        self.assertEqual(doc["profile"]["applies"], "idle")
        self.assertEqual(doc["profile"]["axes"]["governor"]["state"], "observed")
        # Sem jogo o daemon não escreve em sysfs.
        self.assertEqual(self.governor(), "powersave")

    def test_ausencia_e_null_e_se_explica(self):
        d = self.daemon()
        # A primeira leitura do contador de energia é vazia por construção.
        d.tick()
        doc = self.publicado()
        self.assertIsNone(doc["cpuWatts"])
        self.assertIsNone(doc["fps"])
        self.assertEqual(doc["sources"]["fps"]["kind"], "absent")
        self.assertIn("gamescope", doc["sources"]["fps"]["note"])

    def test_rapl_reporta_a_partir_da_segunda_leitura(self):
        d = self.daemon()
        d.tick()
        self.relogio.avancar()
        energia = self.raiz / "sys/class/powercap/intel-rapl:0/energy_uj"
        energia.write_text(str(502_113_884_512 + 38_400_000) + "\n")
        d.tick()
        self.assertEqual(self.publicado()["cpuWatts"], 38.4)

    def test_jogo_aplica_perfil_e_publica_por_eixo(self):
        fakefs.sessao_steam(self.raiz)
        d = self.daemon()
        d.tick()
        doc = self.publicado()

        self.assertEqual(doc["runningGame"]["appid"], 553850)
        eixos = doc["profile"]["axes"]
        self.assertEqual(eixos["governor"]["state"], "applied")
        self.assertEqual(eixos["governor"]["current"], "performance")
        # O achado que obriga o launcher a desabilitar schedutil.
        self.assertEqual(eixos["governor"]["available"], ["powersave", "performance"])
        self.assertEqual(eixos["fpsLimit"]["state"], "unsupported")
        self.assertEqual(eixos["fpsLimit"]["available"], [])
        self.assertEqual(eixos["priority"]["state"], "applied")

    def test_intensidade_descreve_o_que_ficou_aplicado(self):
        fakefs.sessao_steam(self.raiz)
        d = self.daemon()
        d.tick()
        doc = self.publicado()
        # performance (2) + auto (1) + fpsLimit não aplicado (0) + alta (1).
        self.assertEqual(doc["intensity"], 0.5)
        self.assertEqual(doc["watts"], 22 + 4 * 7)
        self.assertEqual(doc["wattsIdle"], 22)
        self.assertEqual(doc["wattsPerPoint"], 7)

    def test_saida_do_jogo_restaura_a_maquina(self):
        fakefs.sessao_steam(self.raiz)
        d = self.daemon()
        d.tick()
        self.assertEqual(self.governor(), "performance")

        for pid in (1200, 1201, 1202):
            (self.raiz / "proc" / str(pid) / "cgroup").unlink()
            (self.raiz / "proc" / str(pid) / "environ").unlink(missing_ok=True)
            (self.raiz / "proc" / str(pid) / "cmdline").unlink(missing_ok=True)
        self.relogio.avancar()
        d.tick()

        self.assertEqual(self.governor(), "powersave")
        self.assertIsNone(self.publicado()["runningGame"])

    def test_perfil_editado_no_disco_chega_ao_state_json_no_tick_seguinte(self):
        """O laço inteiro, que é o caminho que o editor de perfil usa.

        Ele grava o arquivo; o daemon nota pelo tick seguinte, reaplica e
        publica. Não há segundo caminho, e é isso que faz `vi` e a tela do
        console valerem exatamente o mesmo."""
        fakefs.sessao_steam(self.raiz)
        alvo = self.raiz / "var/lib/kyber/profiles.json"
        alvo.parent.mkdir(parents=True, exist_ok=True)

        def gravar(jogos):
            temporario = alvo.parent / (alvo.name + ".tmp")
            temporario.write_text(json.dumps({
                "default": {"governor": "performance", "gpuLevel": "alto"},
                "games": jogos,
            }))
            os.replace(temporario, alvo)

        gravar({})
        d = self.daemon()
        d.tick()
        self.assertEqual(self.governor(), "performance")

        gravar({"553850": {"governor": "powersave"}})
        self.relogio.avancar()
        d.tick()

        self.assertEqual(self.governor(), "powersave")
        eixo = self.publicado()["profile"]["axes"]["governor"]
        self.assertEqual((eixo["requested"], eixo["current"]),
                         ("powersave", "powersave"))

    def test_at_avanca_a_cada_publicacao(self):
        # É o que o vigia do launcher compara para saber se a medição
        # parou. Carimbo repetido em daemon vivo seria falso positivo.
        d = self.daemon()
        d.tick()
        primeiro = self.publicado()["at"]
        self.relogio.avancar()
        d.tick()
        self.assertGreater(self.publicado()["at"], primeiro)

    def test_intervalo_abaixo_de_um_segundo_e_elevado(self):
        d = self.daemon("--interval", "0.2")
        self.assertEqual(d.interval, 1.0)
        self.assertTrue(any("304" in linha for linha in self.log))

    def test_no_apply_detecta_o_jogo_e_nao_escreve(self):
        fakefs.sessao_steam(self.raiz)
        d = self.daemon("--no-apply")
        d.tick()
        doc = self.publicado()
        self.assertEqual(doc["runningGame"]["appid"], 553850)
        eixos = doc["profile"]["axes"]
        self.assertEqual(eixos["governor"]["requested"], "performance")
        self.assertEqual(eixos["governor"]["state"], "observed")
        self.assertEqual(self.governor(), "powersave")

    def test_shutdown_restaura_e_apaga_o_arquivo(self):
        fakefs.sessao_steam(self.raiz)
        d = self.daemon()
        d.tick()
        d.shutdown()
        self.assertEqual(self.governor(), "powersave")
        # Estado antigo no disco faria o launcher ler LEITURA PARADA de um
        # daemon que não existe mais. SEM LEITURA é o correto.
        self.assertFalse((self.raiz / "run/kyber/state.json").exists())

    def test_sensor_que_some_dispara_redescoberta(self):
        d = self.daemon()
        d.tick()
        self.assertEqual(self.publicado()["gpuTemp"], 68)

        # O sensor de borda sumiu. A redescoberta tem que ACHAR OUTRO, não
        # ficar presa num caminho morto: junction é a segunda preferência.
        hwmon = self.raiz / "sys/class/drm/card1/device/hwmon/hwmon2"
        (hwmon / "temp1_input").unlink()
        for _ in range(4):
            self.relogio.avancar()
            d.tick()
        self.assertTrue(any("redescobrindo" in linha for linha in self.log))
        doc = self.publicado()
        self.assertEqual(doc["gpuTemp"], 88)
        self.assertEqual(doc["sources"]["gpuTemp"]["label"], "junction")

    def test_gpu_que_some_inteira_vira_ausencia(self):
        d = self.daemon()
        d.tick()
        hwmon = self.raiz / "sys/class/drm/card1/device/hwmon/hwmon2"
        for entrada in hwmon.glob("temp*_input"):
            entrada.unlink()
        for _ in range(4):
            self.relogio.avancar()
            d.tick()
        doc = self.publicado()
        self.assertIsNone(doc["gpuTemp"])
        self.assertEqual(doc["sources"]["gpuTemp"]["kind"], "absent")

    def test_a_comparacao_de_watts_vai_para_o_log(self):
        d = self.daemon()
        d.tick()
        self.relogio.avancar()
        (self.raiz / "sys/class/powercap/intel-rapl:0/energy_uj").write_text(
            str(502_113_884_512 + 38_400_000) + "\n")
        d.tick()
        comparacoes = [l for l in self.log if l.startswith("watts")]
        self.assertEqual(len(comparacoes), 1)
        self.assertIn("135.2 W medidos", comparacoes[0])

    def test_laco_para_no_evento(self):
        d = self.daemon("--once")
        parar = threading.Event()
        d.relogio = self.relogio
        d.run(parar)
        self.assertTrue((self.raiz / "run/kyber/state.json").exists())


class TestDaemonConsole(DaemonBase):
    """Ryzen 5 5700G + Vega 8. acpi-cpufreq, e a iGPU sem sensor próprio."""

    montar = staticmethod(fakefs.ryzen_5700g)

    def test_gpu_sem_temperatura_publica_null_com_motivo(self):
        d = self.daemon()
        d.tick()
        doc = self.publicado()
        self.assertIsNone(doc["gpuTemp"])
        self.assertEqual(doc["sources"]["gpuTemp"]["kind"], "absent")
        self.assertIn("die com a CPU", doc["sources"]["gpuTemp"]["note"])
        # E a CPU continua sendo medida: uma ausência não derruba as outras.
        self.assertEqual(doc["cpuTemp"], 44)

    def test_repouso_nao_toca_no_governor_da_maquina(self):
        d = self.daemon()
        d.tick()
        doc = self.publicado()
        self.assertEqual(doc["cpuTemp"], 44)
        self.assertEqual(self.governor(), "schedutil")
        self.assertEqual(doc["profile"]["applies"], "idle")

    def test_acpi_cpufreq_oferece_schedutil(self):
        fakefs.sessao_steam(self.raiz)
        d = self.daemon()
        d.tick()
        self.assertEqual(
            self.publicado()["profile"]["axes"]["governor"]["available"],
            ["powersave", "schedutil", "performance"])

    def test_saida_do_jogo_devolve_o_schedutil(self):
        # A máquina estava em schedutil, que o dev box nem oferece.
        # Restaurar tem que devolver o valor capturado, não um default.
        fakefs.sessao_steam(self.raiz)
        d = self.daemon()
        d.tick()
        self.assertEqual(self.governor(), "performance")
        for pid in (1200, 1201, 1202):
            (self.raiz / "proc" / str(pid) / "cgroup").unlink()
            (self.raiz / "proc" / str(pid) / "environ").unlink(missing_ok=True)
            (self.raiz / "proc" / str(pid) / "cmdline").unlink(missing_ok=True)
        self.relogio.avancar()
        d.tick()
        self.assertEqual(self.governor(), "schedutil")


class TestLimiteDeQuadros(DaemonBase):
    """O eixo que deixou de ser unsupported.

    Os testes montam a sessão gráfica na árvore falsa e trocam o runner
    por um duplo: o gamescopectl não existe num Mac, e mesmo no console
    executá-lo daqui mexeria numa sessão de verdade.
    """

    montar = staticmethod(fakefs.intel_rx7600)

    def setUp(self):
        super().setUp()
        fakefs.sessao_steam(self.raiz)
        fakefs.sessao_gamescope(self.raiz)
        fakefs.gamescopectl(self.raiz)
        # A forma REAL: help e valor em stderr, stdout vazio.
        self.runner = RunnerFalso({
            "help": fakefs.RESPOSTA_HELP,
            "debug_set_fps_limit": fakefs.RESPOSTA_GETTER,
        })

    def eixo(self):
        return self.publicado()["profile"]["axes"]["fpsLimit"]

    def escritas(self):
        return [c["argv"][2] for c in self.runner.chamadas if len(c["argv"]) == 3]

    # ----------------------------------------------------------------
    def test_o_eixo_deixa_de_ser_unsupported(self):
        d = self.daemon()
        d.tick()
        eixo = self.eixo()
        self.assertEqual(eixo["state"], "applied")
        self.assertEqual(eixo["available"], ["30", "60", "120", "sem limite"])
        # O perfil padrão pede `sem limite`, que é zero para o convar.
        self.assertEqual(self.escritas()[-1], "0")

    def test_a_regua_alcanca_AGRESSIVO(self):
        # A consequência no modelo de escore: com o fpsLimit aplicável, o
        # máximo alcançável sobe de 5 para 7 de 8, e `hot` exige 6.
        alcancavel = {"governor": "performance", "gpuLevel": "alto",
                      "fpsLimit": "sem limite", "priority": "alta"}
        self.assertEqual(score.score_of(alcancavel), 7)
        self.assertEqual(score.level_of(7), "hot")

        d = self.daemon()
        d.tick()
        corrente = d.manager.current_profile()
        # O perfil de fábrica (gpuLevel auto) dá 6, que já é AGRESSIVO.
        self.assertEqual(score.score_of(corrente), 6)
        self.assertEqual(self.publicado()["intensity"], 0.75)

    def test_saida_do_jogo_solta_o_limite(self):
        d = self.daemon()
        d.tick()
        self.assertIn("0", self.escritas())

        for pid in (1200, 1201, 1202):
            (self.raiz / "proc" / str(pid) / "cgroup").unlink()
            (self.raiz / "proc" / str(pid) / "environ").unlink(missing_ok=True)
            (self.raiz / "proc" / str(pid) / "cmdline").unlink(missing_ok=True)
        self.relogio.avancar()
        d.tick()
        # Console preso a 30 fps depois de fechar o jogo é a mesma classe
        # de falha que o governor preso em performance.
        self.assertEqual(self.escritas()[-1], "0")

    def test_sem_sessao_e_unavailable_e_nao_unsupported(self):
        for entrada in (self.raiz / "proc/1400").iterdir():
            entrada.unlink()
        d = self.daemon()
        d.tick()
        eixo = self.eixo()
        self.assertEqual(eixo["state"], "unavailable")
        self.assertEqual(eixo["available"], [])

    def test_convar_que_some_numa_atualizacao_volta_a_unsupported(self):
        # O prefixo `debug_` não é decoração.
        self.runner = RunnerFalso({"help": fakefs.RESPOSTA_HELP_SEM})
        d = self.daemon()
        d.tick()
        eixo = self.eixo()
        self.assertEqual(eixo["state"], "unsupported")
        self.assertEqual(eixo["available"], [])
        self.assertIn("debug_set_fps_limit", eixo["note"])
        # E o log guarda o que se procurou, para o nome novo ficar a uma
        # linha de journal de distância.
        self.assertTrue(any("fpsLimit" in l for l in self.log))

    def test_sessao_que_aparece_depois_do_start_e_apanhada(self):
        # O daemon sobe no multi-user.target; a sessão só existe depois do
        # login. Ficar `unavailable` para sempre seria o defeito.
        for entrada in (self.raiz / "proc/1400").iterdir():
            entrada.unlink()
        d = self.daemon()
        d.tick()
        self.assertEqual(self.eixo()["state"], "unavailable")

        fakefs.sessao_gamescope(self.raiz)
        self.relogio.avancar(fakefs.HZ)   # passa a janela de rebusca
        d.tick()
        self.assertEqual(self.eixo()["state"], "applied")

    def test_raiz_simulada_nao_fala_com_compositor_nenhum(self):
        # Sem runner injetado, --root instala o SimulatedRunner. O caminho
        # do gamescopectl é absoluto e o uid vem de um /proc falso: numa
        # máquina Linux isto executaria o binário real contra a sessão
        # real de quem está inspecionando.
        self.runner = None
        d = self.daemon()
        d.tick()
        self.assertEqual(self.eixo()["state"], "unavailable")
        self.assertIn("raiz simulada", self.eixo()["note"])
