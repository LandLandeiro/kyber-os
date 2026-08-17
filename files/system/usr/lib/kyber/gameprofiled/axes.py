"""
KYBER — os quatro eixos do perfil de performance.

Eles NÃO têm a mesma viabilidade, e o state.json diz qual é qual em vez de
tratar todos como se funcionassem:

  governor   escreve em scaling_governor, lê de volta, confere. Validável
             de verdade.
  gpuLevel   escreve em power_dpm_force_performance_level e lê de volta. O
             AJUSTE é verificável; o EFEITO só tem evidência indireta.
  priority   nice e ionice na árvore de processos do jogo. Depende de haver
             jogo detectado.
  fpsLimit   não existe arquivo de kernel para isso. Quem limita quadro é o
             compositor. O daemon não tem onde escrever e não finge que tem.

Os estados que um eixo publica, e o que cada um significa para a tela:

  applied      escreveu e a releitura confirmou
  degraded     escreveu e voltou diferente — o kernel aceitou outra coisa
  failed       a escrita deu erro
  unavailable  o eixo existe mas falta pré-condição AGORA (sem PID de jogo,
               ou o valor pedido não está entre os que o driver oferece)
  unsupported  esta build não tem onde escrever. Nunca vai funcionar aqui
  observed     ninguém pediu nada; o valor é só o que a máquina tem

`available` é o que permite ao launcher não desenhar controle morto. Não é
enfeite: com intel_pstate em modo ativo, `scaling_available_governors` traz
só performance e powersave — o `schedutil` que o editor de perfil oferece
hoje não existe na máquina de teste.
"""

import os
import platform
import re
import sys
from dataclasses import dataclass, field

from . import score

CPUFREQ = "sys/devices/system/cpu/cpufreq/policy*"

# baixo/auto/alto do console → o vocabulário do amdgpu.
DPM = {"baixo": "low", "auto": "auto", "alto": "high"}
DPM_INVERSO = {v: k for k, v in DPM.items()}

# `tempo real` fica FORA de propósito. SCHED_FIFO num processo de jogo pode
# travar o console inteiro, e nesta versão não há proteção por cgroup para
# isso. Preferir não oferecer a oferecer e reinterpretar caladamente como
# "alta" — o rótulo prometeria uma coisa e a máquina faria outra.
NICE = {"padrão": 0, "alta": -5}
# Classe 2 é best-effort. A classe 1 (tempo real de E/S) precisa de
# CAP_SYS_ADMIN e deixa o resto do sistema sem disco enquanto o jogo lê.
IOPRIO = {"padrão": (2, 4), "alta": (2, 0)}

IOPRIO_WHO_PROCESS = 1
SYS_IOPRIO_SET = 251  # x86_64; o console e o dev box são os dois


@dataclass
class AxisState:
    requested: str = None
    current: str = None
    state: str = "observed"
    available: list = field(default_factory=list)
    note: str = None

    def to_json(self):
        saida = {
            "requested": self.requested,
            "current": self.current,
            "state": self.state,
            "available": list(self.available),
        }
        if self.note:
            saida["note"] = self.note
        return saida


class SystemOps:
    """As chamadas que mexem em processo, isoladas para o teste poder
    gravá-las em vez de executá-las. Nada aqui roda num Mac."""

    def setpriority(self, pid, nice):
        try:
            os.setpriority(os.PRIO_PROCESS, pid, nice)
            return None
        except OSError as erro:
            return f"{type(erro).__name__}: {erro.strerror or erro}"

    def set_ioprio(self, pid, classe, nivel):
        if sys.platform != "linux" or platform.machine() != "x86_64":
            return "ioprio_set indisponível nesta arquitetura"
        try:
            import ctypes

            libc = ctypes.CDLL(None, use_errno=True)
            valor = (classe << 13) | nivel
            if libc.syscall(SYS_IOPRIO_SET, IOPRIO_WHO_PROCESS, pid, valor) != 0:
                return f"ioprio_set: errno {ctypes.get_errno()}"
            return None
        except Exception as erro:  # ctypes falha de formas variadas
            return f"ioprio_set: {erro}"


# ----------------------------------------------------------------------
class Axis:
    key = None

    def __init__(self, fs):
        self.fs = fs

    def available(self):
        return []

    def read(self, ctx=None):
        return None

    def apply(self, value, ctx=None):
        raise NotImplementedError

    def restore(self, saved, ctx=None):
        return self.apply(saved, ctx)

    def _observed(self, ctx=None):
        return AxisState(current=self.read(ctx), state="observed",
                         available=self.available())


