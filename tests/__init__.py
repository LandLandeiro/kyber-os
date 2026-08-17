"""
Testes do gameprofiled.

O pacote vive na árvore da imagem (files/system/usr/lib/kyber/) porque é
de lá que ele é instalado. Os testes o alcançam pondo esse diretório no
path — não há passo de build nem instalação, e não deve haver: o daemon é
stdlib pura de propósito.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "files/system/usr/lib/kyber"))
