"""
KYBER — ciclo de vida do perfil.

Sem jogo o daemon NÃO aplica nada: observa e reporta. Duas razões, e as
duas são práticas. A primeira é não brigar com o power management do
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
    def __init__(self, fs, config, gpu=None, ops=None, log=None):
        self.fs = fs
        self.config = config
        self.log = log or (lambda _: None)
        self.axes = axes_mod.build(fs, gpu, ops)
        self.appid = None
        self.capturado = {}
        self.estado = {chave: eixo._observed() for chave, eixo in self.axes.items()}

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

        # Captura ANTES de escrever. Só o que a máquina guarda entre
        # sessões precisa voltar: prioridade morre com o processo, e
        # fpsLimit nunca chegou a ser escrito.
        self.capturado = {
            chave: self.axes[chave].read() for chave in ("governor", "gpuLevel")
        }

        self.estado = {}
        for chave, eixo in self.axes.items():
            self.estado[chave] = eixo.apply(perfil.get(chave), contexto)
            resultado = self.estado[chave]
            self.log(f"perfil   {chave:<9} {resultado.state:<12} "
                     f"pedido={resultado.requested} atual={resultado.current}"
                     + (f" — {resultado.note}" if resultado.note else ""))

    def _reaplicar_prioridade(self, jogo):
        eixo = self.axes["priority"]
        pedido = self.estado["priority"].requested
        if pedido is None:
            return
        self.estado["priority"] = eixo.apply(pedido, self._contexto(jogo))

    def _restaurar(self):
        for chave in ("governor", "gpuLevel"):
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
