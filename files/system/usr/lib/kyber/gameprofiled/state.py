"""
KYBER — montagem e publicação do state.json.

DUAS ARMADILHAS DO POLLING MORAM AQUI.

1. ESCRITA ATÔMICA. O darkhttpd faz stat e sendfile sem lock nenhum: ler
   no meio de uma escrita devolve JSON truncado, e o launcher recebe um
   corpo que não parseia. A escrita vai para state.json.tmp no MESMO
   tmpfs e entra por os.replace(), que é rename(2) e é atômico. Quem já
   tinha o arquivo aberto continua lendo o inode antigo até o fim.

   O .tmp fica de fora do symlink de propósito: só state.json é
   publicado em /usr/share/kyber/launcher/, então o arquivo pela metade
   não é alcançável por HTTP nem por um instante.

   Sem fsync: /run é tmpfs, onde o page cache É o armazenamento. fsync
   ali não protege de nada e o rename já ordena o que precisa ser
   ordenado.

2. If-Modified-Since DE 1 SEGUNDO. O darkhttpd compara data de
   modificação como STRING e a granularidade é de um segundo. Duas
   escritas dentro do mesmo segundo fazem o cliente receber 304 e servir
   o corpo em cache — o `at` chega repetido, e o vigia de telemetria do
   launcher declara LEITURA PARADA num console perfeitamente saudável.

   A defesa é publicar com a FASE TRAVADA em X,5 s. Não basta esperar um
   segundo entre escritas: duas escritas separadas por 1,0 s podem cair
   em X,99 e X+1,01 e ainda assim... não podem, mas basta um atraso de
   escalonamento para cair em X,4 e X+1,6, e o par X,99/X+1,00 seria o
   mesmo segundo inteiro. Ancorar no meio do segundo tira a
   possibilidade em vez de torná-la improvável.
"""

import json
import math
import os
from typing import NamedTuple

from . import score


class Reading(NamedTuple):
    """Uma leitura já feita, com a fonte que a produziu.

    `build` recebe isto em vez do sensor porque montar o documento não
    pode ter efeito colateral: um contador de energia lido duas vezes na
    mesma passagem devolveria potência calculada sobre um intervalo de
    zero segundo."""

    value: object
    source: object

SCHEMA = 1
CAMINHO = "/run/kyber/state.json"


def next_publish(now):
    """Próximo instante X,5 s. Ver a armadilha 2 no topo do arquivo."""
    alvo = math.floor(now) + 0.5
    if alvo <= now:
        alvo += 1.0
    return alvo


class Publisher:
    def __init__(self, fs, caminho=CAMINHO):
        self.destino = fs.path(caminho)
        self.temporario = self.destino.parent / (self.destino.name + ".tmp")

    def publish(self, payload):
        self.destino.parent.mkdir(parents=True, exist_ok=True)
        with open(self.temporario, "w", encoding="utf-8") as arquivo:
            json.dump(payload, arquivo, ensure_ascii=False, indent=2)
            arquivo.write("\n")
        # nobody, que é quem roda o darkhttpd, precisa de +r. O diretório
        # ganha +x pelo RuntimeDirectoryMode da unit.
        os.chmod(self.temporario, 0o644)
        os.replace(self.temporario, self.destino)

    def remove(self):
        """Sumir com o arquivo é o que faz o launcher dizer SEM LEITURA em
        vez de LEITURA PARADA. Deixar o último estado no disco depois de o
        daemon sair seria publicar um número que ninguém mais atualiza."""
        for caminho in (self.temporario, self.destino):
            try:
                caminho.unlink()
            except OSError:
                pass


def build(*, at, interval_ms, readings, curve, manager, game, version,
          started_at, measured_sum=None):
    """O state.json inteiro, como dicionário.

    Função pura: recebe leituras já feitas e devolve o documento. É o que
    permite testá-la sem sensor, sem relógio e sem disco."""
    perfil_corrente = manager.current_profile()
    escore = score.score_of(perfil_corrente)

    valores = {nome: leitura.value for nome, leitura in readings.items()}
    fontes = {
        nome: (leitura.source.to_json() if leitura.source else None)
        for nome, leitura in readings.items()
    }

    documento = {
        "schema": SCHEMA,
        "at": at,
        "intervalMs": interval_ms,

        "cpuTemp": valores.get("cpuTemp"),
        "gpuTemp": valores.get("gpuTemp"),
        "cpuWatts": valores.get("cpuWatts"),
        "gpuWatts": valores.get("gpuWatts"),

        "watts": score.watts_for(escore, curve["wattsIdle"], curve["wattsPerPoint"]),
        "intensity": score.intensity_of(escore),
        # Quadro por segundo só existe dentro do compositor. O daemon não
        # tem canal com o gamescope e não inventa o número.
        "fps": None,

        "wattsIdle": curve["wattsIdle"],
        "wattsPerPoint": curve["wattsPerPoint"],

        "runningGame": game.to_json() if game else None,
        "profile": manager.to_json(),
        "sources": fontes,
        "daemon": {"version": version, "startedAt": started_at},
    }

    documento["sources"]["watts"] = watts_source(curve, documento["watts"], measured_sum)
    documento["sources"]["fps"] = {
        "kind": "absent",
        "note": "quadros só existem dentro do compositor; o daemon não tem "
                "canal com o gamescope",
    }
    return documento


def watts_source(curve, estimado, measured_sum=None):
    """A nota que impede alguém de se acostumar com o número errado.

    `watts` NUNCA é medição, nem com a curva calibrada: os dois números da
    curva podem ser medidos, mas o valor publicado continua saindo de um
    modelo. O que a calibração muda é a qualidade da constante, e a nota
    diz qual das duas está em uso.

    Quando há sensor de componente, a soma medida entra na nota ao lado do
    estimado. Nenhum sensor destas máquinas cobre o consumo do console —
    RAPL mede o pacote da CPU, power1_average mede a GPU, e a soma dos
    dois ainda ignora placa-mãe, memória e perda da fonte. Publicar a soma
    como `watts` seria dar cara de medição a um número que não é. Mas
    deixá-la invisível é como se acostuma com uma régua errada."""
    if curve.get("calibrated"):
        nota = (f"curva calibrada ({curve['wattsIdle']} W de repouso + "
                f"{curve['wattsPerPoint']} W por ponto)")
    else:
        nota = (f"curva NÃO calibrada ({curve['wattsIdle']} W de repouso + "
                f"{curve['wattsPerPoint']} W por ponto, chute do protótipo)")

    if measured_sum is not None:
        nota += (f"; estimado {estimado} W contra {measured_sum:.1f} W somando os "
                 "componentes medidos, que não cobrem placa-mãe, memória nem "
                 "perda da fonte")
    else:
        nota += "; nenhum sensor desta máquina cobre o consumo do console"

    return {"kind": "estimated", "note": nota}
