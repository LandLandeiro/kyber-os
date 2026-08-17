"""
KYBER — a sessão gráfica, vista de fora dela.

O daemon roda como root, por unit de sistema. O limite de quadros não tem
arquivo de kernel: quem limita é o gamescope, e falar com ele é falar com
o compositor de uma SESSÃO DE USUÁRIO, por um socket Wayland dentro do
XDG_RUNTIME_DIR daquela pessoa. Este módulo é a travessia dessa fronteira,
e ela é feita uma vez, aqui, em vez de espalhada pelo eixo.

POR QUE O EIXO NÃO FOI PARA O LADO DA SESSÃO. Um ajudante sem privilégio
rodando dentro do gamescope seria mais limpo — processo da sessão fazendo
coisa de sessão. Esbarra numa restrição que decide sozinha: QUEM APLICA É
QUEM REPORTA. O state.json é escrito pelo daemon, e um aplicador do outro
lado precisaria de canal de escrita de volta, que é o socket que a
arquitetura adiou. Sem ele o eixo publicaria estado desconhecido para
sempre, e o editor e a tela 17 consomem estado por eixo. Além disso é a
saída do jogo que dispara a restauração, e só o daemon sabe dela.

COMO A SESSÃO É ENCONTRADA. Não por uid fixo, não por `id -nu 1000`: o
daemon já varre /proc, e acha um processo que está DENTRO da sessão para
tirar tudo dele de uma vez só — uid e gid do status, XDG_RUNTIME_DIR e o
nome do display do environ. Tudo de uma fonte só, coerente por
construção.

O marcador é `GAMESCOPE_WAYLAND_DISPLAY`. O gamescope-session-plus o
define depois que o gamescope reporta o socket, e tudo que ele inicia
herda — o Chromium do launcher inclusive. É a mesma disciplina da
descoberta de sensores: procurar o que existe, registrar o que se achou,
e reportar ausência em vez de chutar.

POR QUE DROPAR PRIVILÉGIO. O root conseguiria abrir o socket — Wayland
não autentica além da permissão de arquivo. Mas cliente Wayland rodando
como root deixa arquivo de root no runtime dir de outra pessoa, e
inverter privilégio para dentro de uma sessão de usuário é coisa a não
fazer mesmo quando funciona. A queda é `subprocess(user=, group=,
extra_groups=[])`: stdlib, setuid/setgid no filho entre o fork e o exec,
sem sudo, sem PAM, sem shell. `extra_groups=[]` porque sem isso o filho
guarda os grupos suplementares do root depois de trocar de uid.
"""

import re
import subprocess
from dataclasses import dataclass

BINARIO = "/usr/bin/gamescopectl"

# O convar que o gamescope expõe hoje. O prefixo `debug_` não é
# decoração: pode sumir ou trocar de assinatura numa atualização, e o
# Bazzite atualiza rápido. Por isso a presença é DETECTADA e nunca
# assumida — ver `Compositor.probe`.
CONVAR = "debug_set_fps_limit"

# Cliente Wayland esperando um compositor que sumiu é cliente que
# bloqueia. O laço publica a 1 Hz e `at` congelado é o que o launcher
# chama de LEITURA PARADA — travar aqui viraria falso positivo lá.
TIMEOUT_S = 2.0


@dataclass
class Session:
    uid: int
    gid: int
    runtime_dir: str
    display: str
    pid: int          # de onde a informação saiu, para o log
    via: str          # 'processo' | 'socket'

    @property
    def chave(self):
        """Identidade para saber se a sessão TROCOU, e não só mexeu."""
        return (self.uid, self.runtime_dir, self.display)


def _environ(fs, pid):
    bruto = fs.read_bytes(f"proc/{pid}/environ")
    if not bruto:
        return {}
    saida = {}
    for item in bruto.split(b"\0"):
        if b"=" in item:
            chave, _, valor = item.partition(b"=")
            saida[chave.decode("utf-8", "replace")] = valor.decode("utf-8", "replace")
    return saida


def _ids(fs, pid):
    """(uid, gid) reais do processo, do /proc/PID/status."""
    texto = fs.read(f"proc/{pid}/status") or ""
    uid = gid = None
    for linha in texto.splitlines():
        if linha.startswith("Uid:"):
            uid = int(linha.split()[1])
        elif linha.startswith("Gid:"):
            gid = int(linha.split()[1])
    return uid, gid


def _pids(fs):
    base = fs.path("proc")
    if not base.exists():
        return []
    return sorted(int(p.name) for p in base.iterdir() if p.name.isdigit())


