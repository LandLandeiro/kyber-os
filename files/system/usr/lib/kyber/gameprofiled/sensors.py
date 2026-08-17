"""
KYBER — descoberta e leitura de sensores.

NENHUM CAMINHO É FIXO, e isso não é zelo excessivo. `hwmonN` é ordem de
bind de driver, não identidade: o mesmo sensor troca de número entre
boots, e as duas máquinas do projeto não têm nem os mesmos drivers. A de
teste é i5-13400F (coretemp, sem iGPU) com RX 7600 (amdgpu discreto); o
console é Ryzen 5 5700G (k10temp) com Vega 8 integrada. Caminho fixo
funcionaria numa e mediria a coisa errada — ou nada — na outra.

A busca é por NOME de driver e por RÓTULO de sensor, e a GPU é procurada
a partir de /sys/class/drm/card*/device/hwmon/ em vez da lista plana de
hwmon: com duas GPUs amdgpu o nome é ambíguo, e o caminho pelo card
amarra o sensor à placa.

Ausência é publicada como ausência. Zero é um valor, e valor é a
afirmação de que alguém mediu.
"""

import re
import time
from dataclasses import dataclass, field

# Ordem de preferência. `zenpower` é fora da árvore e alguns donos de
# Ryzen o instalam no lugar do k10temp; se estiver carregado, é ele que
# tem o sensor bom.
CPU_TEMP_DRIVERS = ("k10temp", "zenpower", "coretemp")

# `Tdie` antes de `Tctl` porque Tctl carrega offset em algumas famílias
# AMD (nas de mesa é o mesmo número, nas Threadripper são 27 °C de
# diferença). `Package id 0` é o rótulo do coretemp para o pacote inteiro,
# que é o que o header do console quer mostrar — não o núcleo mais quente.
CPU_TEMP_LABELS = ("Tdie", "Tctl", "Package id 0", "Tccd1")

# Fallback quando não há hwmon de CPU nenhum.
CPU_THERMAL_ZONES = ("x86_pkg_temp", "k10temp", "acpitz")

# `edge` é o sensor de borda do die e é o que as ferramentas de sistema
# chamam de "temperatura da GPU". `junction` é o hotspot: mais alto,
# é ele que estrangula o clock, e mostrá-lo no header assustaria sem
# ensinar. Fica como segunda opção porque em algumas placas é o único.
GPU_TEMP_LABELS = ("edge", "junction", "mem")

_CARD = re.compile(r"^card\d+$")
_RAPL_PACKAGE = re.compile(r"^intel-rapl:\d+$")


@dataclass
class Source:
    """De onde veio um número — ou por que não veio nenhum.

    Vai inteira para o state.json, INCLUSIVE quando não há sensor: `kind:
    absent` com a nota dizendo onde se procurou. Campo que some sem
    explicação obriga quem depura a abrir o journal para descobrir se o
    traço no header é falta de sensor, driver não carregado ou defeito.

    O launcher usa `kind` para separar medição de estimativa, que é uma
    distinção que a régua já sabe desenhar."""

    kind: str  # 'measured' | 'estimated' | 'absent'
    driver: str = None
    path: str = None
    label: str = None
    covers: str = None
    note: str = None

    def to_json(self):
        saida = {"kind": self.kind}
        for chave in ("driver", "path", "label", "covers", "note"):
            valor = getattr(self, chave)
            if valor is not None:
                saida[chave] = valor
        return saida


@dataclass
class Gpu:
    """A placa escolhida, com tudo que se descobriu dela de uma vez."""

    card: object
    device: object
    driver: str
    vram: int = 0
    hwmon: object = None


# ----------------------------------------------------------------------
# Leitores.
#
# Cada um sabe ler UM sensor e nada mais. O contador de energia é o único
# com memória, porque energia acumulada só vira potência entre duas
# leituras.
# ----------------------------------------------------------------------
class Missing:
    """Sensor que não existe. Lê None para sempre, sem caso especial em
    quem chama, e carrega a explicação de por que não existe."""

    def __init__(self, note=None):
        self.source = Source("absent", note=note)

    def read(self):
        return None


class MilliDegrees:
    def __init__(self, fs, path, source):
        self.fs, self.path, self.source = fs, path, source

    def read(self):
        bruto = self.fs.read_int(self.path)
        return None if bruto is None else round(bruto / 1000)


class MicroWatts:
    def __init__(self, fs, path, source):
        self.fs, self.path, self.source = fs, path, source

    def read(self):
        bruto = self.fs.read_int(self.path)
        return None if bruto is None else round(bruto / 1e6, 1)


