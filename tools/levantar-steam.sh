#!/usr/bin/bash
#
# KYBER — levantamento da biblioteca Steam, para a Etapa 7a.
#
# SÓ LEITURA. Nada aqui cria, move, apaga ou escreve — nem em /tmp. Roda
# no console, como a pessoa dona da sessão, e a saída inteira é para ser
# lida por gente.
#
#     ./tools/levantar-steam.sh 2>&1 | tee /tmp/levantamento.txt
#
# POR QUE ISTO EXISTE EM VEZ DE UMA SUPOSIÇÃO. O formato dos arquivos da
# Steam é da Valve e não tem contrato publicado: o que se sabe dele vem
# de olhar arquivos de verdade. Três decisões da Etapa 7a dependem de
# fatos que só existem NESTA máquina, e errar qualquer uma custa uma
# reescrita:
#
#   · quais campos o appmanifest_*.acf realmente carrega (seção 4). O
#     mock inventa `catalog`, `genre` e `year`; nenhum é do .acf, e o que
#     é do .acf ninguém confirmou lendo;
#   · se o cache de arte da Steam está preenchido no console (seção 8).
#     Ele é preenchido pela UI da Steam sob demanda, então num console
#     que nunca abriu o Big Picture ele pode estar vazio — e a decisão de
#     servir a capa do disco em vez de buscar na CDN depende disso;
#   · o modo do $HOME (seção 10). Se ele for 0700, o darkhttpd, que roda
#     como nobody, não alcança arquivo nenhum da Steam, e a peça que lê a
#     biblioteca só pode viver dentro da sessão da pessoa.
#
# A seção 6 é a mais chata e a mais barata: caractere difícil em nome de
# jogo. BOM, barra invertida e \u2122 escapado quebram um parser pequeno
# de maneiras diferentes, e é melhor descobrir aqui do que na prateleira.
#
S="${HOME}/.local/share/Steam"

echo "════════ 1. A INSTALAÇÃO ════════"
ls -ld "$S" 2>&1
echo "steamapps:"; ls -ld "$S"/steamapps 2>&1
echo "userdata :"; ls -ld "$S"/userdata/* 2>&1 | head -3
echo "quem sou eu: $(id -nu) uid=$(id -u) grupos=$(id -Gn)"
echo "home: $(ls -ld "$HOME" | awk '{print $1, $3, $4}')"

echo
echo "════════ 2. BIBLIOTECAS ════════"
for f in "$S/config/libraryfolders.vdf" "$S/steamapps/libraryfolders.vdf"; do
    echo "── $f"
    [ -f "$f" ] && cat "$f" || echo "   (não existe)"
done

echo
echo "════════ 3. QUANTOS JOGOS, ONDE ════════"
find "$S/steamapps" -maxdepth 1 -name 'appmanifest_*.acf' 2>/dev/null | wc -l | xargs echo "acf na biblioteca principal:"
# outras bibliotecas, tiradas do próprio libraryfolders
grep -oE '"path"[[:space:]]*"[^"]+"' "$S/config/libraryfolders.vdf" 2>/dev/null |
    sed 's/.*"\(.*\)"$/\1/' | while read -r p; do
        echo "  biblioteca: $p"
        echo "    acf: $(find "$p/steamapps" -maxdepth 1 -name 'appmanifest_*.acf' 2>/dev/null | wc -l)"
        df -h "$p" 2>/dev/null | tail -1 | awk '{print "    disco:", $1, $2, "livre", $4}'
    done

echo
echo "════════ 4. TODAS AS CHAVES QUE EXISTEM NOS .acf ════════"
find "$S" -name 'appmanifest_*.acf' 2>/dev/null |
    xargs grep -hoE '^[[:space:]]*"[A-Za-z_]+"' 2>/dev/null |
    tr -d ' \t"' | sort | uniq -c | sort -rn

echo
echo "════════ 5. DOIS .acf INTEIROS ════════"
find "$S" -name 'appmanifest_*.acf' 2>/dev/null | sort | head -2 |
    while read -r f; do echo "── $f"; cat "$f"; echo; done

echo
echo "════════ 6. CARACTERES DIFÍCEIS NOS .acf ════════"
echo -n "com BOM        : "; find "$S" -name 'appmanifest_*.acf' -exec sh -c 'head -c3 "$1" | grep -q $'"'"'\xef\xbb\xbf'"'"' && echo "$1"' _ {} \; 2>/dev/null | wc -l
echo -n "com barra \\    : "; grep -l '\\' $(find "$S" -name 'appmanifest_*.acf' 2>/dev/null) 2>/dev/null | wc -l
echo -n "com // no meio : "; grep -l '//' $(find "$S" -name 'appmanifest_*.acf' 2>/dev/null) 2>/dev/null | wc -l
echo -n "nome nao-ASCII : "; grep -h '"name"' $(find "$S" -name 'appmanifest_*.acf' 2>/dev/null) 2>/dev/null | LC_ALL=C grep -c '[^ -~]'
echo "nomes instalados:"
grep -h '"name"' $(find "$S" -name 'appmanifest_*.acf' 2>/dev/null) 2>/dev/null | sed 's/^[[:space:]]*/  /'

echo
echo "════════ 7. TEMPO DE JOGO (localconfig) ════════"
for f in "$S"/userdata/*/config/localconfig.vdf; do
    echo "── $f  ($(ls -l "$f" | awk '{print $1}'))"
    grep -c 'LastPlayed' "$f" 2>/dev/null | xargs echo "   entradas com LastPlayed:"
done

echo
echo "════════ 8. CACHE DE ARTE EM DISCO ════════"
C="$S/appcache/librarycache"
echo "diretório: $(ls -ld "$C" 2>&1 | awk '{print $1, $3, $4}')  total $(du -sh "$C" 2>/dev/null | cut -f1)"
echo "appids no cache: $(ls "$C" 2>/dev/null | wc -l)"
for n in header.jpg library_600x900.jpg library_hero.jpg logo.png; do
    echo "  $n: $(find "$C" -name "$n" 2>/dev/null | wc -l)"
done
echo "formato antigo (arquivo solto na raiz): $(ls "$C"/*_library_600x900.jpg 2>/dev/null | wc -l)"
echo "grid customizado: $(ls "$S"/userdata/*/config/grid 2>/dev/null | wc -l) arquivos"

echo
echo "════════ 9. REDE, DA PERSPECTIVA DO CONSOLE ════════"
for u in "https://cdn.cloudflare.steamstatic.com/steam/apps/553850/library_600x900.jpg" \
         "https://cdn.cloudflare.steamstatic.com/steam/apps/553850/library_hero.jpg"; do
    printf "  %s\n    -> %s\n" "${u##*/}" "$(curl -sS -o /dev/null -m 10 -w 'HTTP %{http_code}  %{size_download} bytes  %{time_total}s' "$u" 2>&1)"
done

echo
echo "════════ 10. QUEM PODE LER O QUE (pergunta 5) ════════"
# Sem sudo: o que interessa e' a permissao de cada componente do caminho,
# e o namei mostra todas de uma vez. Se qualquer diretorio ate' aqui nao
# tiver o bit x para "outros", nobody nao chega no fim.
namei -l "$S/steamapps" 2>/dev/null || ls -ld "$HOME" "$S" "$S/steamapps"
