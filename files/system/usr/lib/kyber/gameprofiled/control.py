"""
KYBER — o socket de comando.

O daemon continua sem expor HTTP. O que ele ganha aqui é um socket Unix
com uma lista FECHADA de dois verbos, e a lista ser fechada é a
propriedade de segurança — não um detalhe de implementação que dá para
afrouxar depois porque ficou apertado.

  set-profile     grava o perfil de um título
  clear-profile   apaga o perfil de um título; ele volta a seguir o padrão

Não há verbo de leitura, e isso também é propriedade: um protocolo que
não lê não vaza nada, e a frase "o JSON é o canal de leitura" continua
inteira. Quem quer saber o que está gravado busca /profiles.json pelo
darkhttpd; quem quer saber o que está APLICADO busca /state.json. São
perguntas diferentes e continuam tendo respostas diferentes.

O QUE ESTE SOCKET NÃO FAZ, e por que cada ausência foi escolhida:

  apply-now       seria o segundo caminho. O socket grava o ARQUIVO e
                  mais nada; o daemon descobre pelo mtime do próximo
                  tick, do mesmo jeito que descobre uma edição com o
                  `vi`. Duas fontes de perfil que fossem caminhos
                  diferentes contariam histórias diferentes no dia em
                  que discordassem.
  set-curve       a curva de watts se calibra com um wattímetro na
                  parede, uma vez na vida do console. Comando que muda o
                  significado de todo watt publicado, para um evento
                  único, é superfície sem demanda.
  set-default     nenhuma tela edita o perfil do console; a tela 04 é por
                  título. Entra quando a tela existir.
  qualquer coisa que escreva em sysfs direto — seria o caminho paralelo
                  por outro nome.

---------------------------------------------------------------------
VALIDAÇÃO HOSTIL, E POR QUE ELA CONTINUA VALENDO.

Com o socket em 0660 root:kyber-api, quem consegue abri-lo é o kyber-api
e o root — NÃO "qualquer coisa da sessão". Vale dizer isso em voz alta
porque a premissa contrária, se sobreviver seis meses, vira justificativa
para deixar o socket 0666 ("não importa mesmo").

A validação aqui é hostil assim mesmo, e por um motivo diferente do que
parece: o kyber-api recebe entrada de uma porta TCP. Ele é conveniência
de transporte, não fronteira — é justamente ele que pode estar
comprometido. Então nada que chegue por aqui é tratado como vindo de um
amigo:

  · appid é INTEIRO, entre 1 e 2^31-1. Não é string, não é float, não é
    booleano (que em Python é int e passaria por descuido), e nunca é
    caminho de arquivo. O caminho do arquivo é constante deste processo;
    nenhum campo da mensagem influencia caminho nenhum.
  · o vocabulário dos eixos é o do `score`, o MESMO que o config usa para
    filtrar arquivo. Uma segunda lista aqui seria a terceira fonte de
    verdade do projeto, e a segunda já custou um NaN na régua.
  · chave desconhecida em `axes` é RECUSADA, não descartada. Descartar em
    silêncio é o que faz um cliente achar que gravou o que não gravou.

---------------------------------------------------------------------
`available` É AUTORIDADE, MAS SÓ QUANDO TEM O QUE DIZER.

Pedir `schedutil` numa máquina com intel_pstate em modo ativo é recusado
com a razão e com a lista do que existe. O editor já risca o
indisponível, mas interface não é fronteira: a leitura dele é tirada uma
vez, na montagem, e a máquina pode ter mudado desde então.

Mas `available` vazio NÃO recusa. Vazio quer dizer duas coisas muito
diferentes — "esta build nunca vai fazer isso" e "falta pré-condição
AGORA", como o limite de quadros antes de a sessão gráfica subir — e
recusar um SALVAR porque uma sondagem falhou por dois segundos
transformaria estado transitório em trabalho perdido.

Mais que isso: o launcher JÁ desenha esse caso. No grupo onde nada é
aplicável o LED sai de todas as opções e o valor guardado volta como
palavra no cabeçalho — "perfil pede 60". Aquele desenho existe para
mostrar que o perfil guarda um valor que ninguém aplica. Recusar a
gravação apagaria justamente o que ele foi feito para mostrar.

Então: lista com itens e valor fora dela → recusa. Lista vazia → aceita,
com AVISO na resposta. O arquivo continua sendo artefato portátil, que é
o que permite levar o disco para outra máquina e o eixo passar a
funcionar lá.
"""

import grp
import json
import os
import select
import socket
import struct
import time

