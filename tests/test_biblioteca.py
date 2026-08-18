"""
A biblioteca Steam: os dois parsers e a junção das três fontes.

Roda inteiro num Mac, contra árvores de Steam falsas — nenhuma Steam
instalada, nenhuma rede. O que estes testes fixam, e por quê:

  · runtime NÃO aparece na prateleira, e a distinção vem do appinfo.vdf
    binário. É o caso do console: 3 títulos instalados, 2 deles runtime,
    e nada no appmanifest os separa;
  · "Game" e "game" são a mesma coisa. No arquivo real convivem as duas
    grafias, 42 contra 9, e comparar exato esconde nove jogos calado;
  · tipo AUSENTE mostra o título. O appinfo é cache: não saber é
    diferente de saber que não. Jogo sumindo é bug silencioso;
  · caminho nunca se compara por string. /var/home e /home são o mesmo
    diretório no console e strings diferentes em qualquer lugar;
  · epoch 0 vira None e não 1970;
  · o parser binário fecha no byte que cada entrada declara — a
    conferência que o próprio formato oferece.
"""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from kyberlibrary import appinfo, biblioteca, vdf
from kyberlibrary.__main__ import Servidor

from . import fakesteam

ORIGEM = "http://127.0.0.1:8787"


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.raiz = Path(self.dir.name) / "Steam"
        self.linhas = []

    def log(self, mensagem):
        self.linhas.append(mensagem)

    def montar(self):
        return biblioteca.montar(self.raiz, self.log)

    def por_nome(self, jogos):
        return {j["name"]: j for j in jogos}


# ----------------------------------------------------------------------
class TestVDF(unittest.TestCase):
    def test_bloco_aninhado_e_escapes(self):
        d = vdf.carregar('"a"\n{\n\t"b"\t\t"1"\n\t"c"\n\t{\n\t\t"d"\t"x\\"y"\n\t}\n}\n')
        self.assertEqual(d, {"a": {"b": "1", "c": {"d": 'x"y'}}})

    def test_bom_nao_derruba_o_arquivo(self):
        # 30 dos 96 .vdf de uma instalação real começam com BOM. Sem
        # tratar, o erro aponta para a linha 2 de um arquivo cuja linha 2
        # está perfeita.
        d = vdf.carregar('﻿"a"\n{\n\t"b"\t"1"\n}\n')
        self.assertEqual(d, {"a": {"b": "1"}})

    def test_comentario_e_condicional_sao_ignorados(self):
        d = vdf.carregar('// nota\n"a"\n{\n\t"b" [$WIN32]\t"1"\n}\n')
        self.assertEqual(d, {"a": {"b": "1"}})

    def test_chave_duplicada_a_ultima_vence(self):
        # Declarado, não acidental: é assim que o formato quebra parser
        # pequeno, e é o que faz 76 dos 79 arquivos de Steam Input
        # divergirem da referência. Nenhum arquivo que o KYBER lê tem
        # duplicata — mas o comportamento tem que ser previsível.
        self.assertEqual(vdf.carregar('"a"\n{\n"b" "1"\n"b" "2"\n}\n'),
                         {"a": {"b": "2"}})

    def test_arquivo_truncado_falha_alto(self):
        with self.assertRaises(vdf.ErroDeVDF):
            vdf.carregar('"a"\n{\n\t"b"\t"1"\n')

    def test_chave_sem_valor_falha_alto(self):
        with self.assertRaises(vdf.ErroDeVDF):
            vdf.carregar('"a"\n{\n\t"b"\n}\n')

    def test_uXXXX_fica_literal(self):
        # Nem este parser nem o de referência decodificam. Fixado para que
        # a decisão de não decodificar seja visível, e não um esquecimento.
        d = vdf.carregar('"a"\n{\n\t"n"\t"HELLDIVERS\\u2122 2"\n}\n')
        self.assertEqual(d["a"]["n"], "HELLDIVERS\\u2122 2")


