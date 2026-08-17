"""
Os quatro eixos, contra as duas máquinas reais do projeto.

O teste que mais importa aqui é o do governor com intel_pstate: schedutil
não existe nessa máquina, e o eixo tem que dizer isso em vez de escrever e
seguir em frente.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from gameprofiled import axes, config, profile, sensors
from gameprofiled.fs import Fs

from . import fakefs


class OpsFalso:
    """Grava as chamadas em vez de executá-las — nenhuma delas existe num
    Mac, e `setpriority` num PID inventado seria pior que não existir.

    Mas ESCREVE o efeito de volta no /proc falso. Um duplo que só registra
    a chamada verificaria que o daemon pediu, não que a máquina obedeceu, e
    a releitura é exatamente o que separa as duas coisas."""

    def __init__(self, raiz=None, falhar=()):
        self.raiz = raiz
        self.nice = []
        self.ioprio = []
        self.falhar = set(falhar)

    def setpriority(self, pid, valor):
        if pid in self.falhar:
            return "PermissionError: Operation not permitted"
        self.nice.append((pid, valor))
        if self.raiz is not None:
            fakefs.set_nice(self.raiz, pid, valor)
        return None

    def set_ioprio(self, pid, classe, nivel):
        self.ioprio.append((pid, classe, nivel))
        return None


class Base(unittest.TestCase):
    montar = staticmethod(fakefs.intel_rx7600)

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.raiz = Path(self.dir.name)
        self.montar(self.raiz)
        self.fs = Fs(self.raiz)
        self.gpu = sensors.find_gpu(self.fs)
        self.ops = OpsFalso(self.raiz)
        self.log = []


class TestGovernorIntel(Base):
    montar = staticmethod(fakefs.intel_rx7600)

    def test_disponiveis_sao_so_os_que_o_driver_oferece(self):
        eixo = axes.Governor(self.fs)
        # intel_pstate ativo: schedutil NAO existe. É o achado que obriga o
        # launcher a desabilitar a opção.
        self.assertEqual(eixo.available(), ["powersave", "performance"])
        self.assertEqual(eixo.driver(), "intel_pstate")

    def test_schedutil_e_indisponivel_e_nao_e_escrito(self):
        eixo = axes.Governor(self.fs)
        resultado = eixo.apply("schedutil")
        self.assertEqual(resultado.state, "unavailable")
        self.assertIn("intel_pstate", resultado.note)
        # E o governor não foi tocado.
        self.assertEqual(eixo.read(), "powersave")

    def test_performance_aplica_em_todas_as_politicas(self):
        eixo = axes.Governor(self.fs)
        resultado = eixo.apply("performance")
        self.assertEqual(resultado.state, "applied")
        for politica in self.fs.glob(axes.CPUFREQ):
            self.assertEqual(self.fs.read(politica / "scaling_governor"), "performance")

    def test_releitura_diferente_vira_degraded(self):
        eixo = axes.Governor(self.fs)

        # Um kernel que aceita a escrita e mantém outro valor. Sem a
        # releitura o daemon reportaria `applied` e ninguém saberia.
        original = self.fs.write

        def teimoso(caminho, valor):
            if "scaling_governor" in str(caminho):
                return original(caminho, "powersave")
            return original(caminho, valor)

        self.fs.write = teimoso
        resultado = eixo.apply("performance")
        self.assertEqual(resultado.state, "degraded")
        self.assertIn("releitura devolveu powersave", resultado.note)

    def test_restaura_valor_fora_do_vocabulario(self):
        # A máquina podia estar em `ondemand`. Devolver `powersave` porque
        # `ondemand` não está no modelo deixaria a máquina diferente de
        # como a encontramos.
        #
        # O valor aplicado no meio é OBRIGATÓRIO neste teste. A versão
        # anterior escrevia `ondemand` e restaurava para `ondemand`: a
        # máquina já estava no destino, e uma restauração que não fizesse
        # nada passaria igual. Teste de restauração só prova alguma coisa
        # quando o valor de partida difere do que foi aplicado.
        eixo = axes.Governor(self.fs)
        for politica in self.fs.glob(axes.CPUFREQ):
            self.fs.write(politica / "scaling_governor", "ondemand")
        capturado = eixo.read()
        eixo.apply("performance")
        self.assertEqual(eixo.read(), "performance")

        eixo.restore(capturado)
        self.assertEqual(eixo.read(), "ondemand")


class TestGovernorConsole(Base):
    montar = staticmethod(fakefs.ryzen_5700g)

    def test_acpi_cpufreq_oferece_os_tres(self):
        eixo = axes.Governor(self.fs)
        self.assertEqual(eixo.available(), ["powersave", "schedutil", "performance"])
        self.assertEqual(eixo.apply("schedutil").state, "applied")


class TestGovernorSemCpufreq(Base):
    montar = staticmethod(fakefs.bare)

    def test_sem_cpufreq_e_unsupported_e_nao_failed(self):
        resultado = axes.Governor(self.fs).apply("performance")
        self.assertEqual(resultado.state, "unsupported")
        self.assertEqual(resultado.available, [])


class TestGpuLevel(Base):
    def test_aplica_e_confere(self):
        eixo = axes.GpuLevel(self.fs, self.gpu)
        self.assertEqual(eixo.available(), ["baixo", "auto", "alto"])
        resultado = eixo.apply("alto")
        self.assertEqual(resultado.state, "applied")
        no = self.gpu.device / "power_dpm_force_performance_level"
        self.assertEqual(self.fs.read(no), "high")
        self.assertEqual(eixo.read(), "alto")

    def test_estado_do_driver_fora_do_vocabulario_vem_bruto(self):
        no = self.gpu.device / "power_dpm_force_performance_level"
        self.fs.write(no, "profile_peak")
        # Forçar isso para dentro de baixo/auto/alto seria inventar.
        self.assertEqual(axes.GpuLevel(self.fs, self.gpu).read(), "profile_peak")

    def test_sem_gpu_e_unsupported(self):
        resultado = axes.GpuLevel(self.fs, None).apply("auto")
        self.assertEqual(resultado.state, "unsupported")
        self.assertEqual(resultado.available, [])


class TestFpsLimit(Base):
    def test_nunca_aplica_e_diz_por_que(self):
        resultado = axes.FpsLimit(self.fs).apply("60")
        self.assertEqual(resultado.state, "unsupported")
        self.assertEqual(resultado.available, [])
        self.assertIn("gamescope", resultado.note)


class TestPriority(Base):
    def setUp(self):
        super().setUp()
        fakefs.sessao_steam(self.raiz)
        self.ops = OpsFalso(self.raiz)
        self.ctx = {"pids": [1200, 1201, 1202], "cgroup": "steam_app_553850"}

    def test_tempo_real_nao_e_oferecido(self):
        # SCHED_FIFO num processo de jogo pode travar o console.
        self.assertEqual(axes.Priority(self.fs, self.ops).available(),
                         ["padrão", "alta"])

    def test_renica_a_arvore_inteira(self):
        resultado = axes.Priority(self.fs, self.ops).apply("alta", self.ctx)
        self.assertEqual(resultado.state, "applied")
        self.assertEqual(self.ops.nice, [(1200, -5), (1201, -5), (1202, -5)])
        self.assertEqual(self.ops.ioprio, [(p, 2, 0) for p in (1200, 1201, 1202)])
        self.assertIn("steam_app_553850", resultado.note)

    def test_sem_jogo_e_unavailable_e_nao_unsupported(self):
        # O eixo existe e é implementável; falta a pré-condição agora.
        resultado = axes.Priority(self.fs, self.ops).apply("alta", {"pids": []})
        self.assertEqual(resultado.state, "unavailable")
        self.assertEqual(resultado.available, ["padrão", "alta"])

    def test_falha_parcial_vira_degraded(self):
        ops = OpsFalso(self.raiz, falhar={1201})
        resultado = axes.Priority(self.fs, ops).apply("alta", self.ctx)
        self.assertEqual(resultado.state, "degraded")
        self.assertIn("1 falharam", resultado.note)


class TestCicloDeVida(Base):
    def setUp(self):
        super().setUp()
        fakefs.sessao_steam(self.raiz)
        self.ops = OpsFalso(self.raiz)
        self.config = config.Config(self.fs, log=self.log.append)
        self.gerente = profile.ProfileManager(
            self.fs, self.config, self.gpu, self.ops, self.log.append)

    def _jogo(self):
        from gameprofiled import games
        return games.find_running_game(self.fs, hz=fakefs.HZ)

    def test_repouso_observa_e_nao_escreve(self):
        antes = self.fs.read(self.fs.glob(axes.CPUFREQ)[0] / "scaling_governor")
        self.gerente.sync(None)
        depois = self.fs.read(self.fs.glob(axes.CPUFREQ)[0] / "scaling_governor")
        self.assertEqual(antes, depois)
        self.assertEqual(self.gerente.estado["governor"].state, "observed")
        self.assertEqual(self.gerente.to_json()["applies"], "idle")

    def test_jogo_aplica_o_perfil_padrao(self):
        self.gerente.sync(self._jogo())
        estado = self.gerente.estado
        self.assertEqual(estado["governor"].state, "applied")
        self.assertEqual(estado["governor"].current, "performance")
        self.assertEqual(estado["gpuLevel"].current, "auto")
        self.assertEqual(estado["fpsLimit"].state, "unsupported")
        self.assertEqual(estado["priority"].state, "applied")
        self.assertEqual(self.gerente.to_json()["applies"], "553850")

    def test_saida_do_jogo_devolve_a_maquina(self):
        politica = self.fs.glob(axes.CPUFREQ)[0] / "scaling_governor"
        antes = self.fs.read(politica)
        self.gerente.sync(self._jogo())
        self.assertEqual(self.fs.read(politica), "performance")

        # A tela 17b promete que fechar o jogo reverte o perfil.
        self.gerente.sync(None)
        self.assertEqual(self.fs.read(politica), antes)
        self.assertEqual(self.gerente.estado["governor"].state, "observed")

    def test_nao_reescreve_a_cada_leitura(self):
        jogo = self._jogo()
        self.gerente.sync(jogo)
        escritas = []
        original = self.fs.write
        self.fs.write = lambda c, v: (escritas.append(str(c)), original(c, v))[1]
        for _ in range(5):
            self.gerente.sync(jogo)
        # Nenhuma escrita em sysfs: só a prioridade é reavaliada, porque a
        # árvore de processos do jogo cresce depois do lançamento.
        self.assertEqual([c for c in escritas if "/sys/" in c], [])

    def test_encerrar_o_daemon_com_jogo_rodando_tambem_restaura(self):
        politica = self.fs.glob(axes.CPUFREQ)[0] / "scaling_governor"
        antes = self.fs.read(politica)
        self.gerente.sync(self._jogo())
        self.gerente.shutdown()
        self.assertEqual(self.fs.read(politica), antes)

    def test_perfil_corrente_alimenta_o_escore(self):
        from gameprofiled import score
        self.gerente.sync(self._jogo())
        corrente = self.gerente.current_profile()
        self.assertEqual(corrente["priority"], "alta")
        # governor performance (2) + gpuLevel auto (1) + fpsLimit ausente (0)
        # + priority alta (1). O fpsLimit não pontua porque não foi aplicado,
        # e é isso que faz a régua descrever a máquina e não o pedido.
        self.assertEqual(score.score_of(corrente), 4)


class TestPerfilMudaNoDisco(Base):
    """A terceira transição: o arquivo de perfis muda com o jogo rodando.

    É o caminho que o editor de perfil vai usar — ele grava o arquivo, e o
    daemon reage a ele. Por isso a gravação destes testes é `.tmp` +
    `os.replace()`, que é como o kyber-api vai gravar e como o `vi` com
    backup grava: se o daemon só notasse reescrita no lugar, passaria aqui
    e falharia no console.
    """

    def setUp(self):
        super().setUp()
        fakefs.sessao_steam(self.raiz)
        self.ops = OpsFalso(self.raiz)
        self.alvo = self.raiz / "var/lib/kyber/profiles.json"
        self.alvo.parent.mkdir(parents=True, exist_ok=True)
        self._gravar({"governor": "performance", "gpuLevel": "alto"})
        self.config = config.Config(self.fs, log=self.log.append)
        self.gerente = profile.ProfileManager(
            self.fs, self.config, self.gpu, self.ops, self.log.append)

    def _gravar(self, padrao, jogos=None):
        temporario = self.alvo.parent / (self.alvo.name + ".tmp")
        temporario.write_text(json.dumps({"default": padrao, "games": jogos or {}}))
        os.replace(temporario, self.alvo)

    def _jogo(self):
        from gameprofiled import games
        return games.find_running_game(self.fs, hz=fakefs.HZ)

    @property
    def _governor(self):
        return self.fs.read(self.fs.glob(axes.CPUFREQ)[0] / "scaling_governor")

    @property
    def _dpm(self):
        return self.fs.read(self.gpu.device / "power_dpm_force_performance_level")

    # ------------------------------------------------------------------
    def test_edicao_com_jogo_rodando_vale_sem_relancar(self):
        jogo = self._jogo()
        self.gerente.sync(jogo)
        self.assertEqual(self._governor, "performance")

        self._gravar({"governor": "performance", "gpuLevel": "alto"},
                     jogos={"553850": {"governor": "powersave"}})
        self.assertTrue(self.config.reload())
        self.gerente.sync(jogo, config_mudou=True)

        self.assertEqual(self._governor, "powersave")
        self.assertEqual(self.gerente.estado["governor"].requested, "powersave")
        self.assertTrue(any("reaplicando" in linha for linha in self.log))

    def test_reaplicar_nao_recaptura_e_a_saida_devolve_o_que_havia_antes(self):
        """O teste que mais importa deste grupo.

        Recapturar na reaplicação guardaria o que o PRÓPRIO daemon acabou
        de escrever, e fechar o jogo devolveria a máquina para
        performance/alto em vez do powersave/auto que estava lá. Não
        levanta erro nenhum: chega como "meu PC fica quente depois de
        jogar", meses depois."""
        self.assertEqual((self._governor, self._dpm), ("powersave", "auto"))

        jogo = self._jogo()
        self.gerente.sync(jogo)
        self.assertEqual((self._governor, self._dpm), ("performance", "high"))

        self._gravar({"governor": "performance", "gpuLevel": "alto"},
                     jogos={"553850": {"gpuLevel": "baixo"}})
        self.assertTrue(self.config.reload())
        self.gerente.sync(jogo, config_mudou=True)
        self.assertEqual(self._dpm, "low")

        # A captura continua sendo a da ENTRADA do jogo, não a do momento
        # da reaplicação.
        self.assertEqual(self.gerente.capturado["governor"], "powersave")
        self.assertEqual(self.gerente.capturado["gpuLevel"], "auto")

        self.gerente.sync(None)
        self.assertEqual((self._governor, self._dpm), ("powersave", "auto"))

    def test_edicao_de_outro_titulo_nao_escreve_em_sysfs(self):
        jogo = self._jogo()
        self.gerente.sync(jogo)

        escritas = []
        original = self.fs.write
        self.fs.write = lambda c, v: (escritas.append(str(c)), original(c, v))[1]

        self._gravar({"governor": "performance", "gpuLevel": "alto"},
                     jogos={"730": {"governor": "powersave"}})
        self.assertTrue(self.config.reload())
        self.gerente.sync(jogo, config_mudou=True)

        # O arquivo mudou, o perfil DESTE título não. Sem a comparação, um
        # arquivo reescrito em laço viraria escrita em sysfs em laço.
        self.assertEqual([c for c in escritas if "/sys/" in c], [])

    def test_sem_jogo_a_edicao_nao_aplica_nada(self):
        self.gerente.sync(None)
        antes = (self._governor, self._dpm)

        self._gravar({"governor": "performance", "gpuLevel": "alto"},
                     jogos={"553850": {"governor": "powersave"}})
        self.assertTrue(self.config.reload())
        self.gerente.sync(None, config_mudou=True)

        # Em repouso o daemon observa e não aplica; editar o arquivo não
        # muda isso. A edição vale no próximo lançamento.
        self.assertEqual((self._governor, self._dpm), antes)
        self.assertEqual(self.gerente.estado["governor"].state, "observed")

    def test_no_apply_acompanha_a_edicao_sem_escrever(self):
        gerente = profile.ProfileManager(
            self.fs, self.config, self.gpu, self.ops, self.log.append,
            apply_enabled=False)
        jogo = self._jogo()
        gerente.sync(jogo)
        self.assertEqual(gerente.estado["gpuLevel"].requested, "alto")
        self.assertEqual(self._dpm, "auto")

        self._gravar({"governor": "performance", "gpuLevel": "baixo"})
        self.assertTrue(self.config.reload())
        gerente.sync(jogo, config_mudou=True)

        # O modo existe para mostrar o que ACONTECERIA. Publicar o pedido
        # velho depois de alguém editar o arquivo seria mentir sobre isso.
        self.assertEqual(gerente.estado["gpuLevel"].requested, "baixo")
        self.assertEqual(self._dpm, "auto")


