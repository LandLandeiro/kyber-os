#!/usr/bin/bash
#
# KYBER — levantamento do lançamento de jogo, para a Etapa 7a.
#
# SÓ LEITURA nas seções 1 a 7. A seção 8 é a única que AGE, está marcada,
# e não roda sozinha: é preciso passar `--lancar` para ela acontecer.
#
#     ./tools/levantar-lancamento.sh              só lê
#     ./tools/levantar-lancamento.sh --lancar     lê e faz UM teste de
#                                                 lançamento, observando
#
# Roda por SSH. O ambiente gráfico é lido DO PROCESSO DO LAUNCHER e não
# do shell: o gamescope-session-plus exporta DISPLAY dentro do próprio
# script da sessão (linha 294) e o wrapper faz
# `systemctl --user unset-environment DISPLAY` antes de subir — então
# nem o shell do SSH nem o systemd --user conhecem esse DISPLAY. Descobrir
# de onde ele se alcança é metade da pergunta desta etapa.
#
set -uo pipefail

echo "════════ 1. A SESSÃO, E DE ONDE VEM O AMBIENTE ════════"
CHROMIUM=$(pgrep -f 'chromium.*--kiosk' | head -1)
echo "pid do launcher (chromium --kiosk): ${CHROMIUM:-NENHUM}"
if [[ -n ${CHROMIUM} ]]; then
    echo "ambiente do launcher, o que interessa:"
    tr '\0' '\n' < "/proc/${CHROMIUM}/environ" 2>/dev/null |
        grep -E '^(DISPLAY|WAYLAND_DISPLAY|GAMESCOPE_WAYLAND_DISPLAY|XDG_RUNTIME_DIR|XDG_SESSION_TYPE|XAUTHORITY|STEAM|SRT_URLOPEN)' |
        sed 's/^/  /'
    echo "cgroup do launcher (diz sob que unit a sessão roda):"
    cat "/proc/${CHROMIUM}/cgroup" 2>/dev/null | sed 's/^/  /'
else
    echo "  (o launcher não está rodando — a sessão KYBER está no ar?)"
fi
echo "ambiente do systemd --user, para comparar:"
systemctl --user show-environment 2>/dev/null |
    grep -E '^(DISPLAY|WAYLAND_DISPLAY|GAMESCOPE|XDG_RUNTIME_DIR)' | sed 's/^/  /' ||
    echo "  (nenhuma dessas variáveis — que é o esperado, e é o problema)"

echo
echo "════════ 2. GAMESCOPE: COMO ELE FOI CHAMADO ════════"
GS=$(pgrep -x gamescope | head -1)
echo "pid: ${GS:-NENHUM}"
[[ -n ${GS} ]] && tr '\0' ' ' < "/proc/${GS}/cmdline" | fold -w 100 | sed 's/^/  /'
echo
if [[ -n ${GS} ]]; then
    echo -n "tem --steam na linha? "
    tr '\0' '\n' < "/proc/${GS}/cmdline" | grep -qx -- '--steam' && echo SIM || echo "nao (e' assim que o KYBER foi montado)"
fi
command -v gamescope > /dev/null && gamescope --help 2>&1 | grep -i -m3 'steam' | sed 's/^/  /'

echo
echo "════════ 3. A STEAM: ESTÁ RODANDO? ESTÁ LOGADA? ════════"
echo "processos:"
pgrep -a -f 'steam' 2>/dev/null | grep -v levantar | head -10 | sed 's/^/  /' ||
    echo "  NENHUM processo da Steam"
L="${HOME}/.local/share/Steam/config/loginusers.vdf"
echo "loginusers.vdf: $([[ -f $L ]] && echo existe || echo AUSENTE)"
[[ -f $L ]] && grep -E '"(AccountName|PersonaName|MostRecent|RememberPassword|WantsOfflineMode)"' "$L" | sed 's/^/  /'
echo "registry.vdf, AutoLoginUser:"
grep -o '"AutoLoginUser"[[:space:]]*"[^"]*"' "${HOME}/.steam/registry.vdf" 2>/dev/null | sed 's/^/  /' ||
    echo "  (não achei)"

echo
echo "════════ 4. AS JANELAS QUE O COMPOSITOR VÊ ════════"
if [[ -n ${CHROMIUM} ]]; then
    D=$(tr '\0' '\n' < "/proc/${CHROMIUM}/environ" | grep '^DISPLAY=' | cut -d= -f2-)
    XA=$(tr '\0' '\n' < "/proc/${CHROMIUM}/environ" | grep '^XAUTHORITY=' | cut -d= -f2-)
    echo "usando DISPLAY=${D:-?} XAUTHORITY=${XA:-<nenhum>}"
    if command -v xwininfo > /dev/null; then
        DISPLAY="$D" ${XA:+XAUTHORITY="$XA"} xwininfo -root -children 2>&1 | head -20 | sed 's/^/  /'
    else
        echo "  xwininfo não instalado (pacote xorg-x11-utils)"
    fi
    if command -v xprop > /dev/null; then
        echo "propriedades STEAM_* na raiz:"
        DISPLAY="$D" ${XA:+XAUTHORITY="$XA"} xprop -root 2>/dev/null |
            grep -iE 'STEAM|GAMESCOPE' | head -12 | sed 's/^/  /'
    else
        echo "  xprop não instalado"
    fi