# ----------------------------------------------------------------------
class TestAppinfo(Base):
    def test_le_o_tipo_de_cada_app(self):
        fakesteam.appinfo(self.raiz, {
            10: {"type": "Game", "name": "um"},
            20: {"type": "Tool", "name": "dois"},
        })
        arq = appinfo.carregar_arquivo(self.raiz / "appcache/appinfo.vdf")
        achados = {a: (d["appinfo"]["common"]["type"]) for a, d in arq.apps()}
        self.assertEqual(achados, {10: "Game", 20: "Tool"})

    def test_parada_antecipada_nao_le_o_resto(self):
        fakesteam.appinfo(self.raiz, {i: {"type": "Game"} for i in range(10, 60, 10)})
        arq = appinfo.carregar_arquivo(self.raiz / "appcache/appinfo.vdf")
        self.assertEqual([a for a, _ in arq.apps(apenas={20})], [20])

    def test_v27_sem_tabela_de_strings(self):
        # A v28 trocou chave-string por índice. Ler v27 com leitor de v29
        # (e vice-versa) devolve lixo sem reclamar, então as duas entram.
        fakesteam.appinfo(self.raiz, {10: {"type": "Game"}}, versao=27)
        arq = appinfo.carregar_arquivo(self.raiz / "appcache/appinfo.vdf")
        self.assertEqual(arq.versao, 27)
        self.assertEqual([a for a, _ in arq.apps()], [10])

    def test_magic_desconhecido_falha_alto(self):
        alvo = self.raiz / "appcache/appinfo.vdf"
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(b"\x00" * 64)
        with self.assertRaises(appinfo.ErroDeAppinfo):
            appinfo.carregar_arquivo(alvo)

    def test_cada_entrada_fecha_no_tamanho_declarado(self):
        # A conferência que o formato oferece de graça: se o parser de kv
        # terminar num byte diferente do que a entrada declarou, ele leu
        # errado. Num appinfo.vdf real de 550 KB isso vale para 285 de 285.
        fakesteam.appinfo(self.raiz, {
            10: {"type": "Game", "name": "um", "steam_release_date": 1622505600},
            20: {"type": "Tool", "name": "dois"},
            30: {"type": "game", "name": "tres"},
        })
        arq = appinfo.carregar_arquivo(self.raiz / "appcache/appinfo.vdf")
        self.assertEqual(len(list(arq.apps())), 3)   # levantaria se não fechasse

    def test_normalizacao_de_Game_e_game(self):
        self.assertTrue(appinfo.eh_jogavel("Game"))
        self.assertTrue(appinfo.eh_jogavel("game"))
        self.assertTrue(appinfo.eh_jogavel("  GAME  "))
        self.assertTrue(appinfo.eh_jogavel("Demo"))
        self.assertFalse(appinfo.eh_jogavel("Tool"))
        self.assertFalse(appinfo.eh_jogavel("DLC"))
        self.assertFalse(appinfo.eh_jogavel("Config"))
        # None não é False, e a diferença decide se o título aparece.
        self.assertIsNone(appinfo.eh_jogavel(None))


# ----------------------------------------------------------------------
class TestConsole(Base):
    """O aparelho como ele está: 3 instalados, 2 runtime."""

    def setUp(self):
        super().setUp()
        fakesteam.console(self.raiz)

    def test_runtime_fica_fora_da_prateleira(self):
        jogos = self.montar()
        self.assertEqual([j["name"] for j in jogos], ["Muck"])
        self.assertTrue(any("não jogáveis fora da prateleira" in l
                            for l in self.linhas))

    def test_o_titulo_traz_os_campos_das_tres_fontes(self):
        muck = self.por_nome(self.montar())["Muck"]
        self.assertEqual(muck["appid"], 1625450)
        self.assertTrue(muck["installed"])                 # .acf StateFlags
        self.assertAlmostEqual(muck["sizeGB"], 0.41, places=2)  # .acf SizeOnDisk
        self.assertAlmostEqual(muck["hoursTotal"], 2.3, places=1)  # localconfig
        self.assertEqual(muck["lastPlayed"], "2026-08-16")     # .acf LastPlayed
        self.assertEqual(muck["year"], 2021)               # appinfo
        self.assertTrue(muck["hasArt"])                    # disco
        self.assertFalse(muck["hasHero"])                  # a Steam não baixou
        self.assertIsNone(muck["genre"])                   # não se inventa

    def test_genero_nunca_e_inventado(self):
        for jogo in self.montar():
            self.assertIsNone(jogo["genre"])

    def test_nunca_jogado_e_None_e_nao_1970(self):
        fakesteam.manifesto(self.raiz / "steamapps", 42, "Novo", ultimo=0)
        fakesteam.appinfo(self.raiz, {
            1070560: {"type": "Tool"}, 1391110: {"type": "Tool"},
            1625450: {"type": "game", "name": "Muck",
                      "steam_release_date": 1622505600},
            42: {"type": "Game", "name": "Novo"},
        })
        novo = self.por_nome(self.montar())["Novo"]
        self.assertIsNone(novo["lastPlayed"])
        self.assertIsNone(novo["hoursTotal"])

    def test_baixando_pela_metade_nao_conta_como_instalado(self):
        fakesteam.manifesto(self.raiz / "steamapps", 43, "Meio", flags=1026)
        fakesteam.appinfo(self.raiz, {43: {"type": "Game", "name": "Meio"}})
        self.assertFalse(self.por_nome(self.montar())["Meio"]["installed"])