# ----------------------------------------------------------------------
class Governor(Axis):
    key = "governor"

    def _policies(self):
        return self.fs.glob(CPUFREQ)

    def driver(self):
        for politica in self._policies():
            nome = self.fs.read(politica / "scaling_driver")
            if nome:
                return nome
        return None

    def available(self):
        """O que o DRIVER oferece, intersectado com o que o console conhece.

        A interseção é o ponto. Com acpi-cpufreq os três existem; com
        intel_pstate ou amd_pstate em modo ativo só existem performance e
        powersave, e schedutil vira um controle que não faz nada."""
        for politica in self._policies():
            texto = self.fs.read(politica / "scaling_available_governors")
            if texto:
                oferecidos = set(texto.split())
                return [g for g in score.GOVERNOR if g in oferecidos]
        return []

    def read(self, ctx=None):
        valores = []
        for politica in self._policies():
            valor = self.fs.read(politica / "scaling_governor")
            if valor:
                valores.append(valor)
        if not valores:
            return None
        return valores[0]

    def _uniform(self):
        valores = {self.fs.read(p / "scaling_governor") for p in self._policies()}
        valores.discard(None)
        return len(valores) <= 1

    def _write_all(self, valor):
        erros = []
        politicas = self._policies()
        if not politicas:
            return ["não há /sys/devices/system/cpu/cpufreq/policy*"]
        for politica in politicas:
            erro = self.fs.write(politica / "scaling_governor", valor)
            if erro:
                erros.append(f"{politica.name}: {erro}")
        return erros

    def apply(self, value, ctx=None):
        disponiveis = self.available()
        if not disponiveis:
            return AxisState(requested=value, current=None, state="unsupported",
                             available=[],
                             note="máquina sem cpufreq — nenhum governor para escrever")

        if value not in disponiveis:
            # A falha mais provável das duas máquinas, e a mais silenciosa
            # se ninguém a publicar.
            return AxisState(
                requested=value, current=self.read(), state="unavailable",
                available=disponiveis,
                note=f"o driver {self.driver() or '?'} não oferece {value}; "
                     f"oferece {', '.join(disponiveis)}")

        erros = self._write_all(value)
        atual = self.read()
        if erros:
            return AxisState(requested=value, current=atual, state="failed",
                             available=disponiveis, note="; ".join(erros[:3]))
        if atual != value:
            return AxisState(requested=value, current=atual, state="degraded",
                             available=disponiveis,
                             note=f"escrito {value}, releitura devolveu {atual}")
        nota = None if self._uniform() else "políticas de cpufreq divergentes"
        return AxisState(requested=value, current=atual, state="applied",
                         available=disponiveis, note=nota)

    def restore(self, saved, ctx=None):
        """Restaura o valor bruto capturado, mesmo fora do vocabulário.

        A máquina podia estar em `ondemand` antes do jogo. Devolver
        `powersave` porque `ondemand` não está no modelo do console seria
        deixar a máquina diferente de como a encontramos."""
        if not saved:
            return self._observed()
        self._write_all(saved)
        return self._observed()


# ----------------------------------------------------------------------
class GpuLevel(Axis):
    key = "gpuLevel"

    def __init__(self, fs, gpu=None):
        super().__init__(fs)
        self.gpu = gpu

    def _node(self):
        if self.gpu is None:
            return None
        no = self.gpu.device / "power_dpm_force_performance_level"
        return no if self.fs.exists(no) else None

    def available(self):
        # O arquivo não anuncia os valores que aceita; o driver aceita este
        # conjunto desde sempre. Existindo o nó, os três existem.
        return list(DPM) if self._node() else []

    def read(self, ctx=None):
        no = self._node()
        if no is None:
            return None
        bruto = self.fs.read(no)
        if bruto is None:
            return None
        # `manual`, `profile_peak` e afins são estados legítimos do driver
        # que o console não sabe nomear. Devolver o bruto é mais honesto
        # que forçá-lo para dentro do vocabulário.
        return DPM_INVERSO.get(bruto, bruto)

    def apply(self, value, ctx=None):
        no = self._node()
        if no is None:
            return AxisState(requested=value, current=None, state="unsupported",
                             available=[],
                             note="nenhuma GPU amdgpu com power_dpm_force_performance_level")
        if value not in DPM:
            return AxisState(requested=value, current=self.read(), state="unavailable",
                             available=self.available(),
                             note=f"{value} não é um nível de DPM conhecido")

        erro = self.fs.write(no, DPM[value])
        atual = self.read()
        if erro:
            return AxisState(requested=value, current=atual, state="failed",
                             available=self.available(), note=erro)
        if atual != value:
            return AxisState(requested=value, current=atual, state="degraded",
                             available=self.available(),
                             note=f"escrito {DPM[value]}, releitura devolveu {atual}")
        return AxisState(requested=value, current=atual, state="applied",
                         available=self.available(),
                         note="o ajuste é verificável por releitura; o efeito no "
                              "clock só tem evidência indireta")

    def restore(self, saved, ctx=None):
        no = self._node()
        if no is None or not saved:
            return self._observed()
        self.fs.write(no, DPM.get(saved, saved))
        return self._observed()


