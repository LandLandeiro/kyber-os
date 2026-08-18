"""
KYBER — kyber-power

Os quatro verbos de energia do launcher, atrás de HTTP em loopback:
desligar, reiniciar, suspender, ir para o Modo Desktop.

POR QUE NÃO DENTRO DO kyber-api, que já existe, já fala HTTP, já resolveu
CORS e já é a peça que o launcher alcança.

Porque o kyber-api roda como o usuário `kyber-api`, cuja autoridade
inteira é ter escrita num socket Unix. A unit dele tem
CapabilityBoundingSet vazio, SystemCallFilter=@system-service,
IPAddressDeny=any e nenhuma sessão. Ele é o processo que este projeto
construiu para NÃO PODER NADA, justamente por ser o que recebe bytes de
uma porta TCP e, portanto, o que pode estar comprometido. Fazer esse
processo desligar a máquina é dar poder de desligar a máquina ao usuário
escolhido por não ter poder nenhum.

Energia não precisa de autoridade nova. O logind já responde `yes` em
allow_active para power-off, reboot e suspend
(org.freedesktop.login1.policy): quem está sentado na frente do console,
com sessão ativa, JÁ PODE desligá-lo. Então o lugar certo desta peça é
dentro da sessão da pessoa — outro domínio de privilégio que o
kyber-api, por construção. Este processo não pode nada que o dono da
sessão já não pudesse pelo terminal; é conveniência de transporte para
quem não tem teclado, e nada além disso.

O SEGUNDO MOTIVO É A LISTA FECHADA. `set-profile, clear-profile` é
auditável porque tem um ASSUNTO: dá para perguntar "este daemon precisa
fazer mais alguma coisa com perfil?" e responder. Uma lista que mistura
perfil e energia não tem essa pergunta — ela deixa de ser fronteira e
vira menu, e a próxima adição não encontra mais nenhum argumento pela
frente.

O TERCEIRO É DOMÍNIO DE FALHA. Hoje, kyber-api fora do ar quer dizer
"salvar falha" e o console continua inteiro. Com energia lá dentro, a
mesma queda passaria a querer dizer "não dá para desligar o console".
São criticidades diferentes atrás de um mesmo laço de restart.
"""

VERSION = "0.1.0"
