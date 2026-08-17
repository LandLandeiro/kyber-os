"""
KYBER — kyber-api: HTTP em loopback, socket Unix do outro lado.

  POST   /profile/<appid>   {"axes": {...}}   → set-profile
  DELETE /profile/<appid>                     → clear-profile

E nada mais. Leitura não passa por aqui: o perfil gravado é servido pelo
darkhttpd em /profiles.json, e o estado da máquina em /state.json. Este
processo só escreve.

---------------------------------------------------------------------
POR QUE PORTA PRÓPRIA, E NÃO DENTRO DO DARKHTTPD.

O launcher é servido em 127.0.0.1:8787 por um darkhttpd que só serve
estático — sem CGI, sem proxy, por projeto. Então ou esta peça vive noutra
porta e paga CORS, ou ela absorve o serviço estático e some com o CORS.

A segunda opção custa a propriedade que o console tem hoje: a interface
abre com o daemon fora do ar e desenha SEM LEITURA. Pondo o escritor
dentro do servidor estático, um kyber-api que morre deixa de ser "salvar
falha" e vira tela de erro de conexão no boot. É a mesma troca que a unit
do darkhttpd recusa no comentário do --chroot.

Então: porta própria, CORS explícito, e o launcher continua abrindo
mesmo quando esta peça não sobe.

O CORS AQUI NÃO É DEFESA, e vale dizer para ninguém acreditar no
contrário daqui a seis meses. Ele impede uma PÁGINA de outra origem de
ler a resposta; não faz nada contra um processo local, que é a ameaça
realista numa máquina onde o navegador é kiosk numa URL fixa. A fronteira
é a do lado root.

O que ele compra, estreitamente: exigir `Content-Type: application/json`
faz qualquer requisição de outra origem virar preflight, e o preflight
reprova em `Access-Control-Allow-Origin`, que é exato e nunca `*`.
"""

import argparse
import http.server
import json
import os
import socket
import sys

from gameprofiled import control

from . import VERSION

ORIGEM = "http://127.0.0.1:8787"
PORTA = 8788
ENDERECO = "127.0.0.1"

# O mesmo teto do outro lado. Recusar aqui evita empurrar para o socket
# uma mensagem que ele vai cortar no meio.
MAX_CORPO = control.MAX_MENSAGEM

# O daemon responde em milissegundos: ele grava um arquivo pequeno num
# tmpfs. Dois segundos é o prazo de um daemon que está com problema, não
# o de um daemon ocupado.
PRAZO_S = 2.0

# Um appid de verdade tem no máximo 10 dígitos. Acima disso nem se tenta
# converter — o daemon é quem recusa, e recusa por appid inválido.
MAX_DIGITOS = 12


def log(mensagem):
    print(mensagem, file=sys.stderr, flush=True)


