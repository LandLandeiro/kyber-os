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

import errno
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


# Duas coisas na unit fazem a queda de privilégio falhar, e as duas
# chegam aqui como o mesmo EPERM sem contexto. Custaram uma ida ao
# hardware para serem achadas; a pista fica escrita para não custarem uma
# segunda.
DICA_EPERM = (
    "setuid/setgid para o uid da sessão foi recusado — a unit precisa de "
    "CAP_SETUID e CAP_SETGID no CapabilityBoundingSet (o kernel exige as "
    "duas mesmo DESCENDO de privilégio), e de ProtectHome diferente de "
    "`yes`, que esvazia /run/user junto com /home"
)


def _juntar(saida, erro):
    """Os dois canais, sempre.

    O `gamescopectl help` escreve a lista de convars em STDERR. Assumir
    stdout custou um falso negativo no hardware: o convar existia e a
    sondagem disse que não. Nenhuma leitura deste módulo pode escolher um
    canal só — não há por que supor de qual lado uma ferramenta fala."""
    return "\n".join(parte for parte in (saida, erro) if parte)


def _impressao(texto):
    """Quantas linhas o comando devolveu e quantas citam quadros.

    É o que separa "o convar sumiu" de "estou lendo o lugar errado" na
    próxima vez, porque as duas produzem a mesma frase."""
    linhas = [l for l in texto.splitlines() if l.strip()]
    citam = [l.strip() for l in linhas if "fps" in l.lower()]
    resumo = f"saída com {len(linhas)} linhas, {len(citam)} citando fps"
    return f"{resumo}: {'; '.join(citam[:2])[:80]}" if citam else resumo


# Duas formas, e nada além delas. Qualquer outra saída vira None, e o eixo
# fica sem releitura em vez de ganhar uma releitura inventada.
_SO_NUMERO = re.compile(r"-?\d+")
_NOMEADO = re.compile(rf"{re.escape(CONVAR)}\s*[=:]?\s*(-?\d+)\b")


def _parse_limite(texto):
    """Um inteiro, e só quando a saída é inequívoca.

    Da última linha para a primeira: se a ferramenta imprimir cabeçalho, o
    valor está no fim."""
    for linha in reversed((texto or "").splitlines()):
        linha = linha.strip()
        if not linha:
            continue
        if _SO_NUMERO.fullmatch(linha):
            return int(linha)
        casa = _NOMEADO.match(linha)
        if casa:
            return int(casa.group(1))
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
            return None, "", descrever(erro)


def descrever(erro):
    """A mensagem do erro, com a pista quando ela se aplica.

    EPERM aqui quase nunca é o gamescopectl recusando: é o filho morrendo
    entre o fork e o exec, antes de o binário existir no processo. A
    mensagem crua diz `Operation not permitted` e não diz de onde veio."""
    base = f"{type(erro).__name__}: {erro.strerror or erro}"
    if getattr(erro, "errno", None) == errno.EPERM:
        return f"{base} — {DICA_EPERM}"
    return base


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
        o eixo volta a `unsupported`, e a nota guarda o que o `help`
        listou — o nome novo fica a uma linha de journal de distância.

        A CAMADA 3 JÁ REPROVOU UMA VEZ, E POR CULPA DELA MESMA. O
        `gamescopectl help` escreve a lista em STDERR, e a sondagem lia só
        stdout: o convar existia e a resposta foi `unsupported`. Vale
        registrar o que isso mostrou, porque as duas leituras são
        diferentes.

        O MECANISMO ACERTOU. Diante de uma verificação que não passou, ele
        voltou a `unsupported` com a razão escrita, em vez de aplicar
        assim mesmo e virar no-op silencioso — que é exatamente o que a
        defesa em camadas existe para impedir. Um falso negativo custa uma
        funcionalidade desligada e uma linha de log; um falso positivo
        custaria um botão no editor que não faz nada e ninguém descobre.
        A camada errou o canal, não o julgamento.

        MAS A MENSAGEM ERA A MESMA que a de um convar REALMENTE removido,
        e quem ler o journal na próxima vez precisa distinguir os dois.
        Por isso a nota carrega agora a impressão digital do que se viu:
        quantas linhas o `help` devolveu e quantas citam `fps`.

          0 linhas          não é o convar que sumiu, é a leitura que está
                            errada — canal, ambiente ou binário
          N linhas, 0 fps   o convar saiu de vez
          N linhas, M fps   foi renomeado, e os candidatos vão no log"""
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
        texto = _juntar(saida, erro)

        # Conteúdo antes de código de saída: uma ferramenta que escreve
        # `help` em stderr é uma ferramenta que pode muito bem sair com
        # código diferente de zero num `help`. O que importa é se ESTA
        # build conhece o convar, e isso está no texto.
        if CONVAR in texto:
            self.getter = self.get_limit() is not None
            self.suporte = "ok"
            self.nota = None if self.getter else (
                "aplicado sem releitura: o gamescopectl não devolve o valor "
                "corrente, então o sucesso é o código de saída do comando"
            )
            return self.suporte

        self.getter = False

        if codigo is None or not texto.strip():
            # Não rodou, ou rodou e não disse nada. Não dá para acusar o
            # convar de ter sumido sem ter visto a lista.
            self.suporte = "unavailable"
            motivo = (erro or saida).strip()[:120] or "sem saída em nenhum canal"
            self.nota = f"gamescopectl help não respondeu: {motivo}"
            return self.suporte

        self.suporte = "unsupported"
        self.nota = (f"gamescopectl responde e não lista {CONVAR} "
                     f"({_impressao(texto)}) — o convar mudou de nome ou saiu")
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
        """Limite corrente em quadros, ou None quando não há como ler.

        Lê os dois canais, e o código de saída não desqualifica: quem
        escreve `help` em stderr também pode escrever o valor lá, e pode
        não zerar o código.

        A leitura é ESTRITA de propósito — ver `_parse_limite`. Releitura
        errada é pior que releitura nenhuma: ela alimenta a comparação do
        `apply`, e um número pescado de uma mensagem de erro viraria
        `degraded` inventado, ou pior, um `applied` por coincidência."""
        codigo, saida, erro = self._rodar(CONVAR)
        if codigo is None:
            return None
        return _parse_limite(_juntar(saida, erro))

    def set_limit(self, quadros):
        """None em caso de sucesso, ou a mensagem do erro.

        Aqui o código de saída manda, e é o único sinal que há. O risco de
        um `exit 0` que não aplicou nada está declarado na nota do eixo
        quando não há getter — e é a camada 3 que o mantém pequeno: se o
        `help` lista o convar, o setter existe."""
        codigo, saida, erro = self._rodar(CONVAR, str(int(quadros)))
        if codigo == 0:
            return None
        texto = _juntar(saida, erro).strip()
        return (texto or "gamescopectl falhou sem dizer por quê")[:160]
