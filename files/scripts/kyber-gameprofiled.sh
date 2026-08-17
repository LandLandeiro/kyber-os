#!/usr/bin/env bash
#
# Monta o gameprofiled na imagem: confere que ele sobe e cria o canal de
# leitura para o launcher.
#
# ---------------------------------------------------------------------
# O canal de leitura entre o gameprofiled e o launcher.
#
# O daemon publica em /run/kyber/state.json e não expõe HTTP. O launcher
# fala HTTP e só enxerga a árvore que o darkhttpd serve. O symlink é o que
# junta os dois sem dar porta de entrada a um processo que roda como root.
#
# Ele existe como script de build e não como arquivo versionado porque
# /files/system/usr/share/kyber/launcher/ está no .gitignore — o launcher
# é buscado do kyber-shell pelo CI — e o git não permite reincluir um
# arquivo dentro de um diretório excluído.
#
# O alvo não existe na hora do build: /run só é povoado em runtime, pelo
# RuntimeDirectory= da unit. Symlink pendurado na imagem é o esperado.
#
# O darkhttpd segue este symlink porque nunca resolve caminho: não tem
# lstat, realpath nem O_NOFOLLOW, e abre o alvo com open() puro. É também
# por isso que a unit dele não pode ganhar --chroot; ver o comentário lá.

set -oue pipefail

# ---------------------------------------------------------------------
# O daemon existe e importa.
#
# Sao duas falhas que nao quebram o build sozinhas e so aparecem no boot,
# como uma unit em restart eterno: python3 ausente da imagem base, e erro
# de sintaxe no proprio daemon. Importar o grafo inteiro aqui custa
# milissegundos e transforma as duas em build vermelho.
#
# DONTWRITEBYTECODE porque __pycache__ nao tem o que fazer dentro de /usr.
# ---------------------------------------------------------------------
command -v python3
test -f /usr/lib/kyber/gameprofiled/__main__.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/usr/lib/kyber \
    python3 -P -c 'import gameprofiled.__main__'
python3 -c 'import json,sys; json.load(open(sys.argv[1]))' \
    /usr/share/kyber/profiles.default.json

# ---------------------------------------------------------------------
install -d /usr/share/kyber/launcher
ln -sfn /run/kyber/state.json /usr/share/kyber/launcher/state.json

# Falha aqui é melhor que um console que boota mostrando SEM LEITURA para
# sempre sem ninguém saber por quê.
test -L /usr/share/kyber/launcher/state.json
echo "kyber: state.json -> $(readlink /usr/share/kyber/launcher/state.json)"