def conversar(caminho, comando):
    """Manda um comando ao daemon. (resposta, None) ou (None, motivo)."""
    conexao = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conexao.settimeout(PRAZO_S)
    try:
        conexao.connect(caminho)
        conexao.sendall(json.dumps(comando).encode() + b"\n")
        bruto = b""
        while b"\n" not in bruto and len(bruto) < MAX_CORPO:
            pedaco = conexao.recv(4096)
            if not pedaco:
                break
            bruto += pedaco
    except OSError as erro:
        # Os dois casos que importam distinguir no journal: ENOENT é
        # daemon parado (o socket some com o RuntimeDirectory), EACCES é
        # permissão — este processo não está no grupo do socket.
        return None, f"{type(erro).__name__}: {erro.strerror or erro}"
    finally:
        conexao.close()

    try:
        return json.loads(bruto), None
    except ValueError as erro:
        return None, f"resposta do daemon não é JSON: {erro}"


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = f"kyber-api/{VERSION}"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------
    def _cors(self):
        # Origem EXATA. `*` deixaria qualquer página do mundo falar com
        # esta porta se o console um dia abrir um navegador comum.
        self.send_header("Access-Control-Allow-Origin", self.server.origem)
        self.send_header("Vary", "Origin")

    def _responder(self, status, corpo):
        bruto = json.dumps(corpo, ensure_ascii=False).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(bruto)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(bruto)

    def _erro(self, status, codigo, nota):
        self._responder(status, {"v": control.VERSAO, "ok": False,
                                 "error": codigo, "note": nota})

    def log_message(self, formato, *args):
        # O journal já carimba a hora; o formato do http.server põe outra.
        log("api      " + formato % args)

    # ------------------------------------------------------------------
    def _appid(self):
        """O segmento da rota, como o daemon vai recebê-lo.

        Converte para inteiro quando dá, e passa adiante como veio quando
        não dá. Recusar aqui duplicaria a regra do appid — e a regra tem
        que morar num lugar só, do lado que trata a mensagem como
        hostil."""
        partes = self.path.split("?")[0].strip("/").split("/")
        if len(partes) != 2 or partes[0] != "profile" or not partes[1]:
            return None
        bruto = partes[1]
        if bruto.isdigit() and len(bruto) <= MAX_DIGITOS:
            return int(bruto)
        return bruto

    def _corpo(self):
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None, "Content-Length inválido"
        if tamanho > MAX_CORPO:
            return None, f"corpo maior que {MAX_CORPO} bytes"
        if tamanho == 0:
            return {}, None
        try:
            return json.loads(self.rfile.read(tamanho)), None
        except (ValueError, OSError) as erro:
            return None, f"corpo não é JSON: {erro}"

    def _entregar(self, comando):
        resposta, motivo = conversar(self.server.socket_daemon, comando)
        if resposta is None:
            # 503 e não 500: o daemon é outro serviço, e o launcher
            # precisa distinguir "recusou" de "não estava lá".
            log(f"api      daemon inalcançável em "
                f"{self.server.socket_daemon}: {motivo}")
            self._erro(503, "daemon_inalcancavel", motivo)
            return
        # Duas regras, e nenhuma delas conhece o vocabulário: aceito ou
        # recusado. O código do erro viaja no corpo para quem quiser.
        self._responder(200 if resposta.get("ok") else 400, resposta)

    # ------------------------------------------------------------------
    def do_OPTIONS(self):
        if self._appid() is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        appid = self._appid()
        if appid is None:
            self._erro(404, "rota_desconhecida", f"{self.path} não existe")
            return
        # Exigir JSON é o que faz uma página de outra origem precisar de
        # preflight — e o preflight reprova na origem exata.
        tipo = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if tipo != "application/json":
            self._erro(415, "tipo_invalido",
                       "esta rota só aceita application/json")
            return
        corpo, motivo = self._corpo()
        if corpo is None:
            self._erro(400, "corpo_invalido", motivo)
            return
        if not isinstance(corpo, dict):
            self._erro(400, "corpo_invalido", "a raiz do corpo não é objeto")
            return
        # `axes` vai VERBATIM. Filtrar aqui seria a segunda lista.
        self._entregar({"v": control.VERSAO, "cmd": "set-profile",
                        "appid": appid, "axes": corpo.get("axes")})

    def do_DELETE(self):
        appid = self._appid()
        if appid is None:
            self._erro(404, "rota_desconhecida", f"{self.path} não existe")
            return
        self._entregar({"v": control.VERSAO, "cmd": "clear-profile",
                        "appid": appid})


class Servidor(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, endereco, socket_daemon, origem):
        super().__init__(endereco, Handler)
        self.socket_daemon = socket_daemon
        self.origem = origem


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="kyber-api", description=__doc__)
    p.add_argument("--addr", default=ENDERECO)
    p.add_argument("--port", type=int, default=PORTA)
    p.add_argument("--socket", default=control.CAMINHO,
                   help="socket de comando do gameprofiled")
    p.add_argument("--origin", default=ORIGEM,
                   help="origem exata que pode falar com esta porta")
    return p.parse_args(argv)


def main(argv=None):
    opcoes = parse_args(argv)
    servidor = Servidor((opcoes.addr, opcoes.port), opcoes.socket, opcoes.origin)
    log(f"api      {opcoes.addr}:{opcoes.port} → {opcoes.socket} "
        f"· origem {opcoes.origin} · uid {os.getuid()}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
