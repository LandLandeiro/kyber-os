"""
KYBER — juntar as três fontes numa biblioteca.

    steamapps/appmanifest_*.acf      o que está INSTALADO
    userdata/*/config/localconfig    quanto se JOGOU
    appcache/appinfo.vdf             o que a coisa É

---------------------------------------------------------------------
NUNCA COMPARE CAMINHO POR STRING. Isto parece zelo excessivo e não é.

No console, o libraryfolders.vdf diz

    "path"  "/var/home/landeiro/.local/share/Steam"

enquanto o $HOME é /home/landeiro/.local/share/Steam. Os dois são o
mesmo diretório: no Fedora Atomic /home é um symlink para var/home, e a
Steam gravou o caminho já resolvido. ABRIR funciona pelos dois; COMPARAR
não. "esta biblioteca é a mesma que aquela?" responde errado, e o
sintoma é uma biblioteca listada duas vezes ou nenhuma.

Numa distribuição comum isso nunca aparece, então é exatamente o tipo de
coisa que o próximo leitor vai achar exagero. Por isso todo caminho
passa por `os.path.realpath` antes de virar chave de comparação.

---------------------------------------------------------------------
DUAS FONTES PARA DUAS PERGUNTAS, e não duas fontes para a mesma.

`lastPlayed` vem do .acf: é do título instalado NESTA máquina, e o campo
existe lá. `hoursTotal` vem do localconfig, porque o .acf não tem tempo
de jogo — nenhuma das 27 chaves. Não há escolha entre fontes discordando;
há uma fonte para cada pergunta.

Epoch 0 vira None e não 1970. Zero ali quer dizer "nunca jogado", e uma
data de 1970 na tela seria o console afirmando uma coisa que ninguém
mediu — a mesma razão pela qual telemetria ausente não vira 0 W.
"""

import os
import time
from pathlib import Path

from . import appinfo as mod_appinfo
from . import vdf

# Onde a Steam pode estar. A primeira que existir vence; não há mesclagem
# entre elas, porque duas instalações seriam duas bibliotecas e não meia.
RAIZES = (
    "~/.local/share/Steam",
    "~/.steam/steam",
    "~/.steam/root",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",   # Flatpak
)

# StateFlags é bitfield; 4 é StateFullyInstalled. Um título baixando pela
# metade tem o .acf no lugar e o bit desligado.
INSTALADO = 4

ARTE = {
    "cover": "library_600x900.jpg",
    "hero": "library_hero.jpg",
    "header": "header.jpg",
    "logo": "logo.png",
}

GIB = 1024 ** 3


def _real(caminho):
    """O caminho como o kernel o vê. Ver a nota do /var/home lá em cima."""
    return os.path.realpath(os.path.expanduser(str(caminho)))


def achar_raiz(home=None):
    """A instalação da Steam, ou None."""
    for bruto in RAIZES:
        if home is not None:
            bruto = bruto.replace("~", str(home), 1)
        caminho = Path(_real(bruto))
        if (caminho / "steamapps").is_dir():
            return caminho
    return None


def _inteiro(valor, padrao=0):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


# ----------------------------------------------------------------------
def bibliotecas(raiz, log=None):
    """Os diretórios steamapps de todas as bibliotecas, sem repetição.

    O libraryfolders.vdf existe em dois lugares — config/ e steamapps/ —
    e nos aparelhos observados são idênticos. Lemos os dois e unimos pelo
    caminho REAL: se um dia divergirem, o console lista a união em vez de
    perder metade por ter escolhido o arquivo errado."""
    log = log or (lambda _: None)
    vistos = {}
    for relativo in ("config/libraryfolders.vdf", "steamapps/libraryfolders.vdf"):
        arquivo = raiz / relativo
        if not arquivo.is_file():
            continue
        try:
            documento = vdf.carregar_arquivo(arquivo)
        except (OSError, vdf.ErroDeVDF) as erro:
            log(f"library  {arquivo} ilegível: {erro}")
            continue
        pastas = documento.get("libraryfolders") or {}
        if not isinstance(pastas, dict):
            continue
        for indice, dados in pastas.items():
            if not isinstance(dados, dict):
                continue
            caminho = dados.get("path")
            if not caminho:
                continue
            steamapps = Path(_real(caminho)) / "steamapps"
            if steamapps.is_dir():
                vistos.setdefault(str(steamapps), (indice, dados.get("label") or ""))

    # A própria raiz sempre conta, mesmo que o VDF não a liste.
    propria = raiz / "steamapps"
    if propria.is_dir():
        vistos.setdefault(str(_real(propria)), ("própria", ""))

    for caminho, (indice, rotulo) in vistos.items():
        log(f"library  biblioteca [{indice}] {caminho}"
            + (f" ({rotulo})" if rotulo else ""))
    return [Path(c) for c in vistos]


