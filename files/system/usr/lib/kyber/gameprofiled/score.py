"""
KYBER — modelo de escore do perfil de performance.

Os quatro eixos viram um escore 0..8; o escore vira posição na régua e
consumo estimado.

  ATENÇÃO — DUAS FONTES DE VERDADE.

  Este modelo também existe em kyber-shell, em src/data/mock.js. São dois
  repositórios, duas linguagens, e a mesma decisão de produto sobre como
  quatro seletores viram uma posição na régua. Se um lado mudar sozinho, a
  medição publicada aqui e a previsão desenhada lá passam a discordar sem
  que nada quebre — o pior tipo de divergência, porque a tela continua
  bonita.

  A mitigação é o teste tests/test_score.py, que fixa os nove valores
  possíveis de watts e os limiares de nível. Ele quebra se este arquivo
  mudar; não quebra se o mock.js mudar. A saída de verdade é o modelo
  morar num lugar só — ver a pendência registrada no README.
"""

# Ordem das opções = ordem crescente de intensidade. O índice É o peso.
GOVERNOR = ["powersave", "schedutil", "performance"]
GPU_LEVEL = ["baixo", "auto", "alto"]
FPS_LIMIT = ["30", "60", "120", "sem limite"]
PRIORITY = ["padrão", "alta", "tempo real"]

# 'sem limite' não custa mais que 120: o peso do limite de quadros satura.
FPS_WEIGHT = [0, 1, 2, 2]

SCORE_MAX = 8  # 2 + 2 + 2 + 2

AXES = ("governor", "gpuLevel", "fpsLimit", "priority")

_OPTIONS = {
    "governor": GOVERNOR,
    "gpuLevel": GPU_LEVEL,
    "fpsLimit": FPS_LIMIT,
    "priority": PRIORITY,
}


def options(axis):
    return list(_OPTIONS[axis])


def weight_of(axis, value):
    """Peso do valor no eixo, ou None se o valor não pertence ao modelo.

    O `current` de um eixo vem do kernel e pode ser algo que o launcher
    nunca ofereceu — `ondemand` no governor, `profile_peak` no DPM. Isso
    não é erro: é a máquina num estado que o console não sabe nomear.
    Devolver None deixa quem chama decidir, em vez de forçar o valor para
    dentro do modelo e mentir sobre o escore."""
    opcoes = _OPTIONS.get(axis)
    if opcoes is None or value not in opcoes:
        return None
    indice = opcoes.index(value)
    return FPS_WEIGHT[indice] if axis == "fpsLimit" else indice


def score_of(profile):
    """Escore 0..8 de um perfil {governor, gpuLevel, fpsLimit, priority}.

    Eixo desconhecido ou ausente pesa 0. É a escolha conservadora: um eixo
    que não sabemos ler não pode empurrar a régua para cima."""
    total = 0
    for eixo in AXES:
        peso = weight_of(eixo, (profile or {}).get(eixo))
        if peso is not None:
            total += peso
    return total


def intensity_of(score):
    return round(score / SCORE_MAX, 4)


def level_of(score):
    """Limiares do protótipo da Etapa 1: até 2 silencioso, até 5 equilibrado."""
    if score <= 2:
        return "quiet"
    if score <= 5:
        return "nominal"
    return "hot"


def watts_for(score, watts_idle, watts_per_point):
    return round(watts_idle + score * watts_per_point)
