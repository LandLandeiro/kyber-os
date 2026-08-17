"""
Fixa o modelo de escore.

Este arquivo é a mitigação combinada para a duplicação entre
gameprofiled/score.py e kyber-shell/src/data/mock.js. Os números abaixo
foram lidos do mock, não deduzidos daqui: se alguém mexer no modelo de um
lado só, é isto que quebra.

Quebra em UM sentido: mudança no daemon derruba o teste, mudança no
launcher não. A saída de verdade é o modelo morar num lugar só — ver a
pendência no README.
"""

import unittest

from gameprofiled import score


class TestEscore(unittest.TestCase):
    def test_watts_dos_nove_escores(self):
        # kyber-shell: WATTS_IDLE 22, WATTS_PER_POINT 7.
        self.assertEqual(
            [score.watts_for(s, 22, 7) for s in range(9)],
            [22, 29, 36, 43, 50, 57, 64, 71, 78],
        )

    def test_74_watts_nao_existe(self):
        # O index.html do launcher afirmava 74 W durante quatro etapas.
        # Nenhum escore produz isso, e é bom que continue não produzindo.
        self.assertNotIn(74, [score.watts_for(s, 22, 7) for s in range(9)])

    def test_limiares_de_nivel(self):
        # chrome.js: i <= 2/8 quiet, i <= 5/8 nominal, resto hot.
        self.assertEqual([score.level_of(s) for s in range(9)], [
            "quiet", "quiet", "quiet",
            "nominal", "nominal", "nominal",
            "hot", "hot", "hot",
        ])

    def test_perfil_de_repouso_e_zero(self):
        repouso = {"governor": "powersave", "gpuLevel": "baixo",
                   "fpsLimit": "30", "priority": "padrão"}
        self.assertEqual(score.score_of(repouso), 0)
        self.assertEqual(score.intensity_of(0), 0)

    def test_perfil_padrao_de_jogo(self):
        padrao = {"governor": "performance", "gpuLevel": "auto",
                  "fpsLimit": "sem limite", "priority": "alta"}
        self.assertEqual(score.score_of(padrao), 6)
        self.assertEqual(score.intensity_of(6), 0.75)
        self.assertEqual(score.level_of(6), "hot")

    def test_limite_de_quadros_satura(self):
        # 'sem limite' não custa mais que 120: FPS_WEIGHT = [0, 1, 2, 2].
        self.assertEqual(score.weight_of("fpsLimit", "120"), 2)
        self.assertEqual(score.weight_of("fpsLimit", "sem limite"), 2)

    def test_valor_fora_do_modelo_nao_pontua(self):
        # `ondemand` é governor válido no kernel e desconhecido do console.
        self.assertIsNone(score.weight_of("governor", "ondemand"))
        self.assertEqual(score.score_of({"governor": "ondemand"}), 0)

    def test_eixo_ausente_nao_pontua(self):
        # fpsLimit nunca tem valor corrente: não há onde lê-lo.
        self.assertEqual(score.score_of({"governor": "performance"}), 2)