def manifestos(steamapps, log=None):
    """appid → AppState de cada appmanifest_*.acf da pasta."""
    log = log or (lambda _: None)
    encontrados = {}
    for arquivo in sorted(steamapps.glob("appmanifest_*.acf")):
        try:
            documento = vdf.carregar_arquivo(arquivo)
        except (OSError, vdf.ErroDeVDF) as erro:
            # Um manifesto ruim não pode derrubar a biblioteca inteira: o
            # que se perde é UM título, e o journal diz qual.
            log(f"library  {arquivo.name} ignorado: {erro}")
            continue
        estado = documento.get("AppState")
        if not isinstance(estado, dict):
            log(f"library  {arquivo.name} ignorado: sem bloco AppState")
            continue
        appid = _inteiro(estado.get("appid"), 0)
        if appid <= 0:
            log(f"library  {arquivo.name} ignorado: appid {estado.get('appid')!r}")
            continue
        encontrados[appid] = estado
    return encontrados


def tempos_de_jogo(raiz, log=None):
    """appid → (minutos, epoch do último acesso), do localconfig.

    Uma conta por diretório em userdata/. Havendo mais de uma, o maior
    tempo vence: contas diferentes na mesma máquina são pessoas
    diferentes jogando o mesmo título, e somar seria inventar."""
    log = log or (lambda _: None)
    tempos = {}
    for arquivo in sorted(raiz.glob("userdata/*/config/localconfig.vdf")):
        try:
            documento = vdf.carregar_arquivo(arquivo)
        except (OSError, vdf.ErroDeVDF) as erro:
            log(f"library  {arquivo} ilegível: {erro}")
            continue
        apps = (documento.get("UserLocalConfigStore", {})
                .get("Software", {}).get("Valve", {})
                .get("Steam", {}).get("apps", {}))
        if not isinstance(apps, dict):
            continue
        for chave, dados in apps.items():
            if not isinstance(dados, dict):
                continue
            appid = _inteiro(chave, 0)
            if appid <= 0:
                continue
            minutos = _inteiro(dados.get("Playtime"), 0)
            quando = _inteiro(dados.get("LastPlayed"), 0)
            anterior = tempos.get(appid, (0, 0))
            tempos[appid] = (max(minutos, anterior[0]), max(quando, anterior[1]))
    return tempos


def tipos(raiz, appids, log=None):
    """appid → (tipo normalizado|None, ano|None), do appinfo.vdf."""
    log = log or (lambda _: None)
    arquivo = raiz / "appcache" / "appinfo.vdf"
    if not arquivo.is_file():
        # Sem o cache, NENHUM título tem tipo — e a regra manda mostrar
        # todos. Uma prateleira com runtime é feia; uma prateleira vazia
        # porque um cache não existia é o console quebrado.
        log(f"library  {arquivo} não existe — nenhum título tem tipo conhecido")
        return {}
    try:
        arq = mod_appinfo.carregar_arquivo(arquivo)
        achados = {}
        for appid, dados in arq.apps(apenas=appids):
            comum = (dados.get("appinfo", dados) or {}).get("common") or {}
            tipo = comum.get("type")
            lancamento = comum.get("steam_release_date")
            ano = None
            if isinstance(lancamento, int) and lancamento > 0:
                ano = time.gmtime(lancamento).tm_year
            achados[appid] = (tipo.strip().lower() if isinstance(tipo, str) else None,
                              ano)
        return achados
    except (OSError, mod_appinfo.ErroDeAppinfo) as erro:
        log(f"library  appinfo.vdf ilegível ({erro}) — nenhum título tem tipo")
        return {}


