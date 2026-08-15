/* =====================================================================
   KYBER — bootstrap

   Ordem: instala o adapter → semeia o estado da máquina → liga o chrome
   → monta a tela raiz → só então liga a entrada. Ligar o input antes de
   haver algo focável faria a primeira seta cair no vazio.
   ===================================================================== */

import './core/chrome.js';               /* liga o chrome ao state */
import { state } from './core/state.js';
import { FocusManager } from './core/focus.js';
import { InputManager } from './core/input.js';
import { Router } from './core/router.js';
import { toast, toastAction } from './core/toast.js';
import { familiaDe, NOME_FAMILIA } from './core/glyphs.js';
import { calibrar } from './core/calibrate.js';
import { useAdapter, DataAdapter } from './data/adapter.js';
import { MockAdapter } from './data/mock.js';
import { createLibrary } from './screens/library.js';
import { createRunning } from './screens/running.js';
import { createPower } from './screens/power.js';
import { createSettings } from './screens/settings.js';
import { createIndexView } from './screens/index-view.js';
import { createSplash } from './screens/splash.js';
import { createWelcome } from './screens/welcome.js';
import { createSteamLogin } from './screens/steam-login.js';
import { createPairing } from './screens/pairing.js';

useAdapter(MockAdapter);

/* Estado da máquina. Hoje vem do mock; na Etapa 7 vem do gameprofiled
   sem que nenhuma tela perceba a troca. */
const machine = await DataAdapter.getState();
state.set('cpuTemp', machine.cpuTemp);
state.set('gpuTemp', machine.gpuTemp);
/* Controle é hardware: quem responde é a Gamepad API, não o mock. Começa
   em zero e o rodapé abre com as teclas do teclado até um controle
   aparecer — que é a verdade num Mac sem controle pareado. */
state.set('controllers', 0);
/* Medição antes da sessão: a régua nunca resolve com estado pela metade. */
state.set('intensity', machine.intensity);
state.set('watts', machine.watts);
state.set('runningGame', machine.runningGame);

const mountPoint = document.getElementById('screen');
const focus = new FocusManager(mountPoint);
const input = new InputManager();
/* ---------------------------------------------------------------------
   Primeira execução.

   Roda uma vez na vida do console, o que a torna impossível de exercitar
   durante o desenvolvimento sem um gatilho explícito. Por padrão o
   launcher abre direto na biblioteca — comportamento de máquina já
   configurada — e o fluxo se alcança por:

     kyber.primeiraExecucao()     do console, a qualquer momento
     ?first-run                   na URL, no carregamento

   `firstRunComplete` vive em memória e some no reload, por decisão: não
   há persistência no protótipo, e recarregar sempre devolve o launcher
   ao estado configurado.

   16a é pulada quando já existe controle conectado — o passo que ela
   pede já está cumprido.
   --------------------------------------------------------------------- */
const PASSOS = [createSplash, createWelcome, createSteamLogin, createPairing];

let passo = -1;

const firstRun = {
  async comecar() {
    state.set('firstRunComplete', false);
    passo = -1;
    await firstRun.avancar();
  },

  async avancar() {
    passo += 1;
    while (passo < PASSOS.length && pular(PASSOS[passo])) passo += 1;
    if (passo >= PASSOS.length) return firstRun.concluir();
    await router.reset(PASSOS[passo]);
  },

  async voltar() {
    passo -= 1;
    while (passo >= 0 && pular(PASSOS[passo])) passo -= 1;
    if (passo < 0) { passo = 0; }
    await router.reset(PASSOS[passo]);
  },

  async concluir() {
    state.set('firstRunComplete', true);
    state.set('bootStep', null);
    passo = -1;
    await router.reset(homeScreen());
  },
};

/* O pareamento não tem o que pedir quando já há controle na mão. */
const pular = (fabrica) => fabrica === createPairing && (state.get('controllers') ?? 0) > 0;

const router = new Router({
  mountPoint,
  overlayPoint: document.getElementById('app'),   /* overlay cobre o chrome */
  focus,
  /* A tela 16b mostra o que a Gamepad API expõe, não um controle
     fictício — para isso ela precisa da camada de entrada. */
  context: { input, firstRun },
});

window.addEventListener('kyber:move', (e) => {
  /* A tela tem a primeira palavra também no movimento: é como a barra de
     degraus fica com ← → enquanto está focada, sem que o foco escorregue
     para o controle vizinho a cada passo de volume. */
  if (router.current?.onMove?.(e.detail.dir) === true) return;
  focus.move(e.detail.dir);
});

