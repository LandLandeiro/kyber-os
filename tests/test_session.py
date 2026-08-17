"""
A travessia para dentro da sessão gráfica, e a detecção do convar.

Dois grupos de teste, e os dois protegem contra a mesma classe de falha:
depender de uma coisa cuja presença nunca foi verificada.
"""

import tempfile
import unittest
from pathlib import Path

from gameprofiled import axes, session
from gameprofiled.fs import Fs

from . import fakefs


class RunnerFalso:
    """Grava as chamadas em vez de executá-las, e devolve o que o teste
    mandar. `gamescopectl` não existe num Mac, e mesmo no console executá-lo
    de dentro do teste seria mexer numa sessão de verdade."""

    def __init__(self, respostas=None):
        self.chamadas = []
        self.respostas = respostas or {}

    def __call__(self, argv, env, uid, gid, timeout):
        self.chamadas.append({"argv": list(argv), "env": dict(env),
                              "uid": uid, "gid": gid, "timeout": timeout})
        chave = " ".join(argv[1:])
        return self.respostas.get(chave, (0, "", ""))


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.raiz = Path(self.dir.name)
        self.fs = Fs(self.raiz)
        self.log = []


class TestDescoberta(Base):
    def test_acha_pelo_marcador_do_session_plus(self):
        fakefs.sessao_gamescope(self.raiz)
        s = session.find_session(self.fs, self.log.append)
        # Nada de uid fixo: tudo saiu de um processo que está DENTRO da
        # sessão, e saiu junto, coerente por construção.
        self.assertEqual((s.uid, s.gid), (1000, 1000))
        self.assertEqual(s.runtime_dir, "/run/user/1000")
        self.assertEqual(s.display, "gamescope-0")
        self.assertEqual(s.via, "processo")

    def test_uid_diferente_de_1000(self):
        fakefs.sessao_gamescope(self.raiz, uid=1001, gid=1001)
        s = session.find_session(self.fs)
        self.assertEqual((s.uid, s.runtime_dir), (1001, "/run/user/1001"))

    def test_wayland_display_comum_nao_serve_de_marcador(self):
        # Numa sessão de desktop o WAYLAND_DISPLAY é o compositor do
        # desktop, que não entende o convar do gamescope.
        fakefs.proc(self.raiz)
        fakefs.processo(self.raiz, 900, environ=[
            b"XDG_RUNTIME_DIR=/run/user/1000", b"WAYLAND_DISPLAY=wayland-0"])
        self.assertIsNone(session.find_session(self.fs, self.log.append))
        self.assertTrue(any("nenhuma" in l for l in self.log))

    def test_wayland_display_do_gamescope_serve(self):
        fakefs.sessao_gamescope(self.raiz, marcador=b"WAYLAND_DISPLAY")
        self.assertEqual(session.find_session(self.fs).display, "gamescope-0")

    def test_fallback_pelo_socket(self):
        # Sessão iniciada fora do session-plus não tem o marcador.
        fakefs.proc(self.raiz)
        fakefs.socket_gamescope(self.raiz)
        s = session.find_session(self.fs, self.log.append)
        self.assertEqual((s.display, s.via), ("gamescope-0", "socket"))
        self.assertEqual(s.runtime_dir, "/run/user/1000")

    def test_sobra_de_mktemp_nao_e_confundida_com_sessao(self):
        # /run/user/1000/gamescope.XXXXXXX são os diretórios que o
        # session-plus deixa para trás. O glob do fallback casa com
        # `gamescope-*`, não com `gamescope.*`.
        fakefs.proc(self.raiz)
        (self.raiz / "run/user/1000/gamescope.AbC1234").mkdir(parents=True)
        self.assertIsNone(session.find_session(self.fs))

    def test_sem_proc_nao_estoura(self):
        fakefs.bare(self.raiz)
        self.assertIsNone(session.find_session(self.fs, self.log.append))