# ----------------------------------------------------------------------
def _iso(epoch):
    return time.strftime("%Y-%m-%d", time.gmtime(epoch)) if epoch > 0 else None


def montar(raiz, log=None):
    """A biblioteca inteira: lista de títulos, na ordem do nome."""
    log = log or (lambda _: None)
    estados = {}
    for steamapps in bibliotecas(raiz, log):
        estados.update(manifestos(steamapps, log))

    tempos = tempos_de_jogo(raiz, log)
    conhecidos = tipos(raiz, set(estados), log)
    cache_arte = raiz / "appcache" / "librarycache"

    jogos, escondidos, sem_tipo = [], [], []
    for appid, estado in estados.items():
        tipo, ano = conhecidos.get(appid, (None, None))
        jogavel = mod_appinfo.eh_jogavel(tipo)
        nome = estado.get("name") or f"APP {appid}"
        if jogavel is False:
            escondidos.append(f"{appid} {nome} ({tipo})")
            continue
        if jogavel is None:
            sem_tipo.append(f"{appid} {nome}")

        minutos, ultimo_localconfig = tempos.get(appid, (0, 0))
        # O .acf responde "quando", o localconfig responde "quanto". Ver a
        # nota do cabeçalho. Se o .acf não souber, o localconfig serve.
        ultimo = _inteiro(estado.get("LastPlayed"), 0) or ultimo_localconfig

        jogos.append({
            "appid": appid,
            "name": nome,
            "sizeGB": round(_inteiro(estado.get("SizeOnDisk"), 0) / GIB, 2),
            "installed": bool(_inteiro(estado.get("StateFlags"), 0) & INSTALADO),
            "hoursTotal": round(minutos / 60, 1) if minutos else None,
            "lastPlayed": _iso(ultimo),
            "year": ano,
            # Não emitimos gênero: no appinfo ele é ID numérico
            # (`genres {"0":"1"}`) e a tabela que traduz só existe na
            # rede. Null é o que se sabe; uma palavra inventada não.
            "genre": None,
            # Duas perguntas separadas porque a resposta é diferente:
            # medido na CDN com 25 appids reais, header existe em 80% dos
            # títulos e library_600x900 em 24%. Sem `hasHero`, a ficha
            # pediria um hero inexistente para quase todo mundo e comeria
            # um 404 por título — barato em loopback, mas é ruído que não
            # precisa existir.
            "hasArt": (cache_arte / str(appid) / ARTE["cover"]).is_file(),
            "hasHero": (cache_arte / str(appid) / ARTE["hero"]).is_file(),
            "kind": tipo,
        })

    jogos.sort(key=lambda j: j["name"].casefold())
    if escondidos:
        log(f"library  {len(escondidos)} não jogáveis fora da prateleira: "
            + "; ".join(escondidos))
    if sem_tipo:
        # Aparecem, e o journal diz que apareceram sem se saber o que são.
        log(f"library  {len(sem_tipo)} sem tipo conhecido, mostrados assim "
            "mesmo: " + "; ".join(sem_tipo))
    log(f"library  {len(jogos)} títulos na prateleira")
    return jogos


def caminho_da_arte(raiz, appid, especie):
    """O JPEG no cache da Steam, ou None. Nada aqui aceita caminho de fora:
    `especie` é chave de uma tabela fechada e o appid vira inteiro."""
    arquivo = ARTE.get(especie)
    if arquivo is None:
        return None
    caminho = raiz / "appcache" / "librarycache" / str(int(appid)) / arquivo
    return caminho if caminho.is_file() else None