from . import score

CAMINHO = "/run/kyber/control.sock"

# Quem tem permissão de escrita no socket é quem consegue conectar. O
# grupo nasce do /usr/lib/sysusers.d/kyber-api.conf e é o único membro.
GRUPO = "kyber-api"

VERSAO = 1

COMANDOS = ("set-profile", "clear-profile")

# Um comando cabe em algumas centenas de bytes. O teto existe para uma
# mensagem sem fim não virar memória sem fim.
MAX_MENSAGEM = 4096

# Teto de títulos com perfil próprio. Não é limite de produto: é o que
# impede um laço de set-profile de encher o /var, que num console de
# imagem read-only é o único lugar gravável que existe.
MAX_TITULOS = 1024

# Quem não entrega uma mensagem completa por socket local neste tempo não
# é cliente que valha esperar. O prazo é curto porque o laço de
# publicação está esperando: um cliente que segurasse o laço congelaria o
# `at`, e o launcher leria LEITURA PARADA de um daemon perfeitamente vivo.
# O daemon se faria de morto por ter atendido o telefone.
PRAZO_S = 0.1

# Conexões atendidas por rodada. Depois disso o laço volta a publicar,
# mesmo com fila — a publicação tem prioridade sobre o comando.
MAX_POR_RODADA = 8

MAX_APPID = 2 ** 31 - 1

_SO_PEERCRED = getattr(socket, "SO_PEERCRED", None)


def _par(conexao):
    """(pid, uid, gid) de quem está do outro lado, ou None.

    Só para o log. Quem decide QUEM conecta é a permissão do arquivo;
    isto é a contabilidade de quem conectou, e é o que transforma "o
    socket aceita comandos" numa linha de journal com nome e sobrenome.

    Linux-only: no macOS o socket existe e o SO_PEERCRED não, e é no
    macOS que a suíte roda."""
    if _SO_PEERCRED is None:
        return None
    try:
        bruto = conexao.getsockopt(socket.SOL_SOCKET, _SO_PEERCRED,
                                   struct.calcsize("3i"))
    except OSError:
        return None
    return struct.unpack("3i", bruto)


def _quem(par):
    return f"pid {par[0]} uid {par[1]}" if par else "par desconhecido"


def _recusa(codigo, nota, **extra):
    """Código legível por máquina e nota legível por gente.

    A mesma disciplina das `sources` do state.json: quem consome decide
    pelo código, quem depura lê a nota. A lista de códigos é fechada e
    está no README."""
    resposta = {"v": VERSAO, "ok": False, "error": codigo, "note": nota}
    resposta.update({c: v for c, v in extra.items() if v is not None})
    return resposta