class TestConfig(Base):
    def test_semeia_do_usr_share(self):
        semente = self.raiz / "usr/share/kyber/profiles.default.json"
        semente.parent.mkdir(parents=True, exist_ok=True)
        semente.write_text(json.dumps({
            "curve": {"wattsIdle": 19, "wattsPerPoint": 6, "calibrated": True},
            "default": {"governor": "powersave"},
            "games": {"553850": {"priority": "alta"}},
        }))
        cfg = config.Config(self.fs, log=self.log.append)
        self.assertTrue((self.raiz / "var/lib/kyber/profiles.json").exists())
        self.assertEqual(cfg.curve(), {"wattsIdle": 19, "wattsPerPoint": 6,
                                       "calibrated": True})
        self.assertEqual(cfg.profile_for(553850)["governor"], "powersave")
        self.assertEqual(cfg.profile_for(553850)["priority"], "alta")

    def test_sem_arquivo_usa_o_embutido_e_marca_nao_calibrado(self):
        cfg = config.Config(self.fs, log=self.log.append)
        self.assertEqual(cfg.origin, "padrão embutido")
        self.assertEqual(cfg.curve(), {"wattsIdle": 22, "wattsPerPoint": 7,
                                       "calibrated": False})
        self.assertEqual(cfg.profile_for(1)["governor"], "performance")
        self.assertEqual(cfg.profile_for(1)["gpuLevel"], "auto")

    def test_json_quebrado_nao_derruba_o_console(self):
        alvo = self.raiz / "var/lib/kyber/profiles.json"
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text("{ isto nao e json")
        cfg = config.Config(self.fs, log=self.log.append)
        self.assertEqual(cfg.origin, "padrão embutido")
        self.assertTrue(any("ilegível" in linha for linha in self.log))

    def test_valor_fora_do_modelo_e_ignorado_e_logado(self):
        alvo = self.raiz / "var/lib/kyber/profiles.json"
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(json.dumps({"default": {"governor": "turbo_maximo"}}))
        cfg = config.Config(self.fs, log=self.log.append)
        self.assertEqual(cfg.profile_for(1)["governor"], "performance")
        self.assertTrue(any("turbo_maximo" in linha for linha in self.log))

    def test_troca_de_arquivo_e_notada_mesmo_com_carimbo_igual(self):
        # Os dois conteúdos têm o MESMO tamanho e o teste força o mesmo
        # mtime, então só o inode separa um do outro. É o caso real de um
        # filesystem de carimbo grosso — ext4 com inode de 128 bytes
        # arredonda para o segundo — recebendo duas gravações seguidas.
        alvo = self.raiz / "var/lib/kyber/profiles.json"
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(json.dumps({"default": {"governor": "powersave"}}))
        cfg = config.Config(self.fs, log=self.log.append)
        antes = alvo.stat()

        temporario = alvo.parent / "profiles.json.tmp"
        temporario.write_text(json.dumps({"default": {"governor": "schedutil"}}))
        os.replace(temporario, alvo)
        os.utime(alvo, ns=(antes.st_atime_ns, antes.st_mtime_ns))
        self.assertEqual(alvo.stat().st_size, antes.st_size)
        self.assertEqual(alvo.stat().st_mtime_ns, antes.st_mtime_ns)

        self.assertTrue(cfg.reload())
        self.assertEqual(cfg.profile_for(1)["governor"], "schedutil")

    def test_rele_so_quando_o_arquivo_muda(self):
        alvo = self.raiz / "var/lib/kyber/profiles.json"
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(json.dumps({"default": {"governor": "powersave"}}))
        cfg = config.Config(self.fs, log=self.log.append)
        self.assertFalse(cfg.reload())
        os.utime(alvo, ns=(0, 0))
        self.assertTrue(cfg.reload())
