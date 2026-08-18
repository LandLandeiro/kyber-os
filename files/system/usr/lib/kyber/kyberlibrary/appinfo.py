"""
KYBER — appcache/appinfo.vdf, o VDF BINÁRIO.

Existe por UMA pergunta, e nenhuma outra fonte local a responde: o que a
coisa instalada É. Dos três títulos instalados no console, dois são
runtime — "Steam Linux Runtime 1.0 (scout)" e "2.0 (soldier)" — e NADA
nas 27 chaves do appmanifest os separa do terceiro. Sem isto, a
prateleira do console mostra runtime como se fosse título jogável.

    common.type   1070560  Tool     Steam Linux Runtime 1.0 (scout)
                  1391110  Tool     Steam Linux Runtime 2.0 (soldier)
                  1628350  Tool     Steam Linux Runtime 3.0 (sniper)
                   228980  Tool     Steamworks Common Redistributables
                      220  Game     Half-Life 2
                      730  Game     Counter-Strike 2

---------------------------------------------------------------------
O FORMATO, deduzido do arquivo e conferido contra ele:

    uint32  magic     0x07564427 v27 · 0x07564428 v28 · 0x07564429 v29
    uint32  universe
    int64   offset da tabela de strings                        (v28+)
    por app, até appid == 0:
        uint32  appid
        uint32  tamanho do resto da entrada
        uint32  infoState
        uint32  lastUpdated
        uint64  picsToken
        20 B    sha1 do vdf de texto
        uint32  changeNumber
        20 B    sha1 do vdf binário                            (v28+)
        <kv binário>
    no offset acima:
        uint32  quantas strings
        n × cstring utf-8

A ARMADILHA DA v28+: as CHAVES do kv binário não são strings, são uint32
— índice na tabela do fim do arquivo. Um parser de "binary VDF" escrito
para v27, que é o que se acha por aí, lê lixo e não reclama. O arquivo
do console é v29.

COMO SE SABE QUE ESTE PARSER ESTÁ CERTO. Cada entrada declara o próprio
tamanho, então a leitura tem conferência embutida: o parser de kv tem
que terminar exatamente no byte que a entrada declarou. Rodado contra um
appinfo.vdf real de 550 KB, 285 de 285 entradas fecham no byte exato, e
o terminador cai 4 bytes antes da tabela de strings — o arquivo inteiro
consumido, sem folga. É o que o teste `test_appinfo` refaz.

Custo: 12 ms para as 285 entradas.
"""

import struct

MAGICOS = {0x07564427: 27, 0x07564428: 28, 0x07564429: 29}

# Tipos do kv binário.
NINHO, TEXTO, INT32, FLOAT32, PONTEIRO, WTEXTO, COR, UINT64, FIM, INT64, FIM2 = (
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0A, 0x0B)

# infoState + lastUpdated + picsToken + sha1 + changeNumber
CABECALHO_APP = 4 + 4 + 8 + 20 + 4
# v28+ acrescenta um segundo sha1
SHA1 = 20


class ErroDeAppinfo(ValueError):
    """Arquivo que não é um appinfo.vdf que este parser saiba ler."""