/* A raiz do launcher depende da máquina, não da navegação: com sessão em
   curso o lugar de casa é a tela 17. */
const homeScreen = () => {
  if (state.get('runningGame')) return createRunning;
  return state.get('defaultView') === 'index' ? createIndexView : createLibrary;
};

const goHome = () => router.reset(homeScreen());

window.addEventListener('kyber:action', (e) => {
  const { action } = e.detail;

  /* O Guide tem dois papéis e os dois são globais.

     Toque: dentro do launcher abre CONFIGURAÇÕES — é o que o rodapé
     grava como `≡ SISTEMA`. Só volta para casa a partir do estado em que
     o jogo assumiu a tela, que é quando "voltar ao launcher" quer dizer
     alguma coisa. */
  if (action === 'guide') {
    if (router.current?.handsOff) goHome();
    else if (!router.current?.settings) router.push(createSettings);
    return;
  }
  if (action === 'guide-hold') {
    if (!router.current?.power) router.push(createPower);
    return;
  }

  /* Toast com ação declarada fica com o RB enquanto está visível, e
     está ESCRITO dentro dele que fica. Ⓐ e Ⓨ nunca passam por aqui:
     são da tela, com toast na tela ou sem. */
  if (toastAction(action)) return;

  /* A tela tem a primeira palavra e pode consumir o botão devolvendo
     true — é como o teclado virtual fica com o Ⓑ para APAGAR sem que a
     pilha desempilhe debaixo dele. */
  if (router.current?.onAction?.(action) === true) return;

  /* Ⓑ desempilha. Na raiz não há o que desempilhar e o botão morre. */
  if (action === 'b') router.pop();
});

/* Começar e encerrar sessão trocam a raiz do launcher. As telas avisam
   que aconteceu; quem decide para onde ir é aqui. */
window.addEventListener('kyber:game-closed', () => goHome());

/* ---------------------------------------------------------------------
   Controles conectando e desconectando.

   O toast é o canal certo: informa sem prender o foco e sem tirar
   ninguém do lugar. Mapping fora do padrão vira aviso em âmbar porque
   os índices de botão deixam de ser confiáveis — melhor dizer que não
   se sabe do que agir como se soubesse.
   --------------------------------------------------------------------- */
window.addEventListener('kyber:pad', (e) => {
  const { connected, id, count, standard, restored } = e.detail;
  state.set('controllers', count);

  /* A família decide o desenho de toda gravação de botão do sistema.
     Sem controle, volta ao padrão para o rodapé não guardar o desenho
     de um aparelho que saiu. */
  state.set('padFamily', count > 0 ? familiaDe(input.activePad?.id ?? id) : 'xbox');

  const nome = String(id ?? '').replace(/\s*\([^)]*\)\s*$/, '').trim() || 'controle genérico';

  if (connected && !standard) {
    toast({
      kind: 'error',
      title: `CONTROLE ${count} · LAYOUT DESCONHECIDO`,
      body: `${nome} · o navegador não reconheceu o mapeamento padrão; os botões podem sair trocados`,
    });
    return;
  }

  toast({
    kind: 'device',
    title: connected
      ? `CONTROLE ${count} ${restored ? 'RECONHECIDO' : 'CONECTADO'}`
      : 'CONTROLE DESCONECTADO',
    body: connected
      ? `${nome} · ${NOME_FAMILIA[familiaDe(id)]}`
      : count > 0
        ? `${nome} · ${count} ainda conectado${count > 1 ? 's' : ''}`
        : `${nome} · navegação de volta ao teclado`,
  });
});

input.start();

/* A entrada sobe antes da primeira tela para que a 16a já saiba se há
   controle e possa ser pulada, e para o splash aceitar Ⓐ desde o início. */
if (new URLSearchParams(location.search).has('first-run')) {
  await firstRun.comecar();
} else {
  state.set('firstRunComplete', true);
  await router.push(homeScreen());
}

/* Superfície de inspeção pelo console — mesma porta usada nos critérios
   de conclusão das entregas anteriores. */
globalThis.kyber = Object.assign(globalThis.kyber || {}, {
  state, focus, router, input, data: DataAdapter, toast,
  /* Gatilho do fluxo de primeira execução. Ver PASSOS, acima. */
  primeiraExecucao: () => firstRun.comecar(),
  /* Instrumento de aferição do controle. Ver src/core/calibrate.js. */
  calibrar: (ligado) => calibrar(input, ligado),
});
