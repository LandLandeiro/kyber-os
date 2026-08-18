"""
Árvores de Steam falsas.

Montam, num diretório temporário, o que uma instalação de verdade tem —
sem Steam instalada e sem rede. A forma dos arquivos veio de um
levantamento no console e de uma instalação real num Mac, não de
documentação: o VDF é formato da Valve e não tem contrato publicado.

O caso central é `console`, que reproduz o que o aparelho tem hoje e é o
motivo de este módulo existir: TRÊS títulos instalados, dos quais DOIS
são runtime. Nada no appmanifest os separa do terceiro — a distinção só
existe no appinfo.vdf binário, e é isso que o teste prova.

`duas_bibliotecas` existe porque o libraryfolders.vdf é lista indexada
mesmo quando há um disco só, e porque o console guarda o caminho já
resolvido (/var/home/...) enquanto o $HOME diz /home/... — comparar
caminho por string acerta na máquina de quem escreve e erra no console.
"""

import struct
from pathlib import Path


def _escrever(caminho, texto):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")


def libraryfolders(raiz, caminhos):
    """O libraryfolders.vdf, nos DOIS lugares em que a Steam o mantém."""
    blocos = []
    for i, caminho in enumerate(caminhos):
        blocos.append(
            f'\t"{i}"\n'
            f'\t{{\n'
            f'\t\t"path"\t\t"{caminho}"\n'
            f'\t\t"label"\t\t""\n'
            f'\t\t"contentid"\t\t"877430987511951302{i}"\n'
            f'\t\t"totalsize"\t\t"0"\n'
            f'\t\t"apps"\n'
            f'\t\t{{\n'
            f'\t\t}}\n'
            f'\t}}\n')
    texto = '"libraryfolders"\n{\n' + "".join(blocos) + "}\n"
    _escrever(Path(raiz) / "config/libraryfolders.vdf", texto)
    _escrever(Path(raiz) / "steamapps/libraryfolders.vdf", texto)


def manifesto(steamapps, appid, nome, *, tamanho=1 << 30, flags=4,
              ultimo=0, installdir=None, extra=""):
    """Um appmanifest_<appid>.acf, na forma que o console tem."""
    _escrever(
        Path(steamapps) / f"appmanifest_{appid}.acf",
        f'"AppState"\n'
        f'{{\n'
        f'\t"appid"\t\t"{appid}"\n'
        f'\t"Universe"\t\t"1"\n'
        f'\t"name"\t\t"{nome}"\n'
        f'\t"StateFlags"\t\t"{flags}"\n'
        f'\t"installdir"\t\t"{installdir or nome.replace(" ", "")}"\n'
        f'\t"LastUpdated"\t\t"1786994367"\n'
        f'\t"LastPlayed"\t\t"{ultimo}"\n'
        f'\t"SizeOnDisk"\t\t"{tamanho}"\n'
        f'\t"StagingSize"\t\t"0"\n'
        f'\t"buildid"\t\t"23825428"\n'
        f'\t"LastOwner"\t\t"76561198311368291"\n'
        f'\t"DownloadType"\t\t"0"\n'
        f'\t"AutoUpdateBehavior"\t\t"0"\n'
        f'\t"AllowOtherDownloadsWhileRunning"\t\t"0"\n'
        f'\t"ScheduledAutoUpdate"\t\t"0"\n'
        f'\t"InstalledDepots"\n'
        f'\t{{\n'
        f'\t\t"{appid + 1}"\n'
        f'\t\t{{\n'
        f'\t\t\t"manifest"\t\t"4956520704156364317"\n'
        f'\t\t\t"size"\t\t"{tamanho}"\n'
        f'\t\t}}\n'
        f'\t}}\n'
        f'\t"UserConfig"\n'
        f'\t{{\n'
        f'\t}}\n'
        f'{extra}'
        f'}}\n')


def localconfig(raiz, steamid, tempos):
    """userdata/<id>/config/localconfig.vdf — `tempos` é appid → (min, epoch).

    O bloco fica no fundo de quatro níveis, como no arquivo de verdade;
    achatar aqui faria o teste passar com um leitor que não desce."""
    apps = "".join(
        f'\t\t\t\t\t"{appid}"\n'
        f'\t\t\t\t\t{{\n'
        f'\t\t\t\t\t\t"LastPlayed"\t\t"{quando}"\n'
        f'\t\t\t\t\t\t"Playtime"\t\t"{minutos}"\n'
        f'\t\t\t\t\t}}\n'
        for appid, (minutos, quando) in sorted(tempos.items()))
    _escrever(
        Path(raiz) / f"userdata/{steamid}/config/localconfig.vdf",
        '"UserLocalConfigStore"\n'
        '{\n'
        '\t"Software"\n'
        '\t{\n'
        '\t\t"Valve"\n'
        '\t\t{\n'
        '\t\t\t"Steam"\n'
        '\t\t\t{\n'
        '\t\t\t\t"apps"\n'
        '\t\t\t\t{\n'
        + apps +
        '\t\t\t\t}\n'
        '\t\t\t}\n'
        '\t\t}\n'
        '\t}\n'
        '}\n')


