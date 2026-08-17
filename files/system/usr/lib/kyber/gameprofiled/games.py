"""
KYBER — detecção de jogo em execução.

Varredura de /proc, e não aviso do launcher. A razão é que o jogo pode
ser lançado por fora do launcher — pela Steam em modo desktop, por um
atalho, por linha de comando — e um daemon que só sabe do que o launcher
lhe contou aplicaria perfil em metade dos casos.

O QUE SE ENCONTRA DE FATO NA ÁRVORE.

A Steam moderna põe cada título num cgroup próprio, e o nome dele carrega
o AppID:

  /user.slice/user-1000.slice/user@1000.service/.../steam_app_553850

Isso é melhor que ler linha de comando por três motivos: /proc/PID/cgroup
é legível por qualquer um (environ de processo alheio exige
CAP_SYS_PTRACE), o cgroup pega a ÁRVORE inteira e não só o reaper, e a
lista de PIDs que sai daí é exatamente a que o eixo de prioridade precisa
renicar.

A árvore por baixo é reaper → wrapper do Proton → binário do jogo, com
número variável de degraus no meio (pressure-vessel, wine, o launcher
próprio do título). Não se tenta adivinhar qual deles "é o jogo": todos
pertencem à sessão e todos entram na lista.

Dois fallbacks, para quando o cgroup não estiver lá — Steam antiga, ou um
título rodando fora do escopo que a Steam cria:

  environ   SteamAppId=<appid>, herdado por todo descendente do lançamento
  cmdline   `SteamLaunch AppId=<appid>`, que identifica o reaper

`startedAt` sai do processo MAIS ANTIGO do grupo, que é o momento em que
o lançamento começou — é o que a tela 17 conta como duração da sessão.
"""

import os
import re
from dataclasses import dataclass, field

CGROUP = re.compile(r"steam_app_(\d+)")
ENVIRON = re.compile(r"\bSteamAppId=(\d+)")
CMDLINE = re.compile(r"SteamLaunch\s+AppId=(\d+)")


@dataclass
class Game:
    appid: int
    pids: list = field(default_factory=list)
    started_at: int = None  # epoch ms
    via: str = None  # cgroup | environ | cmdline

    def to_json(self):
        return {"appid": self.appid, "startedAt": self.started_at}


def _pids(fs):
    for entrada in fs.path("proc").iterdir() if fs.path("proc").exists() else []:
        if entrada.name.isdigit():
            yield int(entrada.name)


def _appid_of(fs, pid):
    """(appid, por onde) do processo, ou (None, None).

    A ordem é a de confiança e de custo: cgroup primeiro porque é barato e
    não precisa de privilégio; environ depois, que é onde o AppID sobrevive
    a qualquer profundidade da árvore; cmdline por último, que só pega o
    reaper."""
    base = fs.path(f"proc/{pid}")

    cgroup = fs.read(base / "cgroup")
    if cgroup:
        casa = CGROUP.search(cgroup)
        if casa:
            return int(casa.group(1)), "cgroup"

    # NUL vira espaço: os dois arquivos são listas separadas por NUL, e o
    # que se procura neles é texto.
    bruto = fs.read_bytes(base / "environ")
    if bruto:
        casa = ENVIRON.search(bruto.replace(b"\0", b" ").decode("utf-8", "replace"))
        if casa:
            return int(casa.group(1)), "environ"

    bruto = fs.read_bytes(base / "cmdline")
    if bruto:
        casa = CMDLINE.search(bruto.replace(b"\0", b" ").decode("utf-8", "replace"))
        if casa:
            return int(casa.group(1)), "cmdline"

    return None, None


def boot_time(fs):
    """Epoch em que a máquina subiu, de /proc/stat.

    Necessário porque o kernel data o início de um processo em ticks desde
    o boot, não em epoch. Sem isto não há como dizer há quanto tempo a
    sessão está aberta."""
    texto = fs.read("proc/stat") or ""
    for linha in texto.splitlines():
        if linha.startswith("btime "):
            try:
                return int(linha.split()[1])
            except (ValueError, IndexError):
                return None
    return None


def start_time(fs, pid, btime, hz):
    """Início do processo em epoch ms.

    Campo 22 de /proc/PID/stat. O nome do executável é o campo 2, vem
    entre parênteses e pode conter espaço E parêntese — `(Hollow (K) )` é
    um nome válido —, então o corte é no ÚLTIMO fecha-parênteses, nunca por
    split simples."""
    if btime is None or not hz:
        return None
    texto = fs.read(f"proc/{pid}/stat")
    if not texto or ")" not in texto:
        return None
    campos = texto[texto.rindex(")") + 1:].split()
    # campos[0] é o campo 3 (estado); o campo 22 fica em campos[19].
    if len(campos) < 20:
        return None
    try:
        ticks = int(campos[19])
    except ValueError:
        return None
    return int((btime + ticks / hz) * 1000)


def find_running_game(fs, log=None, hz=None):
    """O jogo em execução, ou None.

    Com mais de um, fica o de lançamento mais recente — é o que a pessoa
    acabou de abrir. O caso é logado porque perfil aplicado a um enquanto
    o outro roda é uma explicação que ninguém vai achar sozinho."""
    if hz is None:
        hz = os.sysconf("SC_CLK_TCK")

    grupos = {}
    for pid in _pids(fs):
        appid, via = _appid_of(fs, pid)
        if appid is None:
            continue
        jogo = grupos.setdefault(appid, Game(appid=appid, via=via))
        jogo.pids.append(pid)
        if via == "cgroup":
            jogo.via = "cgroup"  # a via mais confiável que apareceu no grupo

    if not grupos:
        return None

    btime = boot_time(fs)
    for jogo in grupos.values():
        jogo.pids.sort()
        inicios = [start_time(fs, pid, btime, hz) for pid in jogo.pids]
        inicios = [i for i in inicios if i is not None]
        # O mais antigo do grupo: o lançamento começou com o reaper, não
        # com o binário do jogo, que sobe alguns segundos depois.
        jogo.started_at = min(inicios) if inicios else None

    escolhido = max(grupos.values(), key=lambda j: (j.started_at or 0, j.appid))
    if len(grupos) > 1 and log:
        outros = ", ".join(str(a) for a in sorted(grupos) if a != escolhido.appid)
        log(f"jogo     {len(grupos)} sessões em execução; perfil vai para "
            f"{escolhido.appid}, ignorando {outros}")
    return escolhido
