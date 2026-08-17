"""
KYBER — perfis por título.

O perfil que o daemon aplica vem de disco: `/var/lib/kyber/profiles.json`.
É de lá que ele lê, é lá que o `vi` edita, e é lá que o socket de comando
grava — os três pelo mesmo caminho, o que é a razão de o socket não ter
atalho para o ProfileManager.

O arquivo também é SERVIDO: um symlink na árvore do launcher o publica em
/profiles.json, e é assim que o editor de perfil abre mostrando o que
está gravado. Por isso toda escrita aqui é atômica e 0644 — ver
`_entregar`.

A imagem é read-only, então o arquivo nasce de uma semente em
/usr/share/kyber/profiles.default.json na primeira execução. Semear em
vez de embutir só o default no código deixa a decisão de fábrica visível
e editável sem recompilar imagem.

A curva de watts mora aqui pelo mesmo motivo: 22 W de repouso e 7 W por
ponto são chute do protótipo, e `calibrated: false` diz isso em voz alta.
Quando alguém medir o console com um wattímetro na parede, troca os dois
números e vira `true` — e é só então que o `watts` publicado deixa de ser
estimativa.
"""

import copy
import json
import os
from pathlib import Path

from . import score

CAMINHO = "/var/lib/kyber/profiles.json"
SEMENTE = "/usr/share/kyber/profiles.default.json"

EMBUTIDO = {
    "curve": {"wattsIdle": 22, "wattsPerPoint": 7, "calibrated": False},
    # DPM em `auto` e não `alto` de propósito: no 5700G a CPU e a GPU
    # dividem envelope térmico, e o gabinete é fechado com chaminé
    # passiva. Forçar `high` é o tipo de default que só aparece três horas
    # depois de ligado.
    "default": {
        "governor": "performance",
        "gpuLevel": "auto",
        "fpsLimit": "sem limite",
        "priority": "alta",
    },
    "games": {},
}


def embutido():
    """Cópia PROFUNDA do padrão de fábrica.

    Copiar o dicionário de cima só duplica o primeiro nível: as chaves
    `games` e `default` continuam sendo o MESMO objeto em toda cópia.
    Enquanto ninguém escrevia no documento isso não aparecia. A gravação
    pelo socket escreve — e gravar sobre o padrão embutido, que é o que
    acontece quando o arquivo está ilegível, punha o perfil daquele
    título dentro da constante do módulo, para o resto da vida do
    processo. O padrão de fábrica deixaria de ser de fábrica sem que nada
    no disco tivesse mudado, e RESTAURAR PADRÃO passaria a devolver o
    perfil de outro jogo.

    Achado pela suíte, e por acidente: o teste de arquivo corrompido
    envenenou os dois testes de socket que rodavam depois dele.
    """
    return copy.deepcopy(EMBUTIDO)