# ----------------------------------------------------------------------
# appinfo.vdf BINÁRIO. Escrito byte a byte porque é assim que o leitor vai
# encontrá-lo, e porque a v29 tem a armadilha que interessa: as chaves do
# kv não são strings, são índices numa tabela no fim do arquivo.
def _cstring(s):
    return s.encode("utf-8") + b"\x00"


def appinfo(raiz, apps, versao=29):
    """`apps` é appid → dict de common (type, name, steam_release_date)."""
    com_tabela = versao >= 28
    tabela, indice = [], {}

    def idx(chave):
        if chave not in indice:
            indice[chave] = len(tabela)
            tabela.append(chave)
        return indice[chave]

    def kv(d):
        saida = b""
        for chave, valor in d.items():
            marca = struct.pack("<I", idx(chave)) if com_tabela else _cstring(chave)
            if isinstance(valor, dict):
                saida += b"\x00" + marca + kv(valor) + b"\x08"
            elif isinstance(valor, int):
                saida += b"\x02" + marca + struct.pack("<i", valor)
            else:
                saida += b"\x01" + marca + _cstring(str(valor))
        return saida

    corpos = []
    for appid, comum in apps.items():
        dados = kv({"appinfo": {"common": comum}})
        cabecalho = (struct.pack("<II", 0, 0)          # infoState, lastUpdated
                     + struct.pack("<Q", 0)            # picsToken
                     + b"\x00" * 20                    # sha1 do vdf de texto
                     + struct.pack("<I", 0))           # changeNumber
        if com_tabela:
            cabecalho += b"\x00" * 20                  # sha1 do vdf binário
        corpo = cabecalho + dados + b"\x08"
        corpos.append(struct.pack("<II", appid, len(corpo)) + corpo)

    magico = {27: 0x07564427, 28: 0x07564428, 29: 0x07564429}[versao]
    cabecalho = struct.pack("<II", magico, 1)
    apps_bytes = b"".join(corpos) + struct.pack("<I", 0)

    if com_tabela:
        offset = len(cabecalho) + 8 + len(apps_bytes)
        bruto = (cabecalho + struct.pack("<q", offset) + apps_bytes
                 + struct.pack("<I", len(tabela))
                 + b"".join(_cstring(s) for s in tabela))
    else:
        bruto = cabecalho + apps_bytes

    alvo = Path(raiz) / "appcache/appinfo.vdf"
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_bytes(bruto)


def arte(raiz, appid, especies=("library_600x900.jpg",)):
    """JPEGs de mentira no cache da Steam. O conteúdo não importa; o que
    importa é o caminho, que é o que o console vai servir."""
    for nome in especies:
        alvo = Path(raiz) / "appcache/librarycache" / str(appid) / nome
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(b"\xff\xd8\xff" + bytes(64))


# ----------------------------------------------------------------------
def console(raiz):
    """O aparelho como ele está: 3 instalados, 2 deles runtime.

    Os appids e os nomes são os do levantamento. É o caso que prova que
    a prateleira precisa do appinfo — sem ele, "Steam Linux Runtime 2.0
    (soldier)" aparece como título jogável."""
    raiz = Path(raiz)
    libraryfolders(raiz, [str(raiz)])
    steamapps = raiz / "steamapps"
    manifesto(steamapps, 1070560, "Steam Linux Runtime 1.0 (scout)",
              tamanho=222685392, ultimo=0, installdir="SteamLinuxRuntime")
    manifesto(steamapps, 1391110, "Steam Linux Runtime 2.0 (soldier)",
              tamanho=676965917, ultimo=0, installdir="SteamLinuxRuntime_soldier")
    manifesto(steamapps, 1625450, "Muck", tamanho=438755103,
              ultimo=1786900000, installdir="Muck")
    localconfig(raiz, 351102563, {1625450: (137, 1786900000)})
    appinfo(raiz, {
        1070560: {"type": "Tool", "name": "Steam Linux Runtime 1.0 (scout)"},
        1391110: {"type": "Tool", "name": "Steam Linux Runtime 2.0 (soldier)"},
        # minúsculo DE PROPÓSITO: no appinfo real convivem "Game" e "game",
        # 42 contra 9. Um teste só com "Game" deixa passar a normalização.
        1625450: {"type": "game", "name": "Muck",
                  "steam_release_date": 1622505600},
    })
    arte(raiz, 1625450)
    return raiz


def duas_bibliotecas(raiz, segunda):
    """Uma biblioteca na raiz e outra num segundo disco."""
    raiz, segunda = Path(raiz), Path(segunda)
    libraryfolders(raiz, [str(raiz), str(segunda)])
    manifesto(raiz / "steamapps", 220, "Half-Life 2", tamanho=8 << 30)
    manifesto(segunda / "steamapps", 730, "Counter-Strike 2", tamanho=36 << 30)
    appinfo(raiz, {220: {"type": "Game", "name": "Half-Life 2"},
                   730: {"type": "Game", "name": "Counter-Strike 2"}})
    return raiz


def vazia(raiz):
    """Steam instalada, nenhum jogo. O caso do Mac de quem desenvolve."""
    raiz = Path(raiz)
    libraryfolders(raiz, [str(raiz)])
    (raiz / "steamapps").mkdir(parents=True, exist_ok=True)
    return raiz
