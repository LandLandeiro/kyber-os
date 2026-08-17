"""
KYBER — laço do gameprofiled.

Descobre uma vez, publica uma vez por segundo, restaura ao sair.

A PRIMEIRA publicação espera o próximo instante X,5 s em vez de sair na
hora. Custa até um segundo de SEM LEITURA no boot — que é a verdade, não
um contorno — e em troca garante que duas publicações nunca caiam no
mesmo segundo inteiro. Ver a armadilha 2 em state.py.
"""

import argparse
import signal
import sys
import threading
import time

from . import VERSION, games, sensors, session as sessao_mod, state
from .config import Config
from .fs import Fs
from .profile import ProfileManager
from .state import Publisher, Reading


class SimulatedOps:
    """O que substitui as chamadas de processo quando a raiz é simulada.

    `--root` troca o filesystem, e só ele. `setpriority` e `ioprio_set`
    falam com o kernel de verdade por PID, e os PIDs de uma árvore falsa
    são números que EXISTEM na máquina de quem está inspecionando — rodar
    a demonstração do README renicaria três processos aleatórios do host.

    Então raiz simulada não toca em processo nenhum, e o eixo de
    prioridade reporta a recusa em vez de fingir que aplicou."""

    MOTIVO = "raiz simulada (--root); nenhum processo real foi tocado"

    def setpriority(self, pid, nice):
        return self.MOTIVO

    def set_ioprio(self, pid, classe, nivel):
        return self.MOTIVO


class SimulatedRunner:
    """O mesmo perigo do SimulatedOps, por outra porta, e pior.

    `--root` troca o filesystem e só ele. O caminho do gamescopectl é
    ABSOLUTO — tem que ser, senão o daemon resolveria PATH para dentro do
    ambiente de um usuário — e o uid vem de um /proc falso. Numa máquina
    Linux de verdade, rodar a demonstração com uma árvore falsa que
    contenha um marcador de gamescopectl executaria o binário REAL contra
    a sessão REAL de quem está inspecionando, mudando o limite de quadros
    da tela em que a pessoa está olhando.

    Raiz simulada não fala com compositor nenhum."""

    MOTIVO = "raiz simulada (--root); nenhum compositor real foi tocado"

    def __call__(self, argv, env, uid, gid, timeout):
        return None, "", self.MOTIVO

# Depois de tantas leituras vazias seguidas de um sensor que ANTES
# respondia, o caminho provavelmente morreu — driver recarregado, GPU
# suspensa, dispositivo rebindado. Redescobrir é barato; varrer o sysfs a
# cada segundo não seria.
FALHAS_ATE_REDESCOBRIR = 3

# De quanto em quanto tempo o estimado e o medido aparecem lado a lado no
# log. Por leitura seria uma linha por segundo; só no start, uma linha por
# boot, e ninguém repara que a régua está errada olhando uma vez.
COMPARACAO_S = 600

# De quanto em quanto tempo se varre /proc atrás de uma sessão gráfica
# quando não há nenhuma conhecida. A varredura lê o environ de cada
# processo, o que é caro demais para uma vez por segundo — e a sessão
# aparece uma vez por boot. Com sessão conhecida, a checagem é uma leitura
# só, do /proc do processo que a revelou.
BUSCA_SESSAO_S = 15


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="gameprofiled", description=__doc__)
    p.add_argument("--root", default="/",
                   help="raiz do filesystem; existe para teste")
    p.add_argument("--state", default=state.CAMINHO)
    p.add_argument("--config", default=None)
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--once", action="store_true",
                   help="publica uma vez e sai")
    p.add_argument("--no-apply", action="store_true",
                   help="observa e publica sem escrever em sysfs; para a "
                        "primeira execução numa máquina nova")
    return p.parse_args(argv)


def make_log(saida=sys.stderr):
    # Sem carimbo de tempo: o journald põe o dele, e dois na mesma linha
    # só ocupam largura.
    def log(mensagem):
        print(mensagem, file=saida, flush=True)
    return log