class TestTipoAusente(Base):
    def test_sem_appinfo_todos_aparecem_e_o_journal_diz(self):
        # O appinfo é cache. Não existir não é motivo para a prateleira
        # ficar vazia — runtime aparecendo é feio, jogo sumindo é bug
        # silencioso, e este projeto já catalogou essa classe vezes demais.
        fakesteam.console(self.raiz)
        (self.raiz / "appcache/appinfo.vdf").unlink()
        jogos = self.montar()
        self.assertEqual(len(jogos), 3)
        self.assertTrue(any("sem tipo conhecido" in l for l in self.linhas))

    def test_appinfo_corrompido_nao_derruba_a_biblioteca(self):
        fakesteam.console(self.raiz)
        (self.raiz / "appcache/appinfo.vdf").write_bytes(b"lixo" * 40)
        self.assertEqual(len(self.montar()), 3)
        self.assertTrue(any("ilegível" in l for l in self.linhas))

    def test_manifesto_ruim_perde_um_titulo_e_nao_todos(self):
        fakesteam.console(self.raiz)
        (self.raiz / "steamapps/appmanifest_999.acf").write_text('"AppState"\n{\n')
        jogos = self.montar()
        self.assertEqual([j["name"] for j in jogos], ["Muck"])
        self.assertTrue(any("appmanifest_999.acf ignorado" in l
                            for l in self.linhas))


class TestCaminhos(Base):
    def test_duas_bibliotecas_em_discos_diferentes(self):
        segunda = Path(self.dir.name) / "SSD2/SteamLibrary"
        fakesteam.duas_bibliotecas(self.raiz, segunda)
        nomes = [j["name"] for j in self.montar()]
        self.assertEqual(nomes, ["Counter-Strike 2", "Half-Life 2"])

    def test_caminho_por_symlink_nao_duplica_a_biblioteca(self):
        # O caso do ostree: o libraryfolders diz /var/home/... e o $HOME
        # diz /home/..., o mesmo diretório por caminhos diferentes.
        # Comparar string listaria a mesma biblioteca duas vezes.
        fakesteam.console(self.raiz)
        atalho = Path(self.dir.name) / "atalho"
        atalho.symlink_to(self.raiz)
        fakesteam.libraryfolders(self.raiz, [str(self.raiz), str(atalho)])
        self.assertEqual([j["name"] for j in self.montar()], ["Muck"])
        bibs = [l for l in self.linhas if "biblioteca [" in l]
        self.assertEqual(len(bibs), 1, f"listou {len(bibs)}: {bibs}")

    def test_steam_ausente(self):
        self.assertIsNone(biblioteca.achar_raiz(home=self.dir.name))

    def test_steam_sem_jogos(self):
        fakesteam.vazia(self.raiz)
        self.assertEqual(self.montar(), [])