class TestTresCamadas(Base):
    def setUp(self):
        super().setUp()
        fakefs.sessao_gamescope(self.raiz)
        self.sessao = session.find_session(self.fs)

    def compositor(self, respostas=None, com_binario=True):
        if com_binario:
            fakefs.gamescopectl(self.raiz)
        self.runner = RunnerFalso(respostas)
        return session.Compositor(self.fs, self.sessao, self.runner)

    def test_1_sem_binario_e_unsupported(self):
        c = self.compositor(com_binario=False)
        self.assertEqual(c.probe(), "unsupported")
        self.assertIn("não existe", c.nota)
        self.assertEqual(self.runner.chamadas, [])

    def test_2_sem_sessao_e_unavailable_e_nao_unsupported(self):
        fakefs.gamescopectl(self.raiz)
        c = session.Compositor(self.fs, None, RunnerFalso())
        # O eixo funciona; falta a pré-condição AGORA. O daemon sobe no
        # multi-user.target e a sessão só existe depois do login.
        self.assertEqual(c.probe(), "unavailable")

    def test_3_convar_ausente_e_unsupported(self):
        # É o caso que o prefixo `debug_` torna provável: uma atualização
        # do gamescope renomeia ou remove o comando.
        c = self.compositor({"help": (0, fakefs.HELP_SEM_CONVAR, "")})
        self.assertEqual(c.probe(), "unsupported")
        self.assertIn("debug_set_fps_limit", c.nota)

    def test_3_convar_presente_e_ok(self):
        c = self.compositor({"help": (0, fakefs.HELP_COM_CONVAR, ""),
                             "debug_set_fps_limit": (0, "0\n", "")})
        self.assertEqual(c.probe(), "ok")
        self.assertTrue(c.getter)
        self.assertIsNone(c.nota)

    def test_sem_getter_o_sucesso_e_so_o_codigo_de_saida(self):
        c = self.compositor({"help": (0, fakefs.HELP_COM_CONVAR, ""),
                             "debug_set_fps_limit": (1, "", "unknown")})
        self.assertEqual(c.probe(), "ok")
        self.assertFalse(c.getter)
        self.assertIn("sem releitura", c.nota)

    def test_help_que_nao_responde_e_unavailable(self):
        # Compositor morto: o binário está lá, a sessão foi encontrada, e
        # ninguém atende. Não é `unsupported` — a máquina sabe fazer isso.
        c = self.compositor({"help": (None, "", "tempo esgotado em 2.0s")})
        self.assertEqual(c.probe(), "unavailable")
        self.assertIn("tempo esgotado", c.nota)

    def test_o_ambiente_do_filho_e_minimo_e_o_uid_e_o_da_sessao(self):
        c = self.compositor({"help": (0, fakefs.HELP_COM_CONVAR, "")})
        c.probe()
        chamada = self.runner.chamadas[0]
        self.assertEqual(chamada["uid"], 1000)
        self.assertEqual(chamada["gid"], 1000)
        self.assertEqual(chamada["env"]["XDG_RUNTIME_DIR"], "/run/user/1000")
        self.assertEqual(chamada["env"]["WAYLAND_DISPLAY"], "gamescope-0")
        # Nada do daemon vaza para o filho.
        self.assertEqual(set(chamada["env"]), {"XDG_RUNTIME_DIR", "WAYLAND_DISPLAY", "PATH"})
        # Caminho absoluto: PATH resolvido de dentro do ambiente de um
        # usuário é como se executa o binário errado.
        self.assertTrue(chamada["argv"][0].startswith("/usr/bin/"))
        # Cliente Wayland esperando compositor morto bloqueia, e o laço
        # publica a 1 Hz.
        self.assertLessEqual(chamada["timeout"], 5)