def find_session(fs, log=None):
    """A sessão gráfica viva, ou None."""
    for pid in _pids(fs):
        ambiente = _environ(fs, pid)
        display = ambiente.get("GAMESCOPE_WAYLAND_DISPLAY")
        if not display:
            # `WAYLAND_DISPLAY` só serve como marcador quando aponta para
            # um socket do gamescope: numa sessão comum ele é o compositor
            # do desktop, que não entende o convar.
            candidato = ambiente.get("WAYLAND_DISPLAY", "")
            display = candidato if candidato.startswith("gamescope") else None
        runtime = ambiente.get("XDG_RUNTIME_DIR")
        if not display or not runtime:
            continue

        uid, gid = _ids(fs, pid)
        if uid is None or gid is None:
            continue
        sessao = Session(uid=uid, gid=gid, runtime_dir=runtime,
                         display=display, pid=pid, via="processo")
        if log:
            log(f"sessão   uid {uid} · {runtime}/{display} "
                f"(de {fs.show(fs.path(f'proc/{pid}'))})")
        return sessao

    # Sessão iniciada fora do gamescope-session-plus não tem o marcador, e
    # aí o socket é a única pista. O nome do arquivo É o nome do display, e
    # o dono dele dá uid e gid sem precisar abrir /etc/passwd.
    #
    # As sobras de `gamescope.XXXXXXX` que o session-plus deixa em
    # /run/user são DIRETÓRIOS e não casam com este glob — ver a nota de
    # higiene no README.
    for socket in fs.glob("run/user/*/gamescope-*"):
        try:
            estado = socket.stat()
        except OSError:
            continue
        sessao = Session(uid=estado.st_uid, gid=estado.st_gid,
                         runtime_dir=fs.show(socket.parent),
                         display=socket.name, pid=0, via="socket")
        if log:
            log(f"sessão   uid {estado.st_uid} · {fs.show(socket)} "
                "(pelo socket; sem marcador de ambiente)")
        return sessao

    if log:
        log("sessão   nenhuma — procurado GAMESCOPE_WAYLAND_DISPLAY no environ "
            "de /proc/*/ e sockets em /run/user/*/gamescope-*")
    return None


class SubprocessRunner:
    """A única chamada que sai do processo. Isolada para o teste gravá-la
    em vez de executá-la — nada disto roda num Mac."""

    def __call__(self, argv, env, uid, gid, timeout):
        try:
            fim = subprocess.run(
                argv, env=env, user=uid, group=gid, extra_groups=[],
                capture_output=True, text=True, timeout=timeout, check=False,
            )
            return fim.returncode, fim.stdout, fim.stderr
        except subprocess.TimeoutExpired:
            return None, "", f"tempo esgotado em {timeout}s"
        except OSError as erro:
            return None, "", f"{type(erro).__name__}: {erro.strerror or erro}"


class Compositor:
    """O gamescopectl, com a sessão embaixo do braço."""

    def __init__(self, fs, sessao=None, runner=None, binario=BINARIO):
        self.fs = fs
        self.sessao = sessao
        self.runner = runner or SubprocessRunner()
        self.binario = binario
        self.suporte = "unavailable"   # 'ok' | 'unavailable' | 'unsupported'
        self.nota = "sessão gráfica ainda não encontrada"
        self.getter = False

    # ------------------------------------------------------------------
    def _rodar(self, *args):
        """(codigo, saida, erro). `codigo` None quer dizer que nem rodou."""
        if self.sessao is None:
            return None, "", "sem sessão"
        # Ambiente mínimo e explícito: o filho não herda nada do daemon.
        # Caminho absoluto, nunca PATH — daemon root resolvendo PATH para
        # dentro do ambiente de um usuário é como se executa o binário
        # errado.
        env = {
            "XDG_RUNTIME_DIR": self.sessao.runtime_dir,
            "WAYLAND_DISPLAY": self.sessao.display,
            "PATH": "/usr/bin:/bin",
        }
        return self.runner([self.binario, *args], env,
                           self.sessao.uid, self.sessao.gid, TIMEOUT_S)

    # ------------------------------------------------------------------
    def probe(self):
        """Três camadas, todas empíricas, cada uma degradando com a razão.

        A terceira é a que responde ao prefixo `debug_`: procura o NOME do
        convar na saída do `help`, não a existência do binário. Se uma
        atualização do gamescope renomear ou remover o comando, isto pega,
        o eixo volta a `unsupported`, e o log guarda o que o `help` listou
        — o nome novo fica a uma linha de journal de distância."""
        if not self.fs.exists(self.binario):
            self.suporte, self.nota = "unsupported", f"{self.binario} não existe"
            self.getter = False
            return self.suporte

        if self.sessao is None:
            # `unavailable`, não `unsupported`: o eixo funciona, falta a
            # pré-condição AGORA. O launcher desenha as duas diferente.
            self.suporte = "unavailable"
            self.nota = "nenhuma sessão gráfica encontrada"
            self.getter = False
            return self.suporte

        codigo, saida, erro = self._rodar("help")
        if codigo != 0:
            self.suporte = "unavailable"
            self.nota = f"gamescopectl help falhou: {(erro or saida).strip()[:120]}"
            self.getter = False
            return self.suporte

        if CONVAR not in saida:
            self.suporte = "unsupported"
            self.nota = (f"gamescopectl responde mas não lista {CONVAR} — "
                         "o convar mudou de nome ou saiu")
            self.getter = False
            return self.suporte

        # Sistema de convar costuma imprimir o valor corrente quando
        # chamado pelado, e o do gamescope é de linhagem Source. Se
        # imprimir, este eixo ganha releitura como o governor tem; se não,
        # `applied` quer dizer só "o comando saiu 0", e a nota diz isso.
        self.getter = self.get_limit() is not None
        self.suporte = "ok"
        self.nota = None if self.getter else (
            "aplicado sem releitura: o gamescopectl não devolve o valor "
            "corrente, então o sucesso é o código de saída do comando"
        )
        return self.suporte

    # ------------------------------------------------------------------
    def get_limit(self):
        """Limite corrente em quadros, ou None quando não há como ler."""
        codigo, saida, _ = self._rodar(CONVAR)
        if codigo != 0:
            return None
        casa = re.search(r"-?\d+", saida or "")
        return int(casa.group()) if casa else None

    def set_limit(self, quadros):
        """None em caso de sucesso, ou a mensagem do erro."""
        codigo, saida, erro = self._rodar(CONVAR, str(int(quadros)))
        if codigo == 0:
            return None
        return (erro or saida or "gamescopectl falhou sem dizer por quê").strip()[:160]