# ----------------------------------------------------------------------
class TestHTTP(Base):
    def setUp(self):
        super().setUp()
        # O log do servidor vai para stderr, que é onde o journal o quer e
        # onde a suíte não o quer: linha de HTTP no meio de 230 testes
        # esconde a falha de verdade.
        import kyberlibrary.__main__ as mod
        original = mod.log
        mod.log = self.log
        self.addCleanup(lambda: setattr(mod, "log", original))

        fakesteam.console(self.raiz)
        self.http = Servidor(("127.0.0.1", 0), ORIGEM, self.raiz)
        self.addCleanup(self.http.server_close)
        self.porta = self.http.server_address[1]
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.shutdown)

    def pedir(self, caminho, cabecalhos=None):
        pedido = urllib.request.Request(
            f"http://127.0.0.1:{self.porta}{caminho}")
        pedido.add_header("Origin", ORIGEM)
        for chave, valor in (cabecalhos or {}).items():
            pedido.add_header(chave, valor)
        try:
            with urllib.request.urlopen(pedido, timeout=5) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, dict(e.headers), e.read()

    def test_library_json_traz_so_o_jogavel(self):
        status, cabecalhos, corpo = self.pedir("/library.json")
        self.assertEqual(status, 200)
        self.assertEqual(cabecalhos["Access-Control-Allow-Origin"], ORIGEM)
        self.assertEqual(cabecalhos["Cache-Control"], "no-store")
        dados = json.loads(corpo)
        self.assertTrue(dados["ok"])
        self.assertEqual([j["name"] for j in dados["games"]], ["Muck"])

    def test_arte_do_disco_com_etag_e_304(self):
        status, cabecalhos, corpo = self.pedir("/art/1625450/cover")
        self.assertEqual(status, 200)
        self.assertEqual(cabecalhos["Content-Type"], "image/jpeg")
        etag = cabecalhos["ETag"]
        self.assertTrue(corpo)
        status2, _, corpo2 = self.pedir("/art/1625450/cover",
                                        {"If-None-Match": etag})
        self.assertEqual(status2, 304)
        self.assertEqual(corpo2, b"")

    def test_sem_arte_e_404_e_e_rotina(self):
        # Não é erro: a capa vertical não existe para 3 em cada 4 títulos
        # no catálogo da Valve. O launcher desenha a capa gerada.
        status, _, corpo = self.pedir("/art/1625450/hero")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(corpo)["error"], "sem_arte")

    def test_especie_fora_da_tabela_nao_vira_caminho(self):
        for rota in ("/art/1625450/..%2F..%2Fetc%2Fpasswd",
                     "/art/1625450/passwd", "/art/-1/cover",
                     "/art/abc/cover"):
            with self.subTest(rota=rota):
                self.assertEqual(self.pedir(rota)[0], 404)

    def test_nao_ha_rota_de_escrita(self):
        for metodo in ("POST", "PUT", "DELETE", "PATCH"):
            with self.subTest(metodo=metodo):
                pedido = urllib.request.Request(
                    f"http://127.0.0.1:{self.porta}/library.json", method=metodo)
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(pedido, timeout=5)
                self.assertEqual(ctx.exception.code, 501)
                ctx.exception.close()   # senão o urllib avisa no GC

    def test_rota_desconhecida(self):
        self.assertEqual(self.pedir("/games")[0], 404)


# ----------------------------------------------------------------------
def _appinfo_de_verdade():
    """Um appinfo.vdf real desta máquina, se houver Steam instalada."""
    import os
    candidatos = (
        "~/.local/share/Steam/appcache/appinfo.vdf",
        "~/.steam/steam/appcache/appinfo.vdf",
        "~/Library/Application Support/Steam/appcache/appinfo.vdf",
    )
    for bruto in candidatos:
        caminho = Path(os.path.expanduser(bruto))
        if caminho.is_file():
            return caminho
    return None


REAL = _appinfo_de_verdade()


@unittest.skipUnless(REAL, "sem Steam instalada nesta máquina")
class TestAppinfoDeVerdade(unittest.TestCase):
    """A suíte inteira roda sem Steam. Quando há uma, ela também prova o
    parser contra o arquivo que a Valve escreveu — que é o único jeito de
    saber que a árvore falsa não está só concordando consigo mesma."""

    def test_o_arquivo_inteiro_e_consumido_sem_folga(self):
        arq = appinfo.carregar_arquivo(REAL)
        # Cada entrada declara o próprio tamanho e o parser confere; se
        # alguma não fechasse, `apps()` levantaria.
        total = sum(1 for _ in arq.apps())
        self.assertGreater(total, 0)
        self.assertIn(arq.versao, (27, 28, 29))

    def test_as_duas_grafias_de_game_convivem_de_verdade(self):
        # 42 "Game" e 9 "game" no arquivo que motivou a normalização.
        arq = appinfo.carregar_arquivo(REAL)
        grafias = set()
        for _, dados in arq.apps():
            tipo = (dados.get("appinfo", dados) or {}).get("common", {}).get("type")
            if isinstance(tipo, str) and tipo.lower() == "game":
                grafias.add(tipo)
        if len(grafias) < 2:
            self.skipTest(f"esta instalação só tem {grafias or 'nenhuma'}")
        self.assertTrue(all(appinfo.eh_jogavel(g) for g in grafias))


if __name__ == "__main__":
    unittest.main()