def _appid(valor):
    """Inteiro positivo, ou None.

    `isinstance(True, int)` é verdadeiro em Python, então booleano é
    recusado à mão — senão `{"appid": true}` viraria o título 1."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        return None
    return valor if 1 <= valor <= MAX_APPID else None


class Servidor:
    """O socket, e a conversa de um comando por conexão.

    `disponiveis` é uma função (eixo) → lista, que o daemon fornece
    perguntando ao eixo VIVO. Não é uma cópia: o eixo de GPU troca quando
    o card rebinda e o de quadros troca quando a sessão aparece, e uma
    lista congelada na abertura do socket recusaria o que a máquina
    passou a aceitar."""

    def __init__(self, fs, config, disponiveis, caminho=CAMINHO, log=None,
                 grupo=GRUPO):
        self.fs = fs
        self.config = config
        self.disponiveis = disponiveis
        self.caminho = caminho
        self.log = log or (lambda _: None)
        self.grupo = grupo
        self.sock = None

    # ------------------------------------------------------------------
    def abrir(self):
        """Abre e devolve True, ou registra o motivo e devolve False.

        Falhar aqui NÃO derruba o daemon. O socket é aditivo: sem ele o
        console mede, aplica e publica exatamente como publicava antes, e
        o que se perde é o editor poder gravar. Derrubar a telemetria de
        toda a interface porque o canal de escrita não subiu seria trocar
        um recurso por um console cego."""
        alvo = self.fs.path(self.caminho)
        try:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            # Sobra de uma parada suja. O RuntimeDirectory some com o
            # diretório numa parada limpa; o que estiver aqui é de uma que
            # não foi limpa, e ninguém está escutando nele.
            if alvo.is_socket():
                alvo.unlink()
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(str(alvo))
            sock.listen(4)
            sock.setblocking(False)
        except OSError as erro:
            self.log(f"socket   não abriu em {self.fs.show(alvo)}: "
                     f"{type(erro).__name__}: {erro.strerror or erro}"
                     + _dica_caminho(erro, alvo))
            return False

        self.sock = sock
        self._permitir(alvo)
        return True

    def _permitir(self, alvo):
        """0660 root:kyber-api, ou 0600 e um aviso.

        Conectar num socket Unix exige permissão de ESCRITA no arquivo, e
        o modo que sai do umask do root é 0755 — fechado para todo mundo
        menos ele. O default já falha fechado, e este método é um
        AFROUXAMENTO deliberado, feito só quando existe um grupo em favor
        de quem afrouxar.

        Sem o grupo — alguém tirou o sysusers.d, ou é a suíte rodando num
        Mac onde o chown para o root nem é permitido — o socket fica 0600
        e o log diz que só o root vai falar com ele. O contrário, cair
        para 0666 porque o grupo não apareceu, é como um daemon vira porta
        aberta por causa de um arquivo de configuração faltando."""
        try:
            gid = grp.getgrnam(self.grupo).gr_gid
            os.chown(alvo, 0, gid)
            os.chmod(alvo, 0o660)
        except (KeyError, OSError) as erro:
            motivo = (f"grupo {self.grupo} não existe" if isinstance(erro, KeyError)
                      else f"{type(erro).__name__}: {erro.strerror or erro}")
            try:
                os.chmod(alvo, 0o600)
            except OSError:
                pass
            self.log(f"socket   {self.fs.show(alvo)} em 0600 ({motivo}) — "
                     "só o root fala com este daemon")
            return
        self.log(f"socket   {self.fs.show(alvo)} 0660 root:{self.grupo}")

    def fechar(self):
        if self.sock is None:
            return
        self.sock.close()
        self.sock = None
        try:
            self.fs.path(self.caminho).unlink()
        except OSError:
            pass

    # ------------------------------------------------------------------
    def atender(self, timeout):
        """Atende quem estiver esperando, até `timeout` segundos.

        Devolve quantas conversas houve. O laço de publicação chama isto
        no lugar de dormir, e nunca cede o instante da publicação: ver
        MAX_POR_RODADA e PRAZO_S."""
        if self.sock is None:
            return 0
        atendidas = 0
        while atendidas < MAX_POR_RODADA:
            try:
                prontos, _, _ = select.select([self.sock], [], [], max(0.0, timeout))
            except OSError:
                return atendidas
            if not prontos:
                return atendidas
            try:
                conexao, _ = self.sock.accept()
            except OSError:
                return atendidas
            with conexao:
                self._conversar(conexao)
            atendidas += 1
            timeout = 0.0   # o resto da fila sai sem esperar de novo
        return atendidas

    def _conversar(self, conexao):
        par = _par(conexao)
        conexao.settimeout(PRAZO_S)
        limite = time.monotonic() + PRAZO_S
        bruto = b""
        try:
            while b"\n" not in bruto and len(bruto) < MAX_MENSAGEM:
                if time.monotonic() > limite:
                    raise TimeoutError("prazo esgotado")
                pedaco = conexao.recv(MAX_MENSAGEM)
                if not pedaco:
                    break
                bruto += pedaco
        except OSError as erro:
            self.log(f"socket   {_quem(par)} não entregou mensagem em "
                     f"{PRAZO_S}s ({erro}); conexão descartada")
            return

        resposta = self.executar(bruto[:MAX_MENSAGEM])
        if resposta.get("ok"):
            self.log(f"socket   {_quem(par)} {resposta.get('cmd', '')} aceito"
                     + (f" — {resposta['note']}" if resposta.get("note") else ""))
        else:
            self.log(f"socket   {_quem(par)} RECUSADO {resposta.get('error')}: "
                     f"{resposta.get('note')}")
        try:
            conexao.sendall(
                json.dumps(resposta, ensure_ascii=False).encode() + b"\n")
        except OSError:
            pass

    # ------------------------------------------------------------------
    def executar(self, bruto):
        """Bytes entram, resposta sai. Sem socket nenhum no meio.

        É pura de propósito: o vocabulário inteiro se testa sem abrir
        socket, e o que sobra para o teste de socket é só o transporte."""
        try:
            pedido = json.loads(bruto.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as erro:
            return _recusa("mensagem_invalida", f"não é JSON: {erro}")
        if not isinstance(pedido, dict):
            return _recusa("mensagem_invalida", "a raiz não é um objeto")

        if pedido.get("v") != VERSAO:
            # Versão desconhecida não vira melhor esforço. Um kyber-api
            # novo falando com um daemon velho tem que discordar em voz
            # alta, como o launcher faz com o schema do state.json.
            return _recusa("versao_desconhecida",
                           f"este daemon fala v{VERSAO}; chegou "
                           f"{pedido.get('v')!r}")

        comando = pedido.get("cmd")
        if comando not in COMANDOS:
            return _recusa("comando_desconhecido",
                           f"{comando!r} não está na lista; são "
                           + ", ".join(COMANDOS))

        appid = _appid(pedido.get("appid"))
        if appid is None:
            return _recusa("appid_invalido",
                           f"{pedido.get('appid')!r} não é um appid; "
                           f"é inteiro entre 1 e {MAX_APPID}")

        if comando == "set-profile":
            return self._set_profile(appid, pedido)
        return self._clear_profile(appid)

    # ------------------------------------------------------------------
    def _set_profile(self, appid, pedido):
        eixos = pedido.get("axes")
        if not isinstance(eixos, dict) or not eixos:
            return _recusa("mensagem_invalida",
                           "`axes` tem que ser um objeto com ao menos um eixo")

        limpo, avisos = {}, []
        for chave, valor in eixos.items():
            if chave not in score.AXES:
                return _recusa("eixo_desconhecido",
                               f"{chave!r} não é eixo de perfil; são "
                               + ", ".join(score.AXES), axis=chave)
            if score.weight_of(chave, valor) is None:
                return _recusa("valor_fora_do_vocabulario",
                               f"{valor!r} não é valor de {chave}",
                               axis=chave, value=valor,
                               available=score.options(chave))

            oferecidos = list(self.disponiveis(chave) or [])
            if oferecidos and valor not in oferecidos:
                return _recusa("eixo_indisponivel",
                               f"esta máquina não aplica {valor!r} em {chave}; "
                               f"aplica {', '.join(oferecidos)}",
                               axis=chave, value=valor, available=oferecidos)
            if not oferecidos:
                avisos.append({
                    "axis": chave,
                    "note": f"esta máquina não aplica nenhum valor de {chave} "
                            "agora; o pedido fica gravado e vale onde valer",
                })
            limpo[chave] = valor

        def mutar(documento):
            jogos = documento.get("games")
            if not isinstance(jogos, dict):
                jogos = documento["games"] = {}
            if str(appid) not in jogos and len(jogos) >= MAX_TITULOS:
                return "limite_de_titulos"
            # SUBSTITUI a entrada, não mescla. Mesclar deixaria eixos
            # antigos escondidos embaixo de uma gravação nova, e "o que
            # está gravado" deixaria de ser o que o cliente mandou.
            jogos[str(appid)] = limpo
            return None

        erro = self.config.gravar(mutar)
        if erro == "limite_de_titulos":
            return _recusa("limite_de_titulos",
                           f"o arquivo já guarda {MAX_TITULOS} títulos")
        if erro:
            return _recusa("escrita_falhou", erro)

        resposta = {"v": VERSAO, "ok": True, "cmd": "set-profile",
                    "appid": appid, "axes": limpo,
                    "note": "gravado; o daemon aplica no próximo ciclo e "
                            "publica o resultado por eixo no state.json"}
        if avisos:
            resposta["warnings"] = avisos
        return resposta

    def _clear_profile(self, appid):
        removido = []

        def mutar(documento):
            jogos = documento.get("games")
            if isinstance(jogos, dict) and jogos.pop(str(appid), None) is not None:
                removido.append(True)
            return None

        erro = self.config.gravar(mutar)
        if erro:
            return _recusa("escrita_falhou", erro)
        return {"v": VERSAO, "ok": True, "cmd": "clear-profile", "appid": appid,
                "note": ("entrada removida; o título volta a seguir o padrão"
                         if removido else
                         "o título já seguia o padrão; nada havia para remover")}


def _dica_caminho(erro, alvo):
    """A armadilha que só aparece fora do Linux.

    `sun_path` tem 108 bytes no Linux e 104 no Darwin, e o `tempfile` do
    macOS entrega caminhos longos sob /var/folders. Um teste que monte
    diretório fundo falha lá e passa aqui, com um ENAMETOOLONG que não
    diz de onde veio."""
    if len(str(alvo).encode()) > 100:
        return (f" — o caminho tem {len(str(alvo).encode())} bytes e sun_path "
                "cabe 108 no Linux, 104 no macOS")
    return ""
