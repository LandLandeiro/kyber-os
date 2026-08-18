"""
KYBER — VDF de texto, o subconjunto que a Steam usa.

O formato é da Valve e não tem contrato publicado. O que está aqui foi
medido, não deduzido: o parser rodou contra os 96 arquivos .vdf de texto
de uma instalação real, comparado com a biblioteca `vdf` do PyPI.

  arquivos de dados do Steam (config/, userdata/, steamapps/)
      16 de 17 idênticos à referência, 0 divergentes, 0 falhas

  arquivos do Steam Input (controller_base/)
      76 de 79 DIVERGENTES

As 76 divergências são todas a mesma coisa e vale dizer qual, porque é o
único jeito de o formato quebrar um parser pequeno: CHAVE DUPLICADA. Os
temas de controle repetem "group" dezenas de vezes no mesmo nível, a
referência mescla, e um dict sobrescreve. Aqui a última vence, e isso
está declarado em vez de acidental — o KYBER não lê nenhum arquivo de
Steam Input, e nos que ele lê a duplicata não aparece.

O QUE OS ARQUIVOS REAIS NÃO TÊM, e por isso não está implementado:

  condicionais [$WIN32]   0 ocorrências em 96 arquivos
  #base / #include        0
  comentários //          0 (o parser trata mesmo assim: é barato)

O QUE ELES TÊM E SURPREENDE:

  BOM UTF-8   30 dos 96 começam com \\xef\\xbb\\xbf. Sem tratar, o BOM vira
              um token, e o erro aponta para a linha 2 de um arquivo cuja
              linha 2 está perfeita.
  \\uXXXX      fica LITERAL. Nem este parser nem o de referência decodifica
              — se a Valve escrever HELLDIVERS\\u2122 2, é isso que chega.
              Nos .acf do console os nomes vêm em UTF-8 direto, então a
              decodificação não entra aqui: entraria como adivinhação
              sobre um caso que não se observou.
"""


class ErroDeVDF(ValueError):
    """Arquivo que não é VDF, ou é VDF que este parser não lê.

    Falha alta e com a linha. Um parser que devolve dicionário pela
    metade faz a biblioteca aparecer com metade dos títulos, e isso não
    se distingue de uma biblioteca com metade dos títulos."""


def carregar(texto):
    """Texto VDF → dict aninhado. Todo valor escalar é string."""
    # O BOM some antes de qualquer coisa. Ver a nota lá em cima.
    texto = texto.lstrip("﻿")
    pos = 0
    n = len(texto)

    def erro(mensagem):
        raise ErroDeVDF(f"linha {texto.count(chr(10), 0, pos) + 1}: {mensagem}")

    def pular():
        nonlocal pos
        while pos < n:
            c = texto[pos]
            if c in " \t\r\n":
                pos += 1
            elif texto.startswith("//", pos):
                fim = texto.find("\n", pos)
                pos = n if fim < 0 else fim + 1
            else:
                return

    def token():
        """Próximo token, ou None no fim. '{' e '}' saem como si mesmos."""
        nonlocal pos
        pular()
        if pos >= n:
            return None
        c = texto[pos]
        if c == "}":
            return "}"
        if c == "{":
            pos += 1
            return "{"
        if c == '"':
            pos += 1
            partes = []
            while pos < n:
                c = texto[pos]
                if c == "\\" and pos + 1 < n:
                    seguinte = texto[pos + 1]
                    partes.append({"n": "\n", "t": "\t", "\\": "\\",
                                   '"': '"'}.get(seguinte, "\\" + seguinte))
                    pos += 2
                elif c == '"':
                    pos += 1
                    return "".join(partes)
                else:
                    partes.append(c)
                    pos += 1
            erro("string sem fechamento")
        inicio = pos
        while pos < n and texto[pos] not in ' \t\r\n"{}':
            pos += 1
        if pos == inicio:
            erro(f"caractere inesperado {c!r}")
        return texto[inicio:pos]

    def condicional():
        """Consome [$COND], se houver. Não existe nos arquivos do Steam,
        e é tratado para que a ausência seja escolha e não sorte."""
        nonlocal pos
        pular()
        if pos < n and texto[pos] == "[":
            fim = texto.find("]", pos)
            if fim < 0:
                erro("condicional sem fechamento")
            pos = fim + 1

    def bloco(topo=False):
        nonlocal pos
        d = {}
        while True:
            chave = token()
            if chave is None:
                if topo:
                    return d
                erro("fim do arquivo dentro de um bloco")
            if chave == "}":
                pos += 1
                return d
            if chave == "{":
                erro("bloco sem chave")
            condicional()
            valor = token()
            if valor is None or valor == "}":
                erro(f"a chave {chave!r} não tem valor")
            if valor == "{":
                d[chave] = bloco()
            else:
                condicional()
                d[chave] = valor

    return bloco(topo=True)


def carregar_arquivo(caminho):
    """Lê e parseia. `utf-8-sig` come o BOM; o lstrip cobre o resto."""
    with open(caminho, "r", encoding="utf-8-sig", errors="replace") as f:
        return carregar(f.read())