class TestEixo(Base):
    def setUp(self):
        super().setUp()
        fakefs.sessao_gamescope(self.raiz)
        fakefs.gamescopectl(self.raiz)
        self.sessao = session.find_session(self.fs)

    def eixo(self, respostas):
        self.runner = RunnerFalso(respostas)
        c = session.Compositor(self.fs, self.sessao, self.runner)
        c.probe()
        return axes.FpsLimit(self.fs, c)

    def com_getter(self, valor=0):
        return self.eixo({"help": (0, fakefs.HELP_COM_CONVAR, ""),
                          "debug_set_fps_limit": (0, f"{valor}\n", "")})

    def sem_getter(self):
        return self.eixo({"help": (0, fakefs.HELP_COM_CONVAR, ""),
                          "debug_set_fps_limit": (1, "", "no value")})

    def escritas(self):
        return [c["argv"][2] for c in self.runner.chamadas if len(c["argv"]) == 3]

    # ----------------------------------------------------------------
    def test_available_traz_os_quatro_limites(self):
        self.assertEqual(self.com_getter().available(),
                         ["30", "60", "120", "sem limite"])

    def test_sem_suporte_available_e_vazio(self):
        eixo = self.eixo({"help": (0, fakefs.HELP_SEM_CONVAR, "")})
        self.assertEqual(eixo.available(), [])
        self.assertEqual(eixo.apply("60").state, "unsupported")

    def test_sem_limite_vira_zero(self):
        eixo = self.sem_getter()
        eixo.apply("sem limite")
        self.assertEqual(self.escritas()[-1], "0")

    def test_numero_vira_numero(self):
        eixo = self.sem_getter()
        eixo.apply("30")
        self.assertEqual(self.escritas()[-1], "30")

    def test_com_getter_o_applied_tem_prova(self):
        eixo = self.com_getter(valor=30)
        resultado = eixo.apply("30")
        self.assertEqual(resultado.state, "applied")
        self.assertEqual(resultado.current, "30")
        self.assertIsNone(resultado.note)

    def test_sem_getter_o_applied_diz_que_nao_tem_prova(self):
        resultado = self.sem_getter().apply("60")
        self.assertEqual(resultado.state, "applied")
        self.assertIn("sem releitura", resultado.note)

    def test_releitura_diferente_vira_degraded(self):
        eixo = self.com_getter(valor=60)
        resultado = eixo.apply("30")
        self.assertEqual(resultado.state, "degraded")
        self.assertIn("releitura devolveu 60", resultado.note)

    def test_comando_que_falha_vira_failed(self):
        eixo = self.eixo({"help": (0, fakefs.HELP_COM_CONVAR, ""),
                          "debug_set_fps_limit": (0, "0\n", ""),
                          "debug_set_fps_limit 30": (1, "", "recusado")})
        resultado = eixo.apply("30")
        self.assertEqual(resultado.state, "failed")
        self.assertIn("recusado", resultado.note)

    # ---------- restauração ----------
    def test_restaura_o_valor_capturado_quando_ha_getter(self):
        eixo = self.com_getter(valor=60)
        eixo.restore("60")
        self.assertEqual(self.escritas()[-1], "60")

    def test_sem_getter_restaura_para_zero_e_DIZ_QUE_SUPÕE(self):
        # A ressalva que separa este eixo do governor: o governor lê o
        # valor anterior do sysfs e devolve o que encontrou. Este, sem
        # releitura, não tem o que capturar — e o gamescopectl é público,
        # então outro processo da sessão pode ter posto o limite.
        eixo = self.sem_getter()
        resultado = eixo.restore(None)
        self.assertEqual(self.escritas()[-1], "0")
        self.assertIn("SUPOSIÇÃO", resultado.note)
        self.assertIn("outro processo", resultado.note)

    def test_restauracao_para_zero_e_a_direcao_segura(self):
        # Tirar limite nunca trava console; ficar preso a 30 fps depois de
        # fechar o jogo é a mesma classe de falha que o governor preso em
        # performance.
        eixo = self.sem_getter()
        eixo.apply("30")
        eixo.restore(None)
        self.assertEqual(self.escritas(), ["30", "0"])


class TestDicaDeEperm(unittest.TestCase):
    """A queda de privilégio falha por duas razões distintas na unit, e as
    duas chegam como o mesmo EPERM sem contexto. Custaram uma ida ao
    hardware; a pista existe para não custarem uma segunda."""

    def test_eperm_ganha_a_pista_das_capabilities(self):
        erro = PermissionError(1, "Operation not permitted")
        texto = session.descrever(erro)
        self.assertIn("Operation not permitted", texto)
        self.assertIn("CAP_SETUID", texto)
        self.assertIn("CAP_SETGID", texto)
        self.assertIn("ProtectHome", texto)

    def test_outros_erros_nao_ganham_pista_errada(self):
        erro = FileNotFoundError(2, "No such file or directory")
        texto = session.descrever(erro)
        self.assertNotIn("CAP_SETUID", texto)
        self.assertIn("No such file", texto)


