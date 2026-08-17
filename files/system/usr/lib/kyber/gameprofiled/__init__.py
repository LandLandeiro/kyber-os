"""
KYBER — gameprofiled

Daemon de estado da máquina. Mede o que dá para medir, aplica o perfil de
performance do título em execução, e publica tudo em /run/kyber/state.json
uma vez por segundo. O launcher lê esse arquivo por HTTP e não conversa
com o daemon de nenhuma outra forma.

O daemon NÃO expõe HTTP e NÃO aceita comando nesta versão. Juntar "recebe
entrada de fora" com "roda como root" é uma decisão difícil de desfazer
depois; quando o editor de perfil precisar escrever, o caminho previsto é
socket Unix com lista fechada de comandos mais um kyber-api sem privilégio.
O JSON continua sendo o canal de leitura.
"""

VERSION = "0.1.0"