class Appinfo:
    def __init__(self, bruto):
        self.b = bruto
        if len(bruto) < 16:
            raise ErroDeAppinfo("arquivo curto demais para ter cabeçalho")
        magico, self.universo = struct.unpack_from("<II", bruto, 0)
        if magico not in MAGICOS:
            raise ErroDeAppinfo(f"magic 0x{magico:08X} desconhecido")
        self.versao = MAGICOS[magico]
        self.com_tabela = self.versao >= 28
        self.tabela = []
        self._inicio = 8
        if self.com_tabela:
            offset, = struct.unpack_from("<q", bruto, 8)
            self._inicio = 16
            if not 0 < offset < len(bruto):
                raise ErroDeAppinfo(f"tabela de strings fora do arquivo ({offset})")
            self.tabela = self._ler_tabela(offset)

    def _ler_tabela(self, offset):
        quantas, = struct.unpack_from("<I", self.b, offset)
        tabela = []
        p = offset + 4
        for _ in range(quantas):
            fim = self.b.find(b"\x00", p)
            if fim < 0:
                raise ErroDeAppinfo("tabela de strings sem terminador")
            tabela.append(self.b[p:fim].decode("utf-8", "replace"))
            p = fim + 1
        return tabela

    # ------------------------------------------------------------------
    def _texto(self, p):
        fim = self.b.find(b"\x00", p)
        if fim < 0:
            raise ErroDeAppinfo(f"string sem terminador em {p}")
        return self.b[p:fim].decode("utf-8", "replace"), fim + 1

    def _chave(self, p):
        if not self.com_tabela:
            return self._texto(p)
        indice, = struct.unpack_from("<I", self.b, p)
        if indice >= len(self.tabela):
            raise ErroDeAppinfo(f"índice {indice} fora da tabela de strings")
        return self.tabela[indice], p + 4

    def _kv(self, p):
        d = {}
        while True:
            tipo = self.b[p]
            p += 1
            if tipo in (FIM, FIM2):
                return d, p
            chave, p = self._chave(p)
            if tipo == NINHO:
                d[chave], p = self._kv(p)
            elif tipo == TEXTO:
                d[chave], p = self._texto(p)
            elif tipo in (INT32, PONTEIRO, COR):
                d[chave], = struct.unpack_from("<i", self.b, p)
                p += 4
            elif tipo == FLOAT32:
                d[chave], = struct.unpack_from("<f", self.b, p)
                p += 4
            elif tipo == UINT64:
                d[chave], = struct.unpack_from("<Q", self.b, p)
                p += 8
            elif tipo == INT64:
                d[chave], = struct.unpack_from("<q", self.b, p)
                p += 8
            elif tipo == WTEXTO:
                fim = self.b.find(b"\x00\x00", p)
                if fim < 0:
                    raise ErroDeAppinfo(f"wstring sem terminador em {p}")
                d[chave] = self.b[p:fim].decode("utf-16le", "replace")
                p = fim + 2
            else:
                raise ErroDeAppinfo(f"tipo 0x{tipo:02X} desconhecido em {p - 1}")

    def apps(self, apenas=None):
        """(appid, dados) por entrada. `apenas` corta cedo.

        Percorrer o arquivo inteiro custa 12 ms; parar cedo custa menos,
        e é o caso comum — a biblioteca instalada tem punhados de itens
        e o appinfo guarda centenas."""
        p = self._inicio
        faltam = None if apenas is None else set(apenas)
        salto = CABECALHO_APP + (SHA1 if self.com_tabela else 0)
        while True:
            # 4 bytes para o appid, e SÓ eles: na v27 o terminador é o
            # último dado do arquivo e não há mais nada atrás dele. Exigir
            # 8 aqui recusava um arquivo perfeitamente válido — a v29
            # escondia isso porque a tabela de strings vem depois.
            if p + 4 > len(self.b):
                raise ErroDeAppinfo("arquivo acabou sem o terminador de apps")
            appid, = struct.unpack_from("<I", self.b, p)
            if appid == 0:
                return
            if p + 8 > len(self.b):
                raise ErroDeAppinfo(f"app {appid} sem o campo de tamanho")
            tamanho, = struct.unpack_from("<I", self.b, p + 4)
            corpo = p + 8
            if faltam is None or appid in faltam:
                dados, fim = self._kv(corpo + salto)
                # A conferência embutida: a entrada disse quanto ocupa.
                if fim != corpo + tamanho:
                    raise ErroDeAppinfo(
                        f"app {appid}: li até {fim}, a entrada declara "
                        f"{corpo + tamanho}")
                yield appid, dados
                if faltam is not None:
                    faltam.discard(appid)
                    if not faltam:
                        return
            p = corpo + tamanho


def carregar_arquivo(caminho):
    with open(caminho, "rb") as f:
        return Appinfo(f.read())


# ----------------------------------------------------------------------
# `type` NORMALIZADO EM MINÚSCULAS, e a normalização não é zelo.
#
# No appinfo.vdf real convivem as duas grafias: 42 apps com "Game" e 9
# com "game", no MESMO arquivo. Comparar com "Game" esconde nove jogos, e
# esconde em silêncio — que é a classe de defeito que este projeto já
# catalogou vezes demais. Quem "simplificar" isto depois vai reintroduzir
# exatamente esse bug.
#
# JOGÁVEIS é lista fechada. `demo` entra porque demo é jogável e aparece
# na biblioteca da Steam; `tool`, `config`, `dlc` e `application` ficam de
# fora porque nenhum deles se lança como título.
JOGAVEIS = ("game", "demo")


def eh_jogavel(tipo):
    """True, False, ou None quando não se sabe.

    None não é False. O appinfo é um CACHE: um appid que a Steam ainda
    não viu não está lá, e não ter resposta é diferente de ter a resposta
    'não'. Quem consome decide — e a decisão do console é MOSTRAR, porque
    ferramenta aparecendo é feio e jogo sumindo é bug silencioso."""
    if tipo is None:
        return None
    return tipo.strip().lower() in JOGAVEIS