class Config:
    def __init__(self, fs, caminho=CAMINHO, semente=SEMENTE, log=None):
        self.fs = fs
        self.caminho = fs.path(caminho)
        self.semente = fs.path(semente)
        self.log = log or (lambda _: None)
        self.origin = "padrão embutido"
        self.dados = embutido()
        self._marca = None
        self.reload()

    # ------------------------------------------------------------------
    def _seed(self):
        if self.caminho.exists() or not self.semente.exists():
            return
        try:
            # Cópia de BYTES, não json.loads/dumps: a semente carrega um
            # bloco `_comment` escrito para ser lido dentro do arquivo, e
            # reserializar mudaria a formatação dele sem motivo.
            self._entregar(self.semente.read_bytes())
            self.log(f"config   semeado {self.fs.show(self.caminho)} "
                     f"de {self.fs.show(self.semente)}")
        except OSError as erro:
            self.log(f"config   não deu para semear: {erro}")

    def _entregar(self, conteudo):
        """`.tmp` + `os.replace()`, e 0644. A mesma disciplina do state.json.

        Atômico porque este arquivo é SERVIDO: o darkhttpd o alcança por
        symlink e faz stat + sendfile sem lock nenhum, então uma escrita
        no lugar entregaria JSON pela metade a quem estivesse lendo.
        rename(2) troca o inode inteiro e quem já abriu segue lendo o
        antigo até o fim.

        0644 porque quem serve é o darkhttpd rodando como `nobody`. O
        diretório ganha +x pelo StateDirectoryMode da unit. Sem o chmod
        explícito o modo sairia do umask de quem escreveu, que é uma
        variável de ambiente decidindo se o console tem editor de perfil."""
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.caminho.parent / (self.caminho.name + ".tmp")
        with open(temporario, "wb") as arquivo:
            arquivo.write(conteudo)
        os.chmod(temporario, 0o644)
        os.replace(temporario, self.caminho)

    # ------------------------------------------------------------------
    def gravar(self, mutar):
        """Aplica `mutar` ao documento em disco e o regrava. Erro ou None.

        RELÊ DO DISCO, e não usa o `self.dados` que está em memória. Entre
        a última leitura e agora alguém pode ter editado o arquivo à mão,
        e regravar por cima de uma cópia velha perderia essa edição sem
        dizer nada.

        E NÃO TOCA em `self.dados`. Quem descobre que o arquivo mudou é o
        `reload()` do próximo tick, pelo mesmo caminho por onde descobre
        uma edição manual. É isso que faz não existir um segundo caminho:
        gravar pelo socket e gravar com o `vi` chegam ao daemon do mesmo
        jeito, e não há como as duas versões divergirem porque só existe
        uma.

        O preço é até um segundo entre gravar e aplicar. Cabe dentro da
        vida do toast do launcher, e a resposta do socket diz `gravado`,
        não `aplicado` — quem responde `aplicado` é o state.json, um
        segundo depois, com estado por eixo."""
        documento = self._documento_para_escrita()
        erro = mutar(documento)
        if erro:
            return erro
        try:
            self._entregar(
                json.dumps(documento, ensure_ascii=False, indent=2).encode()
                + b"\n")
        except OSError as erro:
            return f"{type(erro).__name__}: {erro.strerror or erro}"
        return None

    def _documento_para_escrita(self):
        """O arquivo como está no disco, ou o embutido se ele não presta.

        Arquivo ilegível não pode travar o editor de perfil: num console
        sem terminal isso seria um beco sem saída — a tela recusaria
        gravar para sempre e não há de onde consertar o arquivo. Então a
        gravação parte do padrão embutido.

        Mas o conteúdo anterior NÃO é jogado fora. Ele vai para
        `.corrompido` ao lado, porque pode ser um arquivo inteiro de
        perfis que perdeu uma vírgula, e apagá-lo em silêncio para
        destravar uma tela seria trocar um problema visível por um
        invisível.

        As chaves que o daemon não conhece sobrevivem: a leitura é do
        documento inteiro e a escrita devolve o documento inteiro. É o que
        preserva o `_comment` da semente e o que faz uma chave de uma
        versão futura não ser apagada por uma versão antiga."""
        try:
            lido = json.loads(self.caminho.read_text())
            if isinstance(lido, dict):
                return lido
            motivo = "raiz não é objeto"
        except FileNotFoundError:
            return embutido()
        except (OSError, ValueError) as erro:
            motivo = str(erro)

        estragado = self.caminho.parent / (self.caminho.name + ".corrompido")
        try:
            os.replace(self.caminho, estragado)
            guardado = f"; o anterior foi para {self.fs.show(estragado)}"
        except OSError:
            guardado = ""
        self.log(f"config   {self.fs.show(self.caminho)} ilegível ({motivo}); "
                 f"gravando sobre o padrão embutido{guardado}")
        return embutido()

    def reload(self):
        """Relê se o arquivo mudou. Devolve True quando releu.

        Comparar a marca do arquivo em vez de reabrir todo segundo: o
        arquivo muda uma vez por edição e o daemon acorda 86400 vezes por
        dia.

        A marca é (mtime, tamanho, INODE), e o inode não é excesso de
        zelo. Toda escrita disciplinada neste arquivo é `.tmp` +
        `os.replace()`, que troca o inode — o `vi` com backup faz o mesmo.
        Só o mtime bastaria se ele tivesse sempre resolução de
        nanossegundo, e não tem: ext4 com inode de 128 bytes arredonda
        para o segundo, e duas gravações dentro do mesmo segundo deixariam
        a segunda invisível até que uma terceira aparecesse. O inode pega
        a troca de arquivo mesmo quando o relógio não ajuda."""
        self._seed()
        try:
            estado = self.caminho.stat()
        except OSError:
            if self._marca is not None:
                self.log("config   arquivo sumiu; voltando ao padrão embutido")
                self.dados, self.origin, self._marca = embutido(), "padrão embutido", None
                return True
            return False

        marca = (estado.st_mtime_ns, estado.st_size, estado.st_ino)
        if marca == self._marca:
            return False
        relendo = self._marca is not None
        self._marca = marca

        try:
            lido = json.loads(self.caminho.read_text())
            if not isinstance(lido, dict):
                raise ValueError("raiz não é objeto")
        except (OSError, ValueError) as erro:
            # Config quebrada não derruba o console: ele volta ao padrão e
            # DIZ que voltou, no log e no `origin` do state.json.
            self.log(f"config   {self.fs.show(self.caminho)} ilegível ({erro}); "
                     "usando o padrão embutido")
            self.dados, self.origin = embutido(), "padrão embutido"
            return True

        self.dados = lido
        self.origin = self.fs.show(self.caminho)
        # Uma linha por edição, e nenhuma no start — a primeira leitura já
        # aparece no `origin` do state.json. É o que dá para ver, no
        # journal, que o daemon percebeu a gravação do editor de perfil.
        if relendo:
            self.log(f"config   {self.origin} mudou; perfil relido")
        return True

    # ------------------------------------------------------------------
    def curve(self):
        curva = self.dados.get("curve") or {}
        padrao = EMBUTIDO["curve"]
        idle = curva.get("wattsIdle")
        ponto = curva.get("wattsPerPoint")
        return {
            "wattsIdle": idle if isinstance(idle, (int, float)) else padrao["wattsIdle"],
            "wattsPerPoint": ponto if isinstance(ponto, (int, float)) else padrao["wattsPerPoint"],
            "calibrated": bool(curva.get("calibrated")),
        }

    def profile_for(self, appid):
        """Perfil do título, com o default cobrindo o que ele não disser.

        Valor fora do vocabulário do modelo cai para o default do eixo e é
        logado: perfil salvo por uma versão futura do editor não pode fazer
        o daemon aplicar uma string que o kernel não entende."""
        base = embutido()["default"]
        base.update(self._validado(self.dados.get("default"), "default"))
        titulo = (self.dados.get("games") or {}).get(str(appid))
        base.update(self._validado(titulo, str(appid)))
        return base

    def _validado(self, perfil, onde):
        if not isinstance(perfil, dict):
            return {}
        limpo = {}
        for eixo in score.AXES:
            valor = perfil.get(eixo)
            if valor is None:
                continue
            if score.weight_of(eixo, valor) is None:
                self.log(f"config   {onde}.{eixo} = {valor!r} não pertence ao "
                         "modelo de perfil; ignorado")
                continue
            limpo[eixo] = valor
        return limpo
