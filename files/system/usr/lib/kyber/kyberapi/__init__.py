"""
KYBER — kyber-api

Processo SEM PRIVILÉGIO que traduz HTTP em comando de socket. É a única
peça que o launcher alcança para gravar, e a razão de ela existir é que
navegador não abre socket Unix.

Ele NÃO valida vocabulário, e isso é decisão, não preguiça. Se validasse,
haveria duas listas de valores válidos — uma aqui e uma no daemon — e
elas divergiriam no dia em que alguém mexesse numa só. Pior: alguém
passaria a acreditar que esta peça protege alguma coisa. Ela não protege.
Quem valida é o lado root, que trata toda mensagem como hostil
justamente porque este processo recebe entrada de uma porta TCP e é ele
que pode estar comprometido.

O que ele faz é estreito de propósito: duas rotas, uma por verbo do
socket. Não é um túnel — não dá para POSTar um objeto de comando
arbitrário e vê-lo chegar ao daemon. A lista fechada aparece na tabela de
rotas, do mesmo jeito que aparece na lista de comandos do outro lado.
"""

VERSION = "0.1.0"