class EnergyCounter:
    """RAPL publica energia acumulada em microjoules, não potência.

    Potência sai da diferença entre duas leituras dividida pelo tempo
    entre elas — e por isso a PRIMEIRA leitura não devolve nada: não há
    intervalo anterior contra o qual medir. Inventar um valor aqui daria
    um número enorme no primeiro segundo do daemon.

    O contador dá a volta em `max_energy_range_uj`. Sem tratar o wrap, o
    momento da volta viraria uma potência negativa gigante uma vez a cada
    poucos minutos."""

    def __init__(self, fs, path, source, limite=None, relogio=time.monotonic):
        self.fs, self.path, self.source = fs, path, source
        self.limite = limite
        self.relogio = relogio
        self._anterior = None
        self._quando = None

    def read(self):
        agora = self.relogio()
        atual = self.fs.read_int(self.path)
        if atual is None:
            self._anterior = None
            return None

        anterior, quando = self._anterior, self._quando
        self._anterior, self._quando = atual, agora

        if anterior is None or quando is None:
            return None

        decorrido = agora - quando
        if decorrido <= 0:
            return None

        delta = atual - anterior
        if delta < 0:
            if not self.limite:
                return None  # deu a volta e não dá para saber de quanto
            delta += self.limite

        return round(delta / 1e6 / decorrido, 1)


# ----------------------------------------------------------------------
# Descoberta.
# ----------------------------------------------------------------------
def _hwmon_nodes(fs):
    """Todos os hwmon, com o nome do driver já lido."""
    saida = []
    for no in fs.glob("sys/class/hwmon/hwmon*"):
        nome = fs.read(no / "name")
        if nome:
            saida.append((nome, no))
    return saida


def _temp_inputs(fs, no):
    """[(numero, caminho, rótulo)] dos temp*_input de um nó hwmon."""
    achados = []
    for entrada in fs.glob(f"{fs.show(no).lstrip('/')}/temp*_input"):
        casa = re.match(r"^temp(\d+)_input$", entrada.name)
        if not casa:
            continue
        rotulo = fs.read(entrada.parent / f"temp{casa.group(1)}_label")
        achados.append((int(casa.group(1)), entrada, rotulo))
    return sorted(achados)


def _pick_temp(entradas, preferidos):
    """Rótulo preferido primeiro; sem rótulo conhecido, o menor índice.

    O menor índice não é chute: em coretemp e k10temp o temp1 é sempre o
    agregado do pacote, e os núcleos individuais vêm depois."""
    for alvo in preferidos:
        for _, caminho, rotulo in entradas:
            if rotulo == alvo:
                return caminho, rotulo
    if entradas:
        _, caminho, rotulo = entradas[0]
        return caminho, rotulo
    return None, None


def find_cpu_temp(fs, log=None):
    nos = _hwmon_nodes(fs)
    for driver in CPU_TEMP_DRIVERS:
        for nome, no in nos:
            if nome != driver:
                continue
            caminho, rotulo = _pick_temp(_temp_inputs(fs, no), CPU_TEMP_LABELS)
            if caminho is None:
                continue
            return MilliDegrees(
                fs, caminho,
                Source("measured", driver=driver, path=fs.show(caminho), label=rotulo),
            )

    # Sem hwmon de CPU: as zonas térmicas do ACPI ainda podem ter o
    # pacote. É medição de pior qualidade — granularidade grossa e
    # atualização lenta — mas é medição.
    for zona in fs.glob("sys/class/thermal/thermal_zone*"):
        tipo = fs.read(zona / "type")
        if tipo in CPU_THERMAL_ZONES:
            return MilliDegrees(
                fs, zona / "temp",
                Source("measured", driver=tipo, path=fs.show(zona / "temp"),
                       note="zona térmica do ACPI; não há hwmon de CPU nesta máquina"),
            )

    nota = ("procurado em /sys/class/hwmon/*/name "
            f"({', '.join(CPU_TEMP_DRIVERS)}) e em /sys/class/thermal/*/type")
    if log:
        log(f"sensor cpuTemp  ausente — {nota}")
    return Missing(nota)