# ----------------------------------------------------------------------
class FpsLimit(Axis):
    key = "fpsLimit"

    # Não há arquivo de kernel para limitar quadro. O limite é do
    # compositor, e o daemon não fala com ele. Ver o README: os três
    # caminhos possíveis passam todos pelo gamescope, e nenhum passa aqui.
    NOTA = ("sem superfície de kernel — quem limita quadro é o gamescope, "
            "e o daemon não tem canal com ele")

    def apply(self, value, ctx=None):
        return AxisState(requested=value, current=None, state="unsupported",
                         available=[], note=self.NOTA)

    def restore(self, saved, ctx=None):
        return AxisState(state="unsupported", available=[], note=self.NOTA)

    def _observed(self, ctx=None):
        return AxisState(state="unsupported", available=[], note=self.NOTA)


# ----------------------------------------------------------------------
class Priority(Axis):
    key = "priority"

    def __init__(self, fs, ops=None):
        super().__init__(fs)
        self.ops = ops or SystemOps()

    def available(self):
        return list(NICE)

    def read(self, ctx=None):
        """Lê o nice do processo mais antigo do jogo, campo 19 de stat."""
        pids = (ctx or {}).get("pids") or []
        for pid in pids:
            texto = self.fs.read(f"proc/{pid}/stat")
            if not texto or ")" not in texto:
                continue
            campos = texto[texto.rindex(")") + 1:].split()
            if len(campos) < 17:
                continue
            try:
                nice = int(campos[16])
            except ValueError:
                continue
            for rotulo, valor in NICE.items():
                if valor == nice:
                    return rotulo
            return str(nice)
        return None

    def apply(self, value, ctx=None):
        pids = (ctx or {}).get("pids") or []
        if not pids:
            # Sem jogo não há a quem dar prioridade. O eixo existe e é
            # implementável; falta a pré-condição, e isso é `unavailable`,
            # não `unsupported`.
            return AxisState(requested=value, current=None, state="unavailable",
                             available=self.available(),
                             note="sem processo de jogo detectado")
        if value not in NICE:
            return AxisState(requested=value, current=self.read(ctx),
                             state="unavailable", available=self.available(),
                             note=f"{value} não é aplicado por esta versão")

        erros, aplicados = [], 0
        for pid in pids:
            erro = self.ops.setpriority(pid, NICE[value])
            if erro:
                erros.append(f"pid {pid}: {erro}")
            else:
                aplicados += 1
            classe, nivel = IOPRIO[value]
            self.ops.set_ioprio(pid, classe, nivel)

        if not aplicados:
            return AxisState(requested=value, current=None, state="failed",
                             available=self.available(), note="; ".join(erros[:3]))

        nota = f"nice {NICE[value]} em {aplicados} de {len(pids)} processos"
        cgroup = (ctx or {}).get("cgroup")
        if cgroup:
            nota += f" do cgroup {cgroup}"
        if erros:
            nota += f" — {len(erros)} falharam"
        return AxisState(requested=value, current=self.read(ctx),
                         state="applied" if not erros else "degraded",
                         available=self.available(), note=nota)

    def restore(self, saved, ctx=None):
        # Não há o que restaurar: os processos que foram renicados são os
        # do jogo, e quando este eixo é restaurado eles já não existem.
        return AxisState(state="observed", available=self.available(),
                         note="nada a restaurar — os processos renicados eram do jogo")


def build(fs, gpu=None, ops=None):
    return {
        "governor": Governor(fs),
        "gpuLevel": GpuLevel(fs, gpu),
        "fpsLimit": FpsLimit(fs),
        "priority": Priority(fs, ops),
    }
