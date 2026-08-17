"""
KYBER — gameprofiled

Daemon de estado da máquina. Mede o que dá para medir, aplica o perfil de
performance do título em execução, e publica tudo em /run/kyber/state.json
uma vez por segundo. O launcher lê esse arquivo por HTTP e não conversa
com o daemon de nenhuma outra forma.

O daemon NÃO expõe HTTP. Juntar "recebe entrada de fora" com "roda como
root" é decisão difícil de desfazer depois, então a escrita entra por um
socket Unix com lista FECHADA de dois verbos — set-profile e
clear-profile — e quem fala HTTP é o kyber-api, um processo sem
privilégio. Ver control.py.

O socket só escreve, e escreve no ARQUIVO: ele não fala com o
ProfileManager nem com eixo nenhum. O daemon descobre a mudança pelo
mesmo mtime por onde descobre uma edição com o `vi`, e é isso que faz
existir um caminho só. A leitura continua sendo arquivo servido por
symlink: state.json para o que a máquina fez, profiles.json para o que
foi pedido.
"""

VERSION = "0.1.0"