else
    echo "  (sem launcher, sem DISPLAY para consultar)"
fi

echo
echo "════════ 5. COMO O SISTEMA ABRE steam:// ════════"
command -v xdg-open steam steamos-session-select 2>/dev/null | sed 's/^/  /'
echo "handler registrado:"
xdg-mime query default x-scheme-handler/steam 2>/dev/null | sed 's/^/  /' || echo "  (nenhum)"
echo "arquivos .desktop da Steam:"
ls /usr/share/applications/steam*.desktop ~/.local/share/applications/steam*.desktop 2>/dev/null | sed 's/^/  /'
echo "política do Chromium (o que evitaria o diálogo de protocolo externo):"
ls -l /etc/chromium/policies/managed/ 2>/dev/null | sed 's/^/  /' || echo "  diretório não existe"

echo
echo "════════ 6. O QUE O DAEMON ESTÁ VENDO AGORA ════════"
curl -s --max-time 3 http://127.0.0.1:8787/state.json 2>/dev/null |
    python3 -c 'import sys,json;d=json.load(sys.stdin);print("  runningGame:",d.get("runningGame"));print("  at:",d.get("at"))' 2>/dev/null ||
    echo "  (state.json não respondeu)"
echo "biblioteca:"
curl -s --max-time 3 http://127.0.0.1:8790/library.json 2>/dev/null |
    python3 -c 'import sys,json;d=json.load(sys.stdin);[print("  ",g["appid"],g["name"]) for g in d.get("games",[])]' 2>/dev/null ||
    echo "  (kyber-library não respondeu — está no ar?)"

echo
echo "════════ 7. AS PEÇAS DA SESSÃO ════════"
systemctl --user --no-pager --plain list-units 'kyber-*' 2>/dev/null | sed 's/^/  /'

if [[ ${1:-} != "--lancar" ]]; then
    echo
    echo "════════ 8. TESTE DE LANÇAMENTO — NÃO RODOU ════════"
    echo "  Repita com --lancar para fazer UM lançamento e observar o que"
    echo "  aparece na tela. É a única parte que age."
    exit 0
fi

echo
echo "════════ 8. TESTE DE LANÇAMENTO (esta parte AGE) ════════"
APPID=$(curl -s --max-time 3 http://127.0.0.1:8790/library.json 2>/dev/null |
        python3 -c 'import sys,json;g=json.load(sys.stdin).get("games") or [];print(g[0]["appid"] if g else "")' 2>/dev/null)
if [[ -z ${APPID} ]]; then
    echo "  não consegui descobrir um appid pela biblioteca; abortando"
    exit 1
fi
echo "appid alvo: ${APPID}"
echo "ANTES  — processos steam: $(pgrep -c -f steam 2>/dev/null || echo 0)"

D=$(tr '\0' '\n' < "/proc/${CHROMIUM}/environ" | grep '^DISPLAY=' | cut -d= -f2-)
W=$(tr '\0' '\n' < "/proc/${CHROMIUM}/environ" | grep '^WAYLAND_DISPLAY=' | cut -d= -f2-)
echo "lançando com DISPLAY=${D} WAYLAND_DISPLAY=${W}"
echo "OLHE A TELA DO CONSOLE e anote o que aparece, em ordem."
env DISPLAY="$D" WAYLAND_DISPLAY="$W" \
    setsid steam "steam://rungameid/${APPID}" > /tmp/kyber-lancamento.log 2>&1 &

for i in 3 6 10 15 20 30; do
    sleep 5
    echo "── ${i}s"
    echo "   processos steam: $(pgrep -c -f steam 2>/dev/null || echo 0)"
    curl -s --max-time 3 http://127.0.0.1:8787/state.json 2>/dev/null |
        python3 -c 'import sys,json;print("   runningGame:",json.load(sys.stdin).get("runningGame"))' 2>/dev/null
    if command -v xwininfo > /dev/null && [[ -n ${D} ]]; then
        echo "   janelas: $(DISPLAY="$D" xwininfo -root -children 2>/dev/null | grep -c '0x')"
    fi
done
echo
echo "log do comando:"; tail -20 /tmp/kyber-lancamento.log 2>/dev/null | sed 's/^/  /'
