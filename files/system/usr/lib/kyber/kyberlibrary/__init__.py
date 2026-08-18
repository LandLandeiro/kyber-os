"""
KYBER — kyber-library

A biblioteca Steam de verdade, no lugar dos doze títulos do mock.

RODA COMO O DONO DA SESSÃO, e aqui isso não é preferência: o $HOME do
console é `drwx------`. O darkhttpd roda como `nobody` e não passa do
primeiro diretório do caminho — medido com `namei` no aparelho. Não há
outro lugar de onde esses arquivos sejam legíveis por direito próprio.

SÓ LÊ. Duas rotas, as duas GET, e nenhum verbo de escrita. É a mesma
linha que separa esta peça do kyber-power, e a linha não é "um processo
por assunto": é o que a peça PODE FAZER. O kyber-power age sobre a
máquina — desliga, reinicia, sai da sessão. Esta lê arquivos. Juntar as
duas poria uma superfície de leitura dentro do processo que encerra a
sessão, e daria a um leitor a capacidade de desligar o console. É a
mesma disciplina do socket do gameprofiled, que deliberadamente não tem
verbo de leitura.

POR QUE NÃO NO gameprofiled, que já lê coisa do sistema: ele é root e
publica /run/kyber/state.json legível por todo mundo. É exatamente por
isso que ele publica appid e NUNCA o nome do jogo — resolver o nome
exigiria varrer /home, e caminho de diretório pessoal em arquivo público
é vazamento por descuido. A biblioteca é a mesma pergunta, com a mesma
resposta.

POR QUE NÃO NO NAVEGADOR, que também seria possível: para o launcher
parsear VDF em JS, a árvore da Steam teria que ser servida por HTTP. O
darkhttpd não faz containment — está escrito na unit dele — e junto dos
appmanifest iria o userdata/<id>/config/localconfig.vdf, que é dado de
conta. O parser fica do lado que já tem o direito de ler.

---------------------------------------------------------------------
TRÊS FONTES, E CADA UMA RESPONDE UMA PERGUNTA DIFERENTE.

  steamapps/appmanifest_*.acf     o que está INSTALADO, e quanto ocupa.
                                  VDF de texto, um arquivo por título.
  userdata/*/config/localconfig   quanto se JOGOU, e quando. Também VDF
                                  de texto; o .acf não tem esse dado.
  appcache/appinfo.vdf            o que a coisa É — jogo, ferramenta,
                                  DLC. VDF BINÁRIO, e é a única fonte
                                  local dessa resposta.

A terceira é a que impede a prateleira de mostrar "Steam Linux Runtime
2.0 (soldier)" como se fosse título jogável. Não existe campo no .acf
que diga isso: dos três títulos instalados no console, DOIS são runtime,
e nada nas 27 chaves do .acf os separa do terceiro.
"""

VERSION = "0.1.0"
