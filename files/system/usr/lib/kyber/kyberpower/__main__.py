"""
KYBER — kyber-power: os quatro verbos de energia, dentro da sessão.

  POST /power/poweroff    desliga
  POST /power/reboot      reinicia
  POST /power/suspend     suspende
  POST /power/desktop     sai para o ambiente gráfico

E nada mais. Não há leitura: não existe pergunta a fazer a esta peça —
o estado de energia de um console é a tela estar acesa.

Roda como o DONO DA SESSÃO, não como um usuário de serviço. Ver o
__init__ para o porquê; em uma frase: os três primeiros verbos são
`allow_active=yes` no logind, então este processo não ganha autoridade
nenhuma — ele empresta a de quem já está na frente da máquina, para quem
não tem teclado.

---------------------------------------------------------------------
POR QUE NÃO HÁ ENDURECIMENTO NA UNIT.

O kyber-api leva quinze linhas de sandbox porque lá elas SIGNIFICAM algo:
aquele processo não deve poder nada, e cada linha fecha uma porta que ele
não usa. Aqui seria teatro. O processo roda com o uid da pessoa e a
fronteira não está no processo — está do outro lado do D-Bus, no polkit,
que decide olhando a sessão e não o programa. Um `ProtectSystem=strict`
aqui não impediria nada que importa e daria a impressão de que impediu.

O que continua valendo é o que é real: escuta em 127.0.0.1, origem exata
no CORS, lista fechada de quatro verbos, e nenhum campo do corpo virando
argumento de comando.

---------------------------------------------------------------------
O CORS AQUI TAMBÉM NÃO É DEFESA.

Mesma nota do kyber-api, e ela não fica menos verdadeira por repetição:
o cabeçalho impede uma PÁGINA de outra origem de ler a resposta, e não
faz nada contra um processo local — que, aqui, já podia rodar
`systemctl poweroff` sozinho, porque roda com o mesmo uid. O que a
exigência de `Content-Type: application/json` compra é estreito e é
mecânico: ela força preflight, e o preflight reprova numa origem exata.
"""

import argparse
import http.server
import json
import os
import subprocess
import sys

from . import VERSION

ORIGEM = "http://127.0.0.1:8787"
PORTA = 8789
ENDERECO = "127.0.0.1"

# Versão do protocolo desta porta. É um `1` próprio e NÃO o
# `control.VERSAO` do gameprofiled: importar de lá amarraria o
# vocabulário de energia à evolução do vocabulário de perfil, que é
# exatamente a mistura que fez esta peça nascer separada.
VERSAO = 1

# A LISTA FECHADA. Rota → comando, e o comando é constante: nenhum campo
# do corpo, nenhum trecho da URL e nenhum cabeçalho entra na linha de
# comando. Não há shell no caminho (`subprocess` com lista de
# argumentos), então não há citação a acertar nem a errar.
VERBOS = {
    "poweroff": ("systemctl", "poweroff"),
    "reboot": ("systemctl", "reboot"),
    "suspend": ("systemctl", "suspend"),
    # Modo Desktop não é `steamos-session-select`, e a ausência é
    # deliberada — ver /usr/libexec/kyber-session-desktop. Em resumo:
    # aquele caminho depende de um vocabulário fechado que não inclui a
    # sessão do KYBER, e de qual drop-in do SDDM a troca escreve e como
    # ele ordena contra o nosso. São duas incógnitas; o arquivo que já é
    # nosso e já é reescrito a cada boot é zero.
    "desktop": ("systemctl", "start", "kyber-session-desktop.service"),
}

# `systemctl poweroff` devolve assim que o logind aceita o trabalho — o
# desligamento em si leva segundos e acontece depois. Cinco segundos é o
# prazo de um systemctl que travou, não o de um que está ocupado.
PRAZO_S = 5.0

# Fora `desktop`, todo verbo daqui termina com a sessão morrendo. A
# resposta vai ANTES disso porque o systemctl devolve antes disso — e ela
# importa: é ela que diz para a tela "aceito, pode mostrar DESLIGANDO"
# em vez de a tela ter que adivinhar pelo silêncio.


def log(mensagem):
    print(mensagem, file=sys.stderr, flush=True)


