"""
Detecção de jogo contra uma árvore de /proc montada como a Steam a monta.
"""

import tempfile
import unittest
from pathlib import Path

from gameprofiled import games
from gameprofiled.fs import Fs

from . import fakefs


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.raiz = Path(self.dir.name)
        self.fs = Fs(self.raiz)
        self.log = []

    def achar(self):
        return games.find_running_game(self.fs, self.log.append, hz=fakefs.HZ)


class TestSessaoSteam(Base):
    def setUp(self):
        super().setUp()
        fakefs.sessao_steam(self.raiz)

    def test_acha_pelo_cgroup(self):
        jogo = self.achar()
        self.assertEqual(jogo.appid, 553850)
        self.assertEqual(jogo.via, "cgroup")

    def test_pega_a_arvore_inteira_e_nao_so_o_reaper(self):
        # A lista de PIDs é o que o eixo de prioridade vai renicar.
        self.assertEqual(self.achar().pids, [1200, 1201, 1202])

    def test_o_launcher_nao_e_confundido_com_jogo(self):
        self.assertNotIn(1400, self.achar().pids)

    def test_inicio_e_o_do_processo_mais_antigo_do_grupo(self):
        # O reaper subiu aos 120 s de uptime; o binário do jogo, aos 124.
        # A sessão começou com o reaper.
        self.assertEqual(self.achar().started_at, (fakefs.BTIME + 120) * 1000)

    def test_sem_jogo_devolve_nada(self):
        for pid in (1200, 1201, 1202):
            (self.raiz / "proc" / str(pid) / "cgroup").unlink()
            (self.raiz / "proc" / str(pid) / "environ").unlink(missing_ok=True)
            (self.raiz / "proc" / str(pid) / "cmdline").unlink(missing_ok=True)
        self.assertIsNone(self.achar())


class TestFallbacks(Base):
    def test_environ_quando_nao_ha_cgroup(self):
        fakefs.proc(self.raiz)
        fakefs.processo(self.raiz, 2000, starttime=300 * fakefs.HZ,
                        environ=[b"SteamAppId=1145360", b"LANG=pt_BR.UTF-8"])
        jogo = self.achar()
        self.assertEqual((jogo.appid, jogo.via), (1145360, "environ"))

    def test_cmdline_quando_nao_ha_nem_cgroup_nem_environ(self):
        fakefs.proc(self.raiz)
        fakefs.processo(self.raiz, 2100, comm="reaper", starttime=300 * fakefs.HZ,
                        cmdline=[b"reaper", b"SteamLaunch", b"AppId=620", b"--"])
        jogo = self.achar()
        self.assertEqual((jogo.appid, jogo.via), (620, "cmdline"))


class TestCasosFeios(Base):
    def test_nome_de_executavel_com_parenteses(self):
        # `(sh)` dentro do comm quebra qualquer parse por split simples.
        fakefs.proc(self.raiz)
        fakefs.processo(self.raiz, 3000, comm="game (sh) x", starttime=50 * fakefs.HZ,
                        cgroup=f"{fakefs.SCOPE}/steam_app_413150")
        self.assertEqual(self.achar().started_at, (fakefs.BTIME + 50) * 1000)

    def test_dois_jogos_fica_o_mais_recente_e_o_caso_vai_ao_log(self):
        fakefs.sessao_steam(self.raiz, appid=553850, inicio_s=120)
        fakefs.processo(self.raiz, 2500, starttime=600 * fakefs.HZ,
                        cgroup=f"{fakefs.SCOPE}/steam_app_367520")
        self.assertEqual(self.achar().appid, 367520)
        self.assertTrue(any("2 sessões" in linha for linha in self.log))

    def test_processo_que_some_no_meio_da_varredura(self):
        # /proc é uma corrida por natureza: o PID some entre o listdir e a
        # leitura. Não pode derrubar o daemon.
        fakefs.sessao_steam(self.raiz)
        (self.raiz / "proc/1201/cgroup").unlink()
        (self.raiz / "proc/1201/stat").unlink()
        self.assertEqual(self.achar().pids, [1200, 1202])

    def test_proc_vazio(self):
        fakefs.bare(self.raiz)
        self.assertIsNone(self.achar())
