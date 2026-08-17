"""
Descoberta de sensores contra as três máquinas falsas.

O que estes testes protegem, em uma frase: nenhum caminho é fixo, e
ausência nunca vira zero.
"""

import tempfile
import unittest
from pathlib import Path

from gameprofiled import sensors
from gameprofiled.fs import Fs

from . import fakefs


class Base(unittest.TestCase):
    montar = staticmethod(fakefs.bare)

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.raiz = Path(self.dir.name)
        self.montar(self.raiz)
        self.fs = Fs(self.raiz)
        self.log = []


class TestDevBox(Base):
    montar = staticmethod(fakefs.intel_rx7600)

    def test_cpu_ignora_o_indice_e_acha_o_coretemp(self):
        sensor = sensors.find_cpu_temp(self.fs, self.log.append)
        self.assertEqual(sensor.read(), 61)
        # hwmon0 é o SSD a 38 °C e hwmon1 é o wi-fi. Ordenar por índice
        # daria 38 e ninguém notaria.
        self.assertEqual(sensor.source.driver, "coretemp")
        self.assertEqual(sensor.source.label, "Package id 0")
        self.assertIn("/sys/class/hwmon/hwmon7/", sensor.source.path)

    def test_cpu_pega_o_pacote_e_nao_o_nucleo_mais_quente(self):
        # Core 0 está a 64 °C. O header mostra o pacote.
        self.assertEqual(sensors.find_cpu_temp(self.fs).read(), 61)

    def test_gpu_vem_do_card_e_prefere_edge(self):
        gpu = sensors.find_gpu(self.fs, self.log.append)
        self.assertEqual(gpu.driver, "amdgpu")
        sensor = sensors.find_gpu_temp(self.fs, gpu)
        # junction está a 88 °C; edge é o que as ferramentas chamam de
        # temperatura da GPU.
        self.assertEqual(sensor.read(), 68)
        self.assertEqual(sensor.source.label, "edge")

    def test_conector_de_video_nao_e_confundido_com_placa(self):
        # card1-DP-1 casa com o glob card* e não tem driver nenhum.
        self.assertEqual(sensors.find_gpu(self.fs).card.name, "card1")

    def test_potencia_da_gpu(self):
        gpu = sensors.find_gpu(self.fs)
        sensor = sensors.find_gpu_power(self.fs, gpu)
        self.assertEqual(sensor.read(), 96.8)
        self.assertEqual(sensor.source.covers, "gpu")

    def test_rapl_ignora_subdominio(self):
        sensor = sensors.find_cpu_power(self.fs)
        self.assertEqual(sensor.source.covers, "package-0")
        self.assertNotIn(":0:0", sensor.source.path)

    def test_rapl_nao_reporta_na_primeira_leitura(self):
        relogio = iter([100.0, 101.0, 102.0])
        sensor = sensors.find_cpu_power(self.fs, relogio=lambda: next(relogio))
        # Sem intervalo anterior não há potência. Inventar aqui daria um
        # número enorme no primeiro segundo do daemon.
        self.assertIsNone(sensor.read())

        energia = self.raiz / "sys/class/powercap/intel-rapl:0/energy_uj"
        energia.write_text(str(502_113_884_512 + 38_400_000) + "\n")
        self.assertEqual(sensor.read(), 38.4)

    def test_rapl_trata_a_volta_do_contador(self):
        relogio = iter([10.0, 11.0])
        sensor = sensors.find_cpu_power(self.fs, relogio=lambda: next(relogio))
        energia = self.raiz / "sys/class/powercap/intel-rapl:0/energy_uj"
        energia.write_text(str(262_143_328_850 - 20_000_000) + "\n")
        sensor.read()
        energia.write_text(str(25_000_000) + "\n")
        # Sem tratar o wrap isto seria uma potência negativa gigante uma
        # vez a cada poucos minutos.
        self.assertEqual(sensor.read(), 45.0)


class TestConsole(Base):
    montar = staticmethod(fakefs.ryzen_5700g)

    def test_k10temp_cai_para_tctl_quando_nao_ha_tdie(self):
        sensor = sensors.find_cpu_temp(self.fs)
        self.assertEqual(sensor.source.label, "Tctl")
        self.assertEqual(sensor.read(), 44)

    def test_igpu_sem_temperatura_publica_ausencia(self):
        gpu = sensors.find_gpu(self.fs)
        self.assertIsNotNone(gpu.hwmon)  # o hwmon existe
        sensor = sensors.find_gpu_temp(self.fs, gpu, self.log.append)
        # ...e mesmo assim não há temperatura. Zero seria mentira e copiar
        # o cpuTemp daria duas células idênticas no header.
        self.assertIsNone(sensor.read())
        self.assertIsNone(sensor.source)
        self.assertTrue(any("ausente" in linha for linha in self.log))

    def test_rapl_da_amd_usa_o_mesmo_caminho_da_intel(self):
        self.assertEqual(sensors.find_cpu_power(self.fs).source.driver, "intel-rapl")


class TestSemSensor(Base):
    montar = staticmethod(fakefs.bare)

    def test_tudo_ausente_e_nada_estoura(self):
        for sensor in (
            sensors.find_cpu_temp(self.fs, self.log.append),
            sensors.find_gpu_temp(self.fs, None, self.log.append),
            sensors.find_gpu_power(self.fs, None, self.log.append),
            sensors.find_cpu_power(self.fs, self.log.append),
        ):
            self.assertIsNone(sensor.read())
            self.assertIsNone(sensor.source)
        self.assertIsNone(sensors.find_gpu(self.fs, self.log.append))

    def test_a_busca_frustrada_vai_para_o_log(self):
        sensors.find_cpu_temp(self.fs, self.log.append)
        # Quem for depurar um traço no header precisa saber ONDE se
        # procurou, não só que não se achou.
        self.assertTrue(any("/sys/class/hwmon" in linha for linha in self.log))


class TestDuasPlacas(Base):
    montar = staticmethod(fakefs.dual_gpu)

    def test_escolhe_a_de_mais_vram(self):
        gpu = sensors.find_gpu(self.fs, self.log.append)
        self.assertEqual(gpu.card.name, "card1")
        self.assertEqual(sensors.find_gpu_temp(self.fs, gpu).read(), 68)
        # As duas candidatas ficam no log: quando o console medir a placa
        # errada, a resposta está lá.
        self.assertEqual(sum("candidata" in l for l in self.log), 2)