def find_gpu(fs, log=None):
    """A GPU do console, procurada pelo card e não pela lista de hwmon.

    Com mais de uma placa fica a de maior VRAM — que é a discreta quando
    há discreta e integrada, o caso do dev box de quem tiver 5700G com
    placa espetada. Empate resolve pelo menor índice de card. Todas as
    candidatas vão para o log: quando o console medir a GPU errada, a
    resposta está lá."""
    candidatas = []
    for card in fs.glob("sys/class/drm/card*"):
        if not _CARD.match(card.name):
            continue  # card1-DP-1 e afins são conectores, não placas
        dispositivo = card / "device"
        uevent = fs.read(dispositivo / "uevent") or ""
        driver = None
        for linha in uevent.splitlines():
            if linha.startswith("DRIVER="):
                driver = linha.split("=", 1)[1]
        vram = fs.read_int(dispositivo / "mem_info_vram_total") or 0
        candidatas.append(Gpu(card=card, device=dispositivo, driver=driver, vram=vram))

    for gpu in candidatas:
        if log:
            log(f"gpu      candidata {fs.show(gpu.card)} driver={gpu.driver} "
                f"vram={gpu.vram // (1024 * 1024) if gpu.vram else 0} MiB")

    amd = [g for g in candidatas if g.driver == "amdgpu"]
    if not amd:
        if candidatas and log:
            outros = ", ".join(sorted({str(g.driver) for g in candidatas}))
            log(f"gpu      nenhuma amdgpu — só {outros}; sensores de GPU ficam ausentes")
        elif log:
            log("gpu      nenhuma placa em /sys/class/drm/card*")
        return None

    escolhida = sorted(amd, key=lambda g: (-g.vram, _card_index(g.card)))[0]
    for hwmon in fs.glob(f"{fs.show(escolhida.device).lstrip('/')}/hwmon/hwmon*"):
        if fs.read(hwmon / "name") == "amdgpu":
            escolhida.hwmon = hwmon
            break
    return escolhida


def _card_index(card):
    casa = re.search(r"(\d+)$", card.name)
    return int(casa.group(1)) if casa else 0


def find_gpu_temp(fs, gpu, log=None):
    if gpu is None or gpu.hwmon is None:
        nota = ("a placa não expõe hwmon próprio; numa APU isso é esperado, "
                "porque a GPU divide o die com a CPU e não tem sensor separado")
        if log:
            log(f"sensor gpuTemp  ausente — {nota}. Copiar o cpuTemp para cá "
                "daria duas células idênticas no header, que lê como defeito.")
        return Missing(nota)

    caminho, rotulo = _pick_temp(_temp_inputs(fs, gpu.hwmon), GPU_TEMP_LABELS)
    if caminho is None:
        nota = (f"{fs.show(gpu.hwmon)} existe mas não tem temp*_input; "
                "numa APU isso é esperado, porque a GPU divide o die com a "
                "CPU e não tem sensor separado")
        if log:
            log(f"sensor gpuTemp  ausente — {nota}. Copiar o cpuTemp para cá "
                "daria duas células idênticas no header, que lê como defeito.")
        return Missing(nota)

    return MilliDegrees(
        fs, caminho,
        Source("measured", driver="amdgpu", path=fs.show(caminho), label=rotulo),
    )


def find_gpu_power(fs, gpu, log=None):
    if gpu is None or gpu.hwmon is None:
        return Missing("nenhuma GPU amdgpu com hwmon")
    for nome in ("power1_average", "power1_input"):
        caminho = gpu.hwmon / nome
        if fs.exists(caminho):
            return MicroWatts(
                fs, caminho,
                Source("measured", driver="amdgpu", path=fs.show(caminho), covers="gpu"),
            )
    nota = f"{fs.show(gpu.hwmon)} não tem power1_average nem power1_input"
    if log:
        log(f"sensor gpuWatts ausente — {nota}")
    return Missing(nota)


def find_cpu_power(fs, log=None, relogio=time.monotonic):
    """Potência do pacote da CPU pelo powercap.

    O nó se chama `intel-rapl` nas duas fabricantes: desde o 5.11 o
    intel_rapl_msr também casa com os MSRs de energia da AMD a partir da
    família 17h, então o mesmo caminho serve para o 13400F e para o
    5700G. Só os domínios de topo (intel-rapl:N) são pacotes; os
    intel-rapl:N:M são subdomínios (core, uncore, dram) e somá-los
    contaria energia duas vezes."""
    for no in fs.glob("sys/class/powercap/intel-rapl:*"):
        if not _RAPL_PACKAGE.match(no.name):
            continue
        nome = fs.read(no / "name") or ""
        if not nome.startswith("package"):
            continue
        energia = no / "energy_uj"
        if not fs.exists(energia):
            continue
        return EnergyCounter(
            fs, energia,
            Source("measured", driver="intel-rapl", path=fs.show(energia), covers=nome),
            limite=fs.read_int(no / "max_energy_range_uj"),
            relogio=relogio,
        )

    nota = "procurado em /sys/class/powercap/intel-rapl:*/name"
    if log:
        log(f"sensor cpuWatts ausente — {nota}")
    return Missing(nota)
