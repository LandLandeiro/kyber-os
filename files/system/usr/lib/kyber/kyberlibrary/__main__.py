"""
KYBER — kyber-library: a biblioteca Steam, em loopback, só leitura.

  GET /library.json          os títulos instalados, resolvidos
  GET /art/<appid>/<espécie> o JPEG que a Steam já baixou, do disco

E nada mais. Não há POST, não há DELETE, não há rota que escreva —
`kyber-power` age, esta lê, e é assim que as duas ficam pequenas o
bastante para caber na cabeça de quem revisar daqui a seis meses.

---------------------------------------------------------------------
A ARTE VEM DO DISCO, E NÃO DA CDN.

A Steam já baixou: appcache/librarycache/<appid>/, 28 MB e 137 títulos
no console. Buscar de novo na rede o que está no disco custaria a
primeira tela do console numa casa com internet ruim — e a biblioteca É
a primeira tela.

Medido na CDN, com 25 appids de uma biblioteca real: header.jpg existe
em 80% dos títulos, library_600x900.jpg em 24%. A capa que a prateleira
usa NÃO EXISTE para três em cada quatro títulos, e isso não é falha de
rede: é o catálogo da Valve. O launcher já desenha esse caso — a capa
gerada — e ele vai ser o caso comum, não a exceção.

CACHE COM VALIDADOR, e aqui ele é seguro. A resposta de arte leva ETag
de mtime+tamanho e responde 304 a um If-None-Match que bata. Sem isso, a
volta à prateleira redecodifica dezenas de JPEGs por nada. O ETag é
confiável porque estes arquivos moram em /home, com mtime de verdade —
ao contrário de /usr, onde o ostree zera o mtime de tudo e foi o que fez
o launcher velho sobreviver a um OTA.

O library.json vai de `no-store`: instalar um jogo tem que aparecer na
volta seguinte à tela, e o corpo é pequeno.

SEM CACHE DO LADO DE CÁ, de propósito. Montar a biblioteca lê alguns
arquivos e corta cedo no appinfo; são dezenas de milissegundos. Um cache
com invalidação seria mais código e mais um jeito de a tela mostrar uma
biblioteca que já mudou.
"""

import argparse
import http.server
import json
import os
import sys

from . import VERSION
from . import biblioteca as mod_biblioteca

ORIGEM = "http://127.0.0.1:8787"
PORTA = 8790
ENDERECO = "127.0.0.1"

VERSAO = 1

TIPO_DE_ARQUIVO = {".jpg": "image/jpeg", ".png": "image/png"}


def log(mensagem):
    print(mensagem, file=sys.stderr, flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = f"kyber-library/{VERSION}"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", self.server.origem)
        self.send_header("Vary", "Origin")

    def _cabecalho(self, status, tipo, tamanho, extras=()):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(tamanho))
        for chave, valor in extras:
            self.send_header(chave, valor)
        self.end_headers()

    def _json(self, status, corpo, cache="no-store"):
        bruto = json.dumps(corpo, ensure_ascii=False).encode()
        self._cabecalho(status, "application/json; charset=utf-8", len(bruto),
                        [("Cache-Control", cache)])
        if self.command != "HEAD":
            self.wfile.write(bruto)

    def _erro(self, status, codigo, nota):
        self._json(status, {"v": VERSAO, "ok": False, "error": codigo,
                            "note": nota})

    def log_message(self, formato, *args):
        log("library  " + formato % args)

    # ------------------------------------------------------------------
    def do_GET(self):
        caminho = self.path.split("?")[0]
        if caminho in ("/library.json", "/library"):
            return self._biblioteca()
        partes = caminho.strip("/").split("/")
        if len(partes) == 3 and partes[0] == "art":
            return self._arte(partes[1], partes[2])
        self._erro(404, "rota_desconhecida", f"{self.path} não existe")

    do_HEAD = do_GET

    # ------------------------------------------------------------------
    def _biblioteca(self):
        raiz = self.server.raiz
        if raiz is None:
            # 503 e não 500: a Steam não estar instalada não é defeito
            # desta peça, e o launcher precisa saber a diferença para
            # dizer "sem biblioteca" em vez de "erro".
            self._erro(503, "steam_ausente",
                       "não achei uma instalação da Steam em nenhum dos "
                       "caminhos conhecidos")
            return
        try:
            jogos = mod_biblioteca.montar(raiz, log)
        except OSError as erro:
            self._erro(503, "biblioteca_ilegivel",
                       f"{type(erro).__name__}: {erro.strerror or erro}")
            return
        self._json(200, {"v": VERSAO, "ok": True, "games": jogos})

    def _arte(self, appid_bruto, especie):
        raiz = self.server.raiz
        if raiz is None:
            self._erro(503, "steam_ausente", "sem instalação da Steam")
            return
        try:
            appid = int(appid_bruto)
        except ValueError:
            self._erro(404, "appid_invalido", f"{appid_bruto!r} não é appid")
            return
        if appid <= 0:
            self._erro(404, "appid_invalido", f"{appid_bruto!r} não é appid")
            return

        arquivo = mod_biblioteca.caminho_da_arte(raiz, appid, especie)
        if arquivo is None:
            # 404 é a resposta CERTA e é rotina: a capa vertical não
            # existe para três em cada quatro títulos. O launcher desenha
            # a capa gerada, que é o caminho normal e não o de erro.
            self._erro(404, "sem_arte",
                       f"a Steam não tem {especie!r} em disco para {appid}")
            return

        try:
            info = arquivo.stat()
            etag = f'"{int(info.st_mtime)}-{info.st_size}"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self._cors()
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            dados = arquivo.read_bytes()
        except OSError as erro:
            self._erro(503, "arte_ilegivel",
                       f"{type(erro).__name__}: {erro.strerror or erro}")
            return

        tipo = TIPO_DE_ARQUIVO.get(arquivo.suffix, "application/octet-stream")
        self._cabecalho(200, tipo, len(dados),
                        [("ETag", etag), ("Cache-Control", "no-cache")])
        if self.command != "HEAD":
            self.wfile.write(dados)


class Servidor(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, endereco, origem, raiz):
        super().__init__(endereco, Handler)
        self.origem = origem
        self.raiz = raiz


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="kyber-library", description=__doc__)
    p.add_argument("--addr", default=ENDERECO)
    p.add_argument("--port", type=int, default=PORTA)
    p.add_argument("--origin", default=ORIGEM,
                   help="origem exata que pode falar com esta porta")
    p.add_argument("--steam", default=None,
                   help="raiz da Steam; o padrão é procurar nos caminhos "
                        "conhecidos. Existe para a suíte apontar para uma "
                        "árvore falsa sem instalar Steam nenhuma")
    return p.parse_args(argv)


def main(argv=None):
    opcoes = parse_args(argv)
    raiz = None
    if opcoes.steam:
        from pathlib import Path
        raiz = Path(opcoes.steam)
    else:
        raiz = mod_biblioteca.achar_raiz()

    if raiz is None:
        # Não é motivo para não subir: a Steam pode ser instalada depois,
        # e a rota responde 503 com o motivo enquanto isso. Peça que
        # morre no start vira "falha ao salvar" sem explicação na tela.
        log("library  nenhuma instalação da Steam encontrada — "
            "as rotas respondem 503 até existir uma")
    else:
        log(f"library  raiz da Steam: {raiz}")

    servidor = Servidor((opcoes.addr, opcoes.port), opcoes.origin, raiz)
    log(f"library  {opcoes.addr}:{opcoes.port} · origem {opcoes.origin} "
        f"· uid {os.getuid()}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
