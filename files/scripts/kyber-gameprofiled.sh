#!/usr/bin/env bash
#
# Monta o gameprofiled na imagem: confere que ele sobe e cria o canal de
# leitura para o launcher.
#
# ---------------------------------------------------------------------
# Os DOIS canais de leitura entre o gameprofiled e o launcher.
#
# O daemon publica em /run/kyber/state.json e não expõe HTTP. O launcher
# fala HTTP e só enxerga a árvore que o darkhttpd serve. Os symlinks são o
# que junta os dois sem dar porta de entrada a um processo que roda como
# root.
#
#   state.json     o que a MÁQUINA FEZ. Medição e estado por eixo, 1x/s.
#   profiles.json  o que foi PEDIDO. O perfil por título, como está gravado.
#
# São perguntas diferentes e por isso são arquivos diferentes. A tela 04
# precisa das duas: `available` (do state.json) para não oferecer controle
# que a máquina não tem, e o perfil gravado (do profiles.json) para abrir
# mostrando o que foi salvo em vez do que o mock lembra.
#
# O profiles.json não passa pelo /run: ele MORA em /var/lib/kyber, que é
# estado de máquina e sobrevive a atualização de imagem, e o symlink
# aponta direto para lá. Publicar uma cópia em /run daria uma janela em
# que as duas versões discordam, e a autoridade tem que ser uma só.
#
# Ler pelo HTTP é seguro contra leitura rasgada pela mesma razão que o
# state.json é: toda escrita nele é .tmp + rename(2). Ver Config._entregar.
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
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/usr/lib/kyber \
    python3 -P -c 'import kyberapi.__main__'
python3 -c 'import json,sys; json.load(open(sys.argv[1]))' \
    /usr/share/kyber/profiles.default.json

# ---------------------------------------------------------------------
install -d /usr/share/kyber/launcher
ln -sfn /run/kyber/state.json /usr/share/kyber/launcher/state.json
ln -sfn /var/lib/kyber/profiles.json /usr/share/kyber/launcher/profiles.json

# Falha aqui é melhor que um console que boota mostrando SEM LEITURA para
# sempre sem ninguém saber por quê.
for canal in state profiles; do
    test -L "/usr/share/kyber/launcher/${canal}.json"
    echo "kyber: ${canal}.json -> $(readlink "/usr/share/kyber/launcher/${canal}.json")"
done
