#!/usr/bin/env python3
"""
KYBER — gera a arte do splash de boot a partir da fonte do kyber-shell.

Roda no RUNNER do CI, antes do build da imagem, e nunca dentro dela: o
resultado são quatro PNGs depositados em
files/system/usr/share/plymouth/themes/kyber/, de onde o módulo `files`
os leva para /usr como qualquer outro arquivo.

    ./tools/gerar-splash.py --fonte .kyber-shell/src/assets/fonts/... \
                            --saida files/system/usr/share/plymouth/themes/kyber

---------------------------------------------------------------------
POR QUE GERAR, E NÃO VERSIONAR O PNG.

Um PNG do wordmark commitado aqui é uma CÓPIA DA MARCA, e cópia deriva
em silêncio — é a mesma falha que o diretório versionado do launcher
produzia e que o pin do KYBER_SHELL_REF produziu de novo por outra
porta. Trocar a fonte no kyber-shell e o console continuar bootando com
as letras velhas, sem nada vermelho, seria a terceira vez.

Gerando aqui, a arte fica presa ao MESMO ref que o resto do launcher: a
fonte que desenha o splash é literalmente a fonte que a interface usa
dois segundos depois.

AS VERSÕES ESTÃO FIXADAS no workflow por um motivo mecânico, não por
supersição: o tema inteiro é copiado para dentro do initramfs, então um
PNG que mude de bytes muda o initramfs, e um initramfs que muda é
dezenas de MB no OTA seguinte. Rasterizador fixo = bytes estáveis.

---------------------------------------------------------------------
AS DUAS DECISÕES QUE DIVERGEM DO MOCKUP, e por quê.

  TRILHO É #161A1C, não o #0E1113 do mockup. O tokens.md manda, e nele
  o `surface-1` é literalmente "painel opaco sobre capa, trilho de
  barra". #0E1113 não é token de lugar nenhum.

  A TINTA É CENTRADA em 960/540, não a caixa de linha. O mockup põe o
  wordmark 15px abaixo do centro e 8,7px à direita, e isso não é
  desenho: é a caixa de linha do CSS mais o letter-spacing negativo
  entrando DEPOIS do último caractere. Replicar seria replicar um bug
  do navegador.
"""

import argparse
import io
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# O palco. Tudo abaixo é px a 1920×1080; o .script reescala pela altura
# real da tela, do mesmo jeito que o launcher reescala por transform.
W, H = 1920, 1080

TEXTO = "KYBER"
TAM = 200                        # font-size
TRACKING = -0.05 * TAM           # letter-spacing: -.05em
COR_TEXTO = (0xF1, 0xF4, 0xF6)   # text-hi
COR_AMBAR = (0xFF, 0x82, 0x46)   # state-hot
COR_TRILHO = (0x16, 0x1A, 0x1C)  # surface-1 — o tokens.md manda

BARRA = 5                        # altura do trilho e do progresso
SOMBRA_BLUR = 26 / 2             # CSS: blur radius r é sigma r/2
SOMBRA_SPREAD = 2
SOMBRA_ALFA = 0.55               # rgba(255,130,70,.55)

# Altura da faixa que carrega barra + brilho. O brilho morre em ~3σ =
# 39px; 48 dá folga e ainda é uma tira pequena.
FAIXA = 48

# Meia-largura da ponta. 64px é ~5σ do fim da barra, que é onde o corpo
# e a ponta já são o mesmo pixel — é isso que faz a emenda não aparecer.
PONTA = 64

# O wordmark sai em 2× e o .script reduz. Reduzir é limpo (o resize do
# plymouth interpola); ampliar não seria, e um painel 4K ampliaria.
ESCALA_WORDMARK = 2


def fonte_700(caminho):
    """woff2 variável → TTF estático em wght 700, em memória.

    A Familjen Grotesk do kyber-shell é variável (wght 400–700). Pedir
    "negrito" ao rasterizador sem instanciar devolveria o eixo no
    default, que é 400 — o wordmark sairia fino e ninguém notaria até
    ver o console ligado."""
    f = TTFont(caminho)
    if "fvar" not in f:
        raise SystemExit(f"{caminho}: fonte sem eixo de peso; esperava variável")
    f.flavor = None
    estatico = instancer.instantiateVariableFont(f, {"wght": 700})
    buf = io.BytesIO()
    estatico.save(buf)
    buf.seek(0)
    return buf


