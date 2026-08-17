"""
Árvores de sysfs falsas.

Três máquinas, e cada uma existe para provar uma coisa diferente:

  intel_rx7600   o dev box. Sensores completos, e os índices de hwmon
                 EMBARALHADOS de propósito — coretemp em hwmon7, amdgpu em
                 hwmon2, lixo em hwmon0 e hwmon1. Descoberta que ordene por
                 índice mede a temperatura do SSD e não percebe.
  ryzen_5700g    o console. k10temp sem `Tdie`, e uma amdgpu integrada que
                 NÃO expõe temperatura. É o caso que precisa publicar
                 ausência em vez de copiar o número da CPU.
  bare           nada. Nenhum hwmon, nenhum card, nenhum cpufreq.
  dual_gpu       integrada e discreta juntas; a escolha tem que cair na de
                 mais VRAM.

O hwmon da GPU é criado sob o card e ESPELHADO em /sys/class/hwmon por
symlink, que é como o sysfs de verdade o apresenta. Sem isso o teste não
exercitaria a razão de a GPU ser procurada pelo card: na lista plana ela
aparece com o mesmo nome que qualquer outra amdgpu da máquina.
"""

import os
from pathlib import Path

GIB = 1024 ** 3


def _escrever(caminho, conteudo):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(str(conteudo) + "\n")


def _hwmon(raiz, indice, nome, atributos, sob=None):
    """Cria um nó hwmon e o publica em /sys/class/hwmon/hwmonN.

    `sob` é o diretório do dispositivo dono (o device de um card, por
    exemplo). Sem ele o nó nasce sob /sys/devices/platform, como os
    sensores de plataforma nascem."""
    dono = Path(sob) if sob else raiz / "sys/devices/platform" / nome
    no = dono / "hwmon" / f"hwmon{indice}"
    _escrever(no / "name", nome)
    for chave, valor in atributos.items():
        _escrever(no / chave, valor)

    classe = raiz / "sys/class/hwmon"
    classe.mkdir(parents=True, exist_ok=True)
    os.symlink(no, classe / f"hwmon{indice}")
    return no


def _cpufreq(raiz, governor, disponiveis, driver, politicas=4):
    for i in range(politicas):
        base = raiz / "sys/devices/system/cpu/cpufreq" / f"policy{i}"
        _escrever(base / "scaling_governor", governor)
        _escrever(base / "scaling_available_governors", disponiveis)
        _escrever(base / "scaling_driver", driver)


def _card(raiz, indice, driver, vram, dpm=None):
    dispositivo = raiz / "sys/class/drm" / f"card{indice}" / "device"
    _escrever(dispositivo / "uevent", f"DRIVER={driver}\nPCI_ID=1002:7480")
    _escrever(dispositivo / "vendor", "0x1002")
    _escrever(dispositivo / "mem_info_vram_total", vram)
    if dpm is not None:
        _escrever(dispositivo / "power_dpm_force_performance_level", dpm)
    # Conector: casa com o glob card* e NÃO é uma placa. Se a descoberta
    # não filtrar por nome, ela tenta ler driver de um conector de vídeo.
    _escrever(raiz / "sys/class/drm" / f"card{indice}-DP-1" / "status", "connected")
    return dispositivo


def _rapl(raiz, energia=502_113_884_512):
    base = raiz / "sys/class/powercap/intel-rapl:0"
    _escrever(base / "name", "package-0")
    _escrever(base / "energy_uj", energia)
    _escrever(base / "max_energy_range_uj", 262_143_328_850)
    # Subdomínio. Somar com o pacote contaria a mesma energia duas vezes.
    sub = raiz / "sys/class/powercap/intel-rapl:0:0"
    _escrever(sub / "name", "core")
    _escrever(sub / "energy_uj", 301_000_000_000)


def intel_rx7600(raiz):
    raiz = Path(raiz)
    _hwmon(raiz, 0, "nvme", {"temp1_input": 38000, "temp1_label": "Composite"})
    _hwmon(raiz, 1, "iwlwifi_1", {"temp1_input": 45000})
    _hwmon(raiz, 7, "coretemp", {
        "temp1_input": 61000, "temp1_label": "Package id 0",
        "temp2_input": 64000, "temp2_label": "Core 0",
        "temp3_input": 59000, "temp3_label": "Core 4",
    })
    dispositivo = _card(raiz, 1, "amdgpu", 8 * GIB, dpm="auto")
    _hwmon(raiz, 2, "amdgpu", {
        "temp1_input": 68000, "temp1_label": "edge",
        "temp2_input": 88000, "temp2_label": "junction",
        "temp3_input": 70000, "temp3_label": "mem",
        "power1_average": 96_800_000,
        "fan1_input": 1450,
    }, sob=dispositivo)
    _rapl(raiz)
    # intel_pstate em modo ativo: schedutil NÃO existe.
    _cpufreq(raiz, "powersave", "performance powersave", "intel_pstate")
    return raiz


def ryzen_5700g(raiz):
    raiz = Path(raiz)
    _hwmon(raiz, 0, "nvme", {"temp1_input": 41000, "temp1_label": "Composite"})
    # Sem Tdie: a preferência tem que cair para Tctl e não para o índice.
    _hwmon(raiz, 3, "k10temp", {
        "temp1_input": 44125, "temp1_label": "Tctl",
        "temp2_input": 44125, "temp2_label": "Tccd1",
    })
    # Vega 8: hwmon existe, temperatura não. É o caso do die compartilhado.
    dispositivo = _card(raiz, 0, "amdgpu", 512 * 1024 * 1024, dpm="auto")
    _hwmon(raiz, 4, "amdgpu", {"freq1_input": 400_000_000}, sob=dispositivo)
    _rapl(raiz)
    _cpufreq(raiz, "schedutil",
             "conservative ondemand userspace powersave performance schedutil",
             "acpi-cpufreq")
    return raiz


def bare(raiz):
    raiz = Path(raiz)
    (raiz / "sys/class").mkdir(parents=True, exist_ok=True)
    (raiz / "proc").mkdir(parents=True, exist_ok=True)
    return raiz


def dual_gpu(raiz):
    raiz = Path(raiz)
    integrada = _card(raiz, 0, "amdgpu", 512 * 1024 * 1024, dpm="auto")
    _hwmon(raiz, 1, "amdgpu", {"temp1_input": 51000, "temp1_label": "edge"},
           sob=integrada)
    discreta = _card(raiz, 1, "amdgpu", 8 * GIB, dpm="auto")
    _hwmon(raiz, 2, "amdgpu", {"temp1_input": 68000, "temp1_label": "edge"},
           sob=discreta)
    return raiz
