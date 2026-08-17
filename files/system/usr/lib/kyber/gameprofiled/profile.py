"""
KYBER — ciclo de vida do perfil.

Sem jogo o daemon NÃO aplica nada: observa e reporta — a exceção é a
restauração, que não é aplicar perfil, é desfazer o que foi aplicado.
Duas razões, e as duas são práticas. A primeira é não brigar com o power management do
Bazzite num console que passa a maior parte do tempo em repouso. A
segunda é que o launcher é uma UI a 60 fps rodando no mesmo hardware —
forçar DPM baixo no repouso deixaria a navegação da biblioteca travada
para economizar energia enquanto alguém está olhando para ela.

Jogo detectado → captura o valor corrente de cada eixo, aplica o perfil.
Jogo encerrado → escreve de volta o que capturou.

A restauração não é zelo: a tela 17b do launcher promete, com todas as
letras, que fechar o jogo "reverte o perfil de performance". Sem escrever
de volta, essa frase é mentira e o console fica presa em `performance`
até o próximo boot.
"""

from . import axes as axes_mod


class ProfileManager:
    # Eixos cujo valor a máquina guarda entre sessões e que por isso
    # precisam voltar ao que eram. A prioridade fica de fora: morre com o
    # processo do jogo. Os TRÊS não capturam da mesma forma — o governor e
    # o DPM leem o valor anterior do sysfs, o limite de quadros só captura
    # quando o compositor devolve o valor corrente, e sem isso restaura por
    # suposição. Ver a nota de FpsLimit em axes.py.
    RESTAURAVEIS = ("governor", "gpuLevel", "fpsLimit")

    def __init__(self, fs, config, gpu=None, ops=None, log=None,
                 apply_enabled=True, compositor=None):
        self.fs = fs
        self.config = config
        self.log = log or (lambda _: None)
        self.ops = ops
        self.apply_enabled = apply_enabled
        self.axes = axes_mod.build(fs, gpu, ops, compositor)
        self.appid = None
        self.capturado = {}
        self.estado = {chave: eixo._observed() for chave, eixo in self.axes.items()}

    def rebind_session(self, compositor):
        """Troca o eixo de quadros quando a sessão gráfica aparece ou muda.

        O daemon sobe no multi-user.target e a sessão só existe depois do
        login: no start não há compositor, e o eixo publica `unavailable`
        até haver. Sem esta troca ele ficaria em `unavailable` para sempre
        num console que fez login normalmente."""
        self.axes["fpsLimit"] = axes_mod.FpsLimit(self.fs, compositor)
        self._readotar("fpsLimit")

    def rebind_gpu(self, gpu):
        """Troca o eixo de GPU quando a redescoberta acha outro caminho.

        O nó de DPM mora sob o card, e o card muda de caminho quando o
        driver rebinda. Sem isto o eixo seguiria escrevendo num caminho que
        já não existe e reportando `failed` para sempre."""
        self.axes["gpuLevel"] = axes_mod.GpuLevel(self.fs, gpu)
        self._readotar("gpuLevel")

    def _readotar(self, chave):
        """Põe um eixo recém-trocado no estado em que ele deveria estar.

        Sem jogo é só observar. COM jogo é reaplicar, e isto não é zelo: o
        eixo pode ter acabado de se tornar aplicável — a sessão gráfica
        aparecendo depois de um reinício do daemon no meio de uma partida
        é o caso real. Esperar a próxima transição significaria não
        aplicar nunca nesta sessão.

        A captura anterior é refeita junto, porque ela veio do eixo velho:
        o valor lido de um card que rebindou, ou de um compositor que
        ainda não respondia, não é o que se quer devolver depois."""
        eixo = self.axes[chave]
        if self.appid is None:
            self.estado[chave] = eixo._observed()
            return
        if not self.apply_enabled:
            return
        self.capturado[chave] = eixo.read()
        pedido = self.config.profile_for(self.appid).get(chave)
        self.estado[chave] = eixo.apply(pedido)
        self.log(f"perfil   {chave:<9} {self.estado[chave].state:<12} "
                 f"reaplicado apos troca de eixo")

    # ------------------------------------------------------------------
    def sync(self, jogo):
        """Reconcilia o que está aplicado com o jogo em execução.

        Chamada a cada leitura. O trabalho real só acontece na TRANSIÇÃO —
        reaplicar o mesmo perfil a cada segundo escreveria em sysfs 86400
        vezes por dia sem mudar nada."""
        appid = jogo.appid if jogo else None

        if appid == self.appid:
            if appid is not None:
                # Só a prioridade é reavaliada: a árvore de processos do
                # jogo cresce depois do lançamento, e um filho que nasceu
                # tarde não herda o nice de quem já estava renicado.
                self._reaplicar_prioridade(jogo)
            return

        if self.appid is not None:
            self._restaurar()
        if appid is not None:
            self._aplicar(jogo)
        else:
            self.estado = {c: e._observed() for c, e in self.axes.items()}
        self.appid = appid

    # ------------------------------------------------------------------
    def _contexto(self, jogo):
        return {
            "pids": list(jogo.pids),
            "cgroup": f"steam_app_{jogo.appid}" if jogo.via == "cgroup" else None,
        }

    def _aplicar(self, jogo):
        perfil = self.config.profile_for(jogo.appid)
        contexto = self._contexto(jogo)

        if not self.apply_enabled:
            # --no-apply. O jogo continua sendo detectado e publicado; o
            # que não acontece é a escrita. O estado sai como `observed`
            # com o pedido preservado, para dar para ver o que ACONTECERIA
            # sem mexer numa máquina que ainda não se conhece.
            self.estado = {}
            for chave, eixo in self.axes.items():
                resultado = eixo._observed(contexto)
                resultado.requested = perfil.get(chave)
                resultado.note = "daemon em --no-apply; nada foi escrito"
                self.estado[chave] = resultado
            return

        # Captura ANTES de escrever. `read()` do limite de quadros devolve
        # None quando o compositor não tem getter, e é o próprio eixo que
        # decide o que None quer dizer na hora de restaurar — para o
        # governor quer dizer "não escreva nada"; para os quadros, "solte
        # o limite, por suposição".
        self.capturado = {
            chave: self.axes[chave].read() for chave in self.RESTAURAVEIS
        }

        self.estado = {}
        for chave, eixo in self.axes.items():
            self.estado[chave] = eixo.apply(perfil.get(chave), contexto)
            resultado = self.estado[chave]
            self.log(f"perfil   {chave:<9} {resultado.state:<12} "
                     f"pedido={resultado.requested} atual={resultado.current}"
                     + (f" — {resultado.note}" if resultado.note else ""))

    def _reaplicar_prioridade(self, jogo):
        if not self.apply_enabled:
            return
        eixo = self.axes["priority"]
        pedido = self.estado["priority"].requested
        if pedido is None:
            return
        self.estado["priority"] = eixo.apply(pedido, self._contexto(jogo))

    def _restaurar(self):
        if not self.apply_enabled:
            self.capturado = {}
            self.estado = {c: e._observed() for c, e in self.axes.items()}
            return
        for chave in self.RESTAURAVEIS:
            salvo = self.capturado.get(chave)
            resultado = self.axes[chave].restore(salvo)
            self.log(f"perfil   {chave:<9} restaurado para {salvo!r} "
                     f"(agora {resultado.current!r})")
        self.capturado = {}
        self.estado = {c: e._observed() for c, e in self.axes.items()}

    def shutdown(self):
        """Encerrar o daemon com jogo rodando também tem que devolver a
        máquina. Um console preso em `performance` porque o daemon foi
        reiniciado é o mesmo defeito por outra porta."""
        if self.appid is not None:
            self._restaurar()
            self.appid = None

    # ------------------------------------------------------------------
    def current_profile(self):
        """O perfil CORRENTE, para o escore da régua.

        Sai do que a máquina tem, não do que se pediu: a régua descreve o
        estado da máquina, e um eixo pedido mas não aplicado não move
        nada."""
        return {chave: estado.current for chave, estado in self.estado.items()}

    def to_json(self):
        return {
            "origin": self.config.origin,
            "applies": str(self.appid) if self.appid is not None else "idle",
            "axes": {c: e.to_json() for c, e in self.estado.items()},
        }