def wordmark(caminho_fonte, escala=ESCALA_WORDMARK):
    """O wordmark com tracking, recortado na tinta."""
    fonte = ImageFont.truetype(fonte_700(caminho_fonte), TAM * escala)
    tela = Image.new("RGBA", (TAM * escala * len(TEXTO) * 2, TAM * escala * 3),
                     (0, 0, 0, 0))
    d = ImageDraw.Draw(tela)
    x = float(TAM * escala)
    y = float(TAM * escala)
    for ch in TEXTO:
        d.text((x, y), ch, font=fonte, fill=COR_TEXTO + (255,))
        # O tracking entra ENTRE caracteres. Somar depois do último
        # também — que é o que o CSS faz — é o que empurra a tinta para
        # a direita no mockup.
        x += fonte.getlength(ch) + TRACKING * escala
    return tela.crop(tela.getbbox())


def barra_em(largura):
    """Um quadro com trilho, progresso e brilho, para recortar fatias.

    Desenhado no palco inteiro de propósito: as fatias saem do MESMO
    cálculo de sombra que o quadro final, então não há uma segunda
    fórmula de brilho para divergir da primeira."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([0, H - BARRA, W, H], fill=COR_TRILHO)
    if largura > 0:
        halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(halo).rectangle(
            [-SOMBRA_SPREAD, H - BARRA - SOMBRA_SPREAD,
             largura + SOMBRA_SPREAD, H + SOMBRA_SPREAD],
            fill=COR_AMBAR + (round(255 * SOMBRA_ALFA),))
        im.alpha_composite(halo.filter(ImageFilter.GaussianBlur(SOMBRA_BLUR)))
        ImageDraw.Draw(im).rectangle([0, H - BARRA, largura, H], fill=COR_AMBAR)
    return im


def fatias():
    """(corpo, ponta) — as duas peças com que o .script monta a barra.

    O corpo é uniforme em x, então escalar na horizontal reproduz o
    interior exatamente. A ponta não escala: ela é o fim de verdade,
    borrado como o CSS borraria."""
    fim = 600
    quadro = barra_em(fim)
    corpo = quadro.crop((200, H - FAIXA, 208, H))
    ponta = quadro.crop((fim - PONTA, H - FAIXA, fim + PONTA, H))
    return corpo, ponta


def trilho():
    """O trilho sozinho, para o .script esticar na largura da tela."""
    return Image.new("RGBA", (8, BARRA), COR_TRILHO + (255,))


def previa(caminho_fonte, fracao):
    """O quadro inteiro, como ele deve aparecer. Só para conferir."""
    im = barra_em(round(W * fracao))
    marca = wordmark(caminho_fonte)
    marca = marca.resize((marca.width // ESCALA_WORDMARK,
                          marca.height // ESCALA_WORDMARK), Image.LANCZOS)
    im.alpha_composite(marca, ((W - marca.width) // 2, (H - marca.height) // 2))
    return im


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fonte", required=True, type=Path,
                   help="o .woff2 da Familjen Grotesk, do kyber-shell")
    p.add_argument("--saida", required=True, type=Path,
                   help="diretório do tema")
    p.add_argument("--previa", type=Path,
                   help="além dos PNGs do tema, escreve um quadro inteiro aqui")
    p.add_argument("--previa-fracao", type=float, default=0.8)
    opcoes = p.parse_args(argv)

    if not opcoes.fonte.is_file():
        # Falha na hora, e não uma imagem que boota sem wordmark: um
        # splash pela metade é caro de descobrir e barato de recusar.
        raise SystemExit(f"fonte não encontrada: {opcoes.fonte}")

    opcoes.saida.mkdir(parents=True, exist_ok=True)
    marca = wordmark(opcoes.fonte)
    corpo, ponta = fatias()

    for nome, imagem in (("wordmark.png", marca),
                         ("trilho.png", trilho()),
                         ("progresso.png", corpo),
                         ("ponta.png", ponta)):
        alvo = opcoes.saida / nome
        imagem.save(alvo, optimize=True)
        print(f"splash  {alvo}  {imagem.width}×{imagem.height}")

    print(f"splash  wordmark em 2× — a 1080p o .script reduz para "
          f"{marca.width // ESCALA_WORDMARK}×{marca.height // ESCALA_WORDMARK}")

    if opcoes.previa:
        previa(opcoes.fonte, opcoes.previa_fracao).save(opcoes.previa)
        print(f"splash  prévia {opcoes.previa} a {opcoes.previa_fracao:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