class TestCanaisDeSaida(Base):
    """O `gamescopectl help` escreve em STDERR.

    A sondagem lia só stdout e reprovou um convar que existia. O regresso
    é fácil de reintroduzir — em qualquer chamada nova que escolha um
    canal — e caro de perceber, porque produz a mesma frase que um convar
    de verdade removido.
    """

    def setUp(self):
        super().setUp()
        fakefs.sessao_gamescope(self.raiz)
        fakefs.gamescopectl(self.raiz)
        self.sessao = session.find_session(self.fs)

    def compositor(self, respostas):
        self.runner = RunnerFalso(respostas)
        return session.Compositor(self.fs, self.sessao, self.runner)

    # ---------- o bug ----------
    def test_help_em_stderr_e_detectado(self):
        c = self.compositor({"help": fakefs.RESPOSTA_HELP,
                             "debug_set_fps_limit": fakefs.RESPOSTA_GETTER})
        self.assertEqual(c.probe(), "ok")
        self.assertTrue(c.getter)

    def test_help_em_stdout_continua_detectado(self):
        c = self.compositor({"help": (0, fakefs.HELP_COM_CONVAR, ""),
                             "debug_set_fps_limit": (0, "0\n", "")})
        self.assertEqual(c.probe(), "ok")

    def test_help_dividido_entre_os_dois_canais(self):
        c = self.compositor({"help": (0, "convars:\n", "  debug_set_fps_limit\n"),
                             "debug_set_fps_limit": fakefs.RESPOSTA_GETTER})
        self.assertEqual(c.probe(), "ok")

    def test_conteudo_vence_codigo_de_saida(self):
        # Ferramenta que escreve help em stderr é ferramenta que pode sair
        # com código diferente de zero num help. O que importa é se ESTA
        # build conhece o convar.
        c = self.compositor({"help": (1, "", fakefs.HELP_COM_CONVAR),
                             "debug_set_fps_limit": fakefs.RESPOSTA_GETTER})
        self.assertEqual(c.probe(), "ok")

    def test_getter_em_stderr_e_lido(self):
        c = self.compositor({"help": fakefs.RESPOSTA_HELP,
                             "debug_set_fps_limit": (0, "", "debug_set_fps_limit = 60\n")})
        c.probe()
        self.assertEqual(c.get_limit(), 60)

    # ---------- distinguir os dois casos ----------
    def test_sem_saida_nenhuma_e_unavailable_e_nao_unsupported(self):
        # Não dá para acusar o convar de ter sumido sem ter visto a lista.
        c = self.compositor({"help": (0, "", "")})
        self.assertEqual(c.probe(), "unavailable")
        self.assertIn("não respondeu", c.nota)

    def test_a_nota_distingue_convar_removido_de_canal_errado(self):
        c = self.compositor({"help": fakefs.RESPOSTA_HELP_SEM})
        self.assertEqual(c.probe(), "unsupported")
        # A impressão digital: quantas linhas vieram e quantas citam fps.
        self.assertIn("3 linhas", c.nota)
        self.assertIn("0 citando fps", c.nota)

    def test_convar_renomeado_deixa_os_candidatos_na_nota(self):
        renomeado = "convars:\n  set_fps_limit\n  vblank_debug\n"
        c = self.compositor({"help": (0, "", renomeado)})
        self.assertEqual(c.probe(), "unsupported")
        self.assertIn("1 citando fps", c.nota)
        # O nome novo fica escrito, para a correção ser de uma linha.
        self.assertIn("set_fps_limit", c.nota)


class TestLeituraEstrita(unittest.TestCase):
    """Releitura errada é pior que releitura nenhuma: ela alimenta a
    comparação do `apply`, e um número pescado de uma mensagem de erro
    viraria `degraded` inventado — ou um `applied` por coincidência."""

    def test_formas_aceitas(self):
        for texto, esperado in [
            ("0", 0),
            ("30\n", 30),
            ("debug_set_fps_limit = 0", 0),
            ("debug_set_fps_limit: 60", 60),
            ("debug_set_fps_limit 120 (default: 0)", 120),
            ("cabeçalho\ndebug_set_fps_limit = 30", 30),
        ]:
            self.assertEqual(session._parse_limite(texto), esperado, texto)

    def test_formas_recusadas(self):
        for texto in ["unknown convar", "error code 2", "", None,
                      "gamescope 3.17.1", "falhou: errno 13"]:
            self.assertIsNone(session._parse_limite(texto), texto)
