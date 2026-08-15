/* =====================================================================
   KYBER — tela 03 · Overlay de lançamento

   Overlay, não tela: monta por cima do chrome e a tela de baixo continua
   ali, atrás do scrim. É o scrim que garante o contraste — o painel de
   vidro só flutua sobre ele. Sem scrim o vidro não passaria em nada.

   A fila mostra o que o `gameprofiled` está fazendo, um passo a cada
   620ms. O ritmo vem do adapter, não daqui: quem demora é o daemon. A
   interface só marca APLICADO / EXECUTANDO / AGUARDA.

   Ⓑ cancela a qualquer momento. O `popTrap` devolve o foco ao botão
   JOGAR de onde se saiu — o overlay não precisa saber disso.
   ===================================================================== */

import { state } from '../core/state.js';
import { glifo, glifoHTML } from '../core/glyphs.js';
import { DataAdapter } from '../data/adapter.js';
import { createLoader } from '../components/loader.js';

const MARKS = { done: 'APLICADO', running: 'EXECUTANDO', waiting: 'AGUARDA' };

export async function createLaunch({ router }, appid) {
  const game = await DataAdapter.getGame(appid);
  const plan = await DataAdapter.launchPlan(appid);
  const est = DataAdapter.estimateProfile(game.profile);

  const control = new AbortController();
  let current = -1;
  let finished = false;

  const el = template(game, plan, est);
  /* Transição curta até o jogo assumir a tela: subida. */
  el.querySelector('[data-launch="loader"]').append(createLoader('subida', 24));

  const dom = {
    head:    el.querySelector('[data-launch="head"]'),
    rows:    [...el.querySelectorAll('[data-step]')],
    bar:     el.querySelector('[data-launch="bar"]'),
    cancel:  el.querySelector('[data-launch="cancel"]'),
    outcome: el.querySelector('[data-launch="outcome"]'),
  };

  paint();
  run();

  /* `handsOff` vira true quando o jogo assume a tela: a partir daí o
     toque no Guide significa "volta ao launcher", não "abre sistema". */
  const screen = { el, overlay: true, onAction, unmount, handsOff: false };
  return screen;

  /* ---------- a fila ---------- */

  async function run() {
    try {
      await DataAdapter.launch(appid, {
        signal: control.signal,
        onStep: (i) => { current = i; paint(); },
      });
      finished = true;
      current = plan.length;
      await complete();
      screen.handsOff = true;
    } catch (error) {
      if (error.name === 'AbortError') return;   /* o router já desmonta */
      /* A tela de erro de lançamento é uma das quatro que o mapa prevê e
         ninguém desenhou. Falhar em silêncio seria pior: o overlay diz o
         que quebrou e o que falta. */
      finished = true;
      dom.head.textContent = 'GAMEPROFILED · FALHOU';
      dom.cancel.innerHTML = `${glifoHTML('B')} · FECHAR`;
      dom.outcome.hidden = false;
      dom.outcome.dataset.error = 'true';
      dom.outcome.textContent =
        `${error.message} · TELA DE ERRO DE LANÇAMENTO NÃO IMPLEMENTADA`;
    }
  }

  async function complete() {
    /* O adapter é quem sabe que a sessão começou; a interface relê o
       estado dele em vez de inventar o próprio. */
    const machine = await DataAdapter.getState();
    state.set('intensity', machine.intensity);
    state.set('watts', machine.watts);
    state.set('runningGame', machine.runningGame);

    /* A tela 17 consome isto. */
    window.dispatchEvent(new CustomEvent('kyber:game-launched', { detail: { appid } }));

    paint();
    dom.head.textContent = 'GAMEPROFILED · PERFIL APLICADO';
    dom.cancel.innerHTML = `${glifoHTML('B')} · FECHAR`;
    dom.outcome.hidden = false;
    /* No console o jogo toma a tela e o launcher sai de cena. Aqui não
       há jogo para tomar nada, então o overlay diz o que aconteceu e
       aponta o caminho de volta — que é o mesmo do console real. */
    dom.outcome.textContent =
      `${game.name.toUpperCase()} ASSUMIU A TELA · ${glifo('GUIDE')} VOLTA AO LAUNCHER`;
  }

  function paint() {
    dom.rows.forEach((row, i) => {
      const status = i < current ? 'done' : i === current ? 'running' : 'waiting';
      row.dataset.status = status;
      row.querySelector('[data-mark]').textContent = MARKS[status];
    });
    const done = Math.max(0, Math.min(current, plan.length));
    dom.bar.style.width = `${(done / plan.length) * 100}%`;
  }

  /* ---------- ações ---------- */

  function onAction(action) {
    /* Ⓐ sobre o botão faz o mesmo que Ⓑ: é o único alvo do trap. */
    if (action === 'a') close();
  }

  function close() {
    router.pop();
  }

  function unmount() {
    /* Desmontar sem ter terminado é cancelamento — inclusive quando vem
       do Ⓑ tratado no main, que não passa por onAction. */
    if (!finished) control.abort();
  }
}

function template(game, plan, est) {
  const root = document.createElement('div');
  root.className = 'launch glass-scrim';

  const rows = plan
    .map(
      (step, i) => `
      <div class="queue__row" data-step="${i}" data-status="waiting">
        <div class="queue__name">${escape(step.name)}</div>
        <div class="queue__right">
          <div class="queue__value">${escape(step.value)}</div>
          <div class="queue__mark" data-mark>${MARKS.waiting}</div>
        </div>
      </div>`
    )
    .join('');

  root.innerHTML = `
    <div class="launch__panel glass-overlay">
      <div class="launch__head">
        <div class="launch__label" data-launch="head">
          <span data-launch="loader"></span>GAMEPROFILED · APLICANDO PERFIL</div>
        <div class="launch__level">
          <span class="steps">${[1, 2, 3]
            .map((n) => `<span class="step${n <= LEVEL_STEPS[est.level] ? ' step--on' : ''}"></span>`)
            .join('')}</span>
          <span class="launch__level-name">${LEVEL_NAME[est.level]}</span>
        </div>
      </div>

      <div class="launch__title">${escape(game.name)}</div>

      <div class="queue">${rows}</div>

      <div class="launch__track"><div class="launch__bar" data-launch="bar"></div></div>

      <div class="launch__foot">
        <div class="launch__uri">steam://rungameid/${game.appid}</div>
        <div class="launch__cancel focusable" tabindex="0" role="button"
             data-launch="cancel" data-focus-initial>${glifoHTML('B')} · CANCELAR</div>
      </div>

      <div class="launch__outcome" data-launch="outcome" hidden></div>
    </div>`;
  return root;
}

const LEVEL_NAME = { quiet: 'SILENCIOSO', nominal: 'EQUILIBRADO', hot: 'AGRESSIVO' };
const LEVEL_STEPS = { quiet: 1, nominal: 2, hot: 3 };

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