class Daemon:
    def __init__(self, opcoes, log=None, relogio=time.time,
                 cronometro=time.monotonic, runner=None):
        """Dois relógios, e não é descuido.

        `relogio` é tempo de parede: carimba o `at` que o launcher compara
        e ancora a fase da publicação, que precisa casar com o mtime que o
        darkhttpd serve. `cronometro` é monotônico e mede INTERVALO — é o
        que o contador de energia do RAPL divide para virar potência.
        Medir intervalo com o relógio de parede daria potência negativa ou
        absurda toda vez que o NTP ajustasse o horário."""
        self.opcoes = opcoes
        self.log = log or make_log()
        self.relogio = relogio
        self.cronometro = cronometro
        self.fs = Fs(opcoes.root)

        # O intervalo é travado em 1 s no piso. Publicar mais rápido faz o
        # If-Modified-Since do darkhttpd devolver 304 e o launcher declarar
        # LEITURA PARADA num console saudável.
        self.interval = max(1.0, float(opcoes.interval))
        if self.interval != opcoes.interval:
            self.log(f"daemon   intervalo pedido {opcoes.interval}s elevado para "
                     f"{self.interval}s — abaixo disso o cache do darkhttpd "
                     "devolve 304 e o cliente perde atualização")

        argumentos = {"fs": self.fs, "log": self.log}
        if opcoes.config:
            argumentos["caminho"] = opcoes.config
        self.config = Config(**argumentos)
        self.publisher = Publisher(self.fs, opcoes.state)

        self.started_at = int(self.relogio() * 1000)
        self.gpu = None
        self.sensors = {}
        self.falhas = {}
        self.respondeu = set()
        self.ultima_comparacao = None

        self.discover()
        simulando = str(opcoes.root) != "/"
        self.runner = runner or (SimulatedRunner() if simulando
                                 else sessao_mod.SubprocessRunner())
        self.sessao = None
        self.compositor = sessao_mod.Compositor(self.fs, runner=self.runner)
        self._ultima_busca = None
        # Sonda antes de procurar sessão: a camada do binário se resolve
        # sem sessão nenhuma, e uma máquina sem gamescopectl é
        # `unsupported` desde o primeiro segundo em vez de ficar
        # `unavailable` esperando um login que não vai mudar nada.
        self._sondar()
        self.buscar_sessao(inicial=True)

        if simulando:
            self.log("daemon   raiz simulada em " + str(opcoes.root)
                     + " — nenhum processo nem compositor real será tocado")
        self.manager = ProfileManager(
            self.fs, self.config, self.gpu,
            ops=SimulatedOps() if simulando else None,
            log=self.log, apply_enabled=not opcoes.no_apply,
            compositor=self.compositor)
        self._log_eixos()

    # ------------------------------------------------------------------
    def discover(self):
        self.gpu = sensors.find_gpu(self.fs, self.log)
        self.sensors = {
            "cpuTemp": sensors.find_cpu_temp(self.fs, self.log),
            "gpuTemp": sensors.find_gpu_temp(self.fs, self.gpu, self.log),
            "cpuWatts": sensors.find_cpu_power(self.fs, self.log, self.cronometro),
            "gpuWatts": sensors.find_gpu_power(self.fs, self.gpu, self.log),
        }
        self.falhas = {nome: 0 for nome in self.sensors}
        self.respondeu = set()

        for nome, sensor in self.sensors.items():
            fonte = sensor.source
            if fonte and fonte.kind == "measured":
                rotulo = f", {fonte.label}" if fonte.label else ""
                self.log(f"sensor {nome:<9} {fonte.path} ({fonte.driver}{rotulo})")

    # ------------------------------------------------------------------
    def buscar_sessao(self, inicial=False):
        """Acha (ou reacha) a sessão gráfica e re-sonda o compositor.

        O daemon sobe no multi-user.target e a sessão só existe depois do
        login, então no start não há o que achar — e isso não é falha, é
        ordem de boot. A busca se repete de tempos em tempos até aparecer.

        A checagem barata vem primeiro: se o processo que revelou a sessão
        continua vivo e continua anunciando o mesmo display, não há o que
        procurar. Só quando ele some é que se varre /proc de novo, porque
        varrer significa ler o environ de cada processo da máquina."""
        agora = self.relogio()

        if self.sessao and self._sessao_viva():
            return False
        if not inicial and self._ultima_busca is not None \
                and agora - self._ultima_busca < BUSCA_SESSAO_S:
            return False
        self._ultima_busca = agora

        achada = sessao_mod.find_session(self.fs, self.log)
        if achada is None and self.sessao is None:
            return False
        if achada is not None and self.sessao is not None \
                and achada.chave == self.sessao.chave:
            return False

        self.sessao = achada
        self.compositor = sessao_mod.Compositor(self.fs, achada, self.runner)
        self._sondar()

        if getattr(self, "manager", None) is not None:
            self.manager.rebind_session(self.compositor)
        return True

    def _sondar(self):
        suporte = self.compositor.probe()
        self.log(f"eixo   fpsLimit  {suporte}"
                 + (" · com releitura" if self.compositor.getter else "")
                 + (f" — {self.compositor.nota}" if self.compositor.nota else ""))
        return suporte

    def _sessao_viva(self):
        """O processo que revelou a sessão ainda está lá e ainda é ela."""
        if self.sessao.pid == 0:
            return self.fs.exists(f"{self.sessao.runtime_dir}/{self.sessao.display}")
        ambiente = sessao_mod._environ(self.fs, self.sessao.pid)
        return ambiente.get("GAMESCOPE_WAYLAND_DISPLAY") == self.sessao.display \
            or ambiente.get("WAYLAND_DISPLAY") == self.sessao.display

    def _log_eixos(self):
        for chave, eixo in self.manager.axes.items():
            disponiveis = eixo.available()
            if chave == "governor":
                extra = f"driver {eixo.driver() or '?'}; "
            else:
                extra = ""
            self.log(f"eixo   {chave:<9} {extra}"
                     + (f"disponíveis: {', '.join(disponiveis)}"
                        if disponiveis else "NÃO APLICÁVEL nesta máquina"))
        if self.opcoes.no_apply:
            self.log("daemon   --no-apply: nada será escrito em sysfs")

    # ------------------------------------------------------------------
    def ler_sensores(self):
        leituras = {}
        for nome, sensor in self.sensors.items():
            valor = sensor.read()
            leituras[nome] = Reading(valor, sensor.source)

            if valor is not None:
                self.respondeu.add(nome)
                self.falhas[nome] = 0
            elif nome in self.respondeu:
                # Só conta como falha depois de o sensor ter respondido ao
                # menos uma vez: a primeira leitura de um contador de
                # energia é vazia por construção, não por defeito.
                self.falhas[nome] += 1
        return leituras

    def talvez_redescobrir(self):
        mortos = [n for n, c in self.falhas.items() if c >= FALHAS_ATE_REDESCOBRIR]
        if not mortos:
            return
        self.log(f"sensor   {', '.join(mortos)} parou de responder; redescobrindo")
        self.discover()
        self.manager.rebind_gpu(self.gpu)

    def soma_medida(self, leituras):
        """Soma dos sensores de potência, ou None se algum deles devia ter
        respondido e não respondeu.

        Soma incompleta é pior que soma nenhuma: ela tem cara de total. Na
        primeira leitura o contador de energia do RAPL é vazio por
        construção, e sem esta regra a comparação sairia contando só a GPU
        e depois ficaria dez minutos em silêncio com o número errado no
        log. Sensor que morreu de vez vira `absent` na redescoberta e sai
        da conta — a soma volta a estar completa sem ele."""
        total, esperados = 0.0, 0
        for nome in ("cpuWatts", "gpuWatts"):
            leitura = leituras.get(nome)
            if not leitura or not leitura.source or leitura.source.kind != "measured":
                continue
            if leitura.value is None:
                return None
            esperados += 1
            total += leitura.value
        return total if esperados else None

    def comparar_watts(self, documento, soma, agora):
        """Põe estimado e medido na mesma linha do log, de tempos em tempos.

        Não é para o usuário: é para quem olha esta régua todo dia não se
        acostumar com um número que ninguém conferiu."""
        if soma is None:
            return
        if (self.ultima_comparacao is not None
                and agora - self.ultima_comparacao < COMPARACAO_S):
            return
        self.ultima_comparacao = agora
        calibrada = "calibrada" if self.config.curve()["calibrated"] else "NÃO calibrada"
        self.log(f"watts    estimado {documento['watts']} W (curva {calibrada}) "
                 f"contra {soma:.1f} W medidos nos componentes "
                 f"(cpu {documento['cpuWatts']}, gpu {documento['gpuWatts']}) — "
                 "os componentes não cobrem o consumo do console")

    # ------------------------------------------------------------------
    def tick(self):
        agora = self.relogio()
        self.config.reload()
        self.buscar_sessao()

        jogo = games.find_running_game(self.fs, self.log)
        self.manager.sync(jogo)

        leituras = self.ler_sensores()
        soma = self.soma_medida(leituras)

        documento = state.build(
            at=int(agora * 1000),
            interval_ms=int(self.interval * 1000),
            readings=leituras,
            curve=self.config.curve(),
            manager=self.manager,
            game=jogo,
            version=VERSION,
            started_at=self.started_at,
            measured_sum=soma,
        )
        self.publisher.publish(documento)
        self.comparar_watts(documento, soma, agora)
        self.talvez_redescobrir()
        return documento

    def run(self, parar=None):
        parar = parar or threading.Event()
        while not parar.is_set():
            espera = state.next_publish(self.relogio()) - self.relogio()
            if parar.wait(max(0.0, espera)):
                break
            self.tick()
            if self.opcoes.once:
                break

    def shutdown(self):
        self.manager.shutdown()

        # --once existe para se OLHAR o resultado; apagar o arquivo logo
        # depois de escrevê-lo deixaria o comando sem saída nenhuma.
        if self.opcoes.once:
            return

        # O systemd apaga /run/kyber ao parar a unit, mas uma parada suja
        # deixaria o arquivo para trás e o launcher leria LEITURA PARADA de
        # um daemon que não existe mais. SEM LEITURA é o estado correto.
        self.publisher.remove()


def main(argv=None):
    opcoes = parse_args(argv)
    log = make_log()
    daemon = Daemon(opcoes, log)

    parar = threading.Event()
    for sinal in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sinal, lambda *_: parar.set())

    try:
        daemon.run(parar)
    finally:
        daemon.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
