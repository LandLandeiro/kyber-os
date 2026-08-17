"""
KYBER — perfis por título.

O daemon não aceita comando nesta versão, então o perfil que ele aplica
tem que vir de disco. `/var/lib/kyber/profiles.json` é esse disco, e é a
costura onde o futuro kyber-api vai escrever quando o editor de perfil
puder salvar — o formato já é o que ele vai gravar.

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

import json
import shutil
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


class Config:
    def __init__(self, fs, caminho=CAMINHO, semente=SEMENTE, log=None):
        self.fs = fs
        self.caminho = fs.path(caminho)
        self.semente = fs.path(semente)
        self.log = log or (lambda _: None)
        self.origin = "padrão embutido"
        self.dados = dict(EMBUTIDO)
        self._marca = None
        self.reload()

    # ------------------------------------------------------------------
    def _seed(self):
        if self.caminho.exists() or not self.semente.exists():
            return
        try:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.semente, self.caminho)
            self.log(f"config   semeado {self.fs.show(self.caminho)} "
                     f"de {self.fs.show(self.semente)}")
        except OSError as erro:
            self.log(f"config   não deu para semear: {erro}")

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
                self.dados, self.origin, self._marca = dict(EMBUTIDO), "padrão embutido", None
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
            self.dados, self.origin = dict(EMBUTIDO), "padrão embutido"
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
        base = dict(EMBUTIDO["default"])
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