def executar(comando, prazo=PRAZO_S):
    """Roda o comando. (None) se deu certo, ou (codigo, nota).

    Recebe o executor por injeção no servidor para a suíte poder rodar
    num Mac sem desligar o Mac."""
    try:
        fim = subprocess.run(comando, capture_output=True, text=True,
                             timeout=prazo, check=False)
    except FileNotFoundError:
        return "comando_ausente", f"{comando[0]} não existe nesta máquina"
    except subprocess.TimeoutExpired:
        return "comando_travou", f"{comando[0]} não respondeu em {prazo:g} s"
    except OSError as erro:
        return "comando_falhou", f"{type(erro).__name__}: {erro}"

    if fim.returncode == 0:
        return None

    # A primeira linha do stderr é o que o systemctl tem a dizer —
    # "Interactive authentication required." quando o polkit recusou,
    # "Failed to start ..." quando a unit falhou. Repassar VERBATIM é o
    # que permite a tela mostrar o motivo real em vez de "não deu": esta
    # peça não conhece os motivos e não deve fingir que conhece.
    nota = (fim.stderr or fim.stdout or "").strip().splitlines()
    return "comando_falhou", (nota[0] if nota else
                              f"saiu {fim.returncode} sem dizer nada")


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = f"kyber-power/{VERSION}"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------
    def _cors(self):
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

    def _erro(self, status, codigo, nota, **extra):
        corpo = {"v": VERSAO, "ok": False, "error": codigo, "note": nota}
        corpo.update(extra)
        self._responder(status, corpo)

    def log_message(self, formato, *args):
        log("power    " + formato % args)

    # ------------------------------------------------------------------
    def _verbo(self):
        """O verbo da rota, ou None quando a rota não é /power/<algo>.

        Rota errada e verbo fora da lista são coisas DIFERENTES e a
        resposta distingue as duas: 404 quer dizer "não é aqui", 400 quer
        dizer "é aqui e isso não existe" — e a segunda vem com a lista,
        que é o que faz um cliente errado se consertar."""
        partes = self.path.split("?")[0].strip("/").split("/")
        if len(partes) != 2 or partes[0] != "power" or not partes[1]:
            return None
        return partes[1]

    def do_OPTIONS(self):
        if self._verbo() is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        verbo = self._verbo()
        if verbo is None:
            self._erro(404, "rota_desconhecida", f"{self.path} não existe")
            return

        tipo = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if tipo != "application/json":
            self._erro(415, "tipo_invalido",
                       "esta rota só aceita application/json")
            return

        if verbo not in VERBOS:
            self._erro(400, "verbo_desconhecido",
                       f"{verbo!r} não é verbo de energia; são "
                       + ", ".join(VERBOS),
                       verbs=list(VERBOS))
            return

        # O corpo não é lido e não é usado. A exigência de Content-Type
        # existe pelo preflight; o verbo inteiro está na rota. Ler para
        # descartar seria abrir a porta para alguém, um dia, aceitar um
        # campo — e o dia seguinte é o campo virar argumento.
        self._drenar()

        comando = VERBOS[verbo]
        falha = self.server.executor(comando)
        if falha is None:
            log(f"power    {verbo} aceito · {' '.join(comando)}")
            self._responder(200, {
                "v": VERSAO, "ok": True, "cmd": verbo,
                "note": "o logind aceitou; a máquina responde a seguir"})
            return

        codigo, nota = falha
        log(f"power    {verbo} RECUSADO {codigo}: {nota}")
        # 200 para aceito, 502 para "o comando existiu e recusou". Não é
        # 500: o erro não é deste processo, é do lado que decide — e a
        # tela precisa distinguir isso de um bug daqui.
        self._erro(502, codigo, nota, cmd=verbo)

    def _drenar(self):
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if 0 < tamanho <= 4096:
            self.rfile.read(tamanho)


class Servidor(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, endereco, origem, executor=executar):
        super().__init__(endereco, Handler)
        self.origem = origem
        self.executor = executor


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="kyber-power", description=__doc__)
    p.add_argument("--addr", default=ENDERECO)
    p.add_argument("--port", type=int, default=PORTA)
    p.add_argument("--origin", default=ORIGEM,
                   help="origem exata que pode falar com esta porta")
    return p.parse_args(argv)


def main(argv=None):
    opcoes = parse_args(argv)
    servidor = Servidor((opcoes.addr, opcoes.port), opcoes.origin)
    log(f"power    {opcoes.addr}:{opcoes.port} · origem {opcoes.origin} "
        f"· uid {os.getuid()} · verbos {', '.join(VERBOS)}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
