/* =====================================================================
   KYBER — tela 17b · Confirmação de fechar jogo

   Diálogo destrutivo. Duas regras mandam no desenho:

   1. O FOCO INICIAL É CANCELAR. Ação destrutiva não recebe foco de
      presente — quem vai destruir precisa se mover até o botão.
   2. FECHAR JOGO leva o fio de 4px em `state-hot` na aresta esquerda.
      É o terceiro uso de cor saturada que a identidade permite, um por
      tela, exatamente para isto.

   A tabela diz o que acontece em vez de perguntar "tem certeza?".
   ===================================================================== */

import { state } from '../core/state.js';
import { glifoHTML } from '../core/glyphs.js';
import { DataAdapter } from '../data/adapter.js';
import { relogio } from './running.js';

export async function createConfirmClose({ router }, appid) {
  const game = await DataAdapter.getGame(appid);
  const live = state.get('runningGame');
  const repouso = DataAdapter.estimateProfile(await DataAdapter.idleProfile());

  const el = template(game, live, repouso);
  const clockEl = el.querySelector('[data-confirm="clock"]');

  let timer = 0;

  return { el, overlay: true, onEnter, onLeave, onAction, unmount };

  function onEnter() {
    const paint = () => {
      const atual = state.get('runningGame');
      if (atual) clockEl.textContent = relogio(Date.now() - atual.startedAt);
    };
    paint();
    timer = setInterval(paint, 1000);
  }

  function onLeave() { clearInterval(timer); }
  function unmount() { clearInterval(timer); }

  function onAction(action) {
    if (action !== 'a') return;
    const acao = document.activeElement?.dataset?.action;
    if (acao === 'cancel') { router.pop(); return; }
    if (acao === 'confirm') close();
  }

  async function close() {
    await DataAdapter.closeGame();
    const machine = await DataAdapter.getState();
    state.set('runningGame', machine.runningGame);
    state.set('intensity', machine.intensity);
    state.set('watts', machine.watts);

    /* Quem decide para onde ir sem sessão é o main: o diálogo só avisa
       que a sessão acabou. */
    window.dispatchEvent(new CustomEvent('kyber:game-closed', { detail: { appid } }));
  }
}

function template(game, live, repouso) {
  const root = document.createElement('div');
  root.className = 'confirm glass-scrim';

  const linha = (label, value) => `
    <div class="consequence">
      <span class="consequence__label">${label}</span>
      <span class="consequence__value">${value}</span>
    </div>`;

  const sessao = live ? relogio(Date.now() - live.startedAt) : '00:00:00';

  root.innerHTML = `
    <div class="confirm__panel glass-overlay">
      <div class="confirm__kicker">CONFIRMAR</div>
      <h1 class="confirm__title">Fechar ${escape(game.name)}?</h1>
      <p class="confirm__desc">O progresso não salvo desde o último ponto será perdido.</p>

      <div class="consequences">
        ${linha('SESSÃO ENCERRADA', `<span data-confirm="clock">${sessao}</span>`)}
        ${linha('PERFIL REVERTIDO PARA', `${NIVEL[repouso.level]} · ${repouso.watts} W`)}
        ${linha('SAVE NA NUVEM', 'sincroniza ao fechar')}
      </div>

      <div class="confirm__actions" data-region="confirm" data-region-flow="horizontal"
           data-region-dim="off">
        <div class="btn btn--primary focusable" tabindex="0" role="button"
             data-action="cancel" data-focus-initial>CANCELAR</div>
        <div class="btn btn--destructive focusable" tabindex="0" role="button"
             data-action="confirm">FECHAR JOGO</div>
      </div>

      <div class="confirm__hint">${glifoHTML('A')} CONFIRMAR · ${glifoHTML('B')} VOLTAR</div>
    </div>`;
  return root;
}

/* Valor por extenso e em minúsculas: é nome técnico do perfil, não
   estado do sistema em caixa alta. */
const NIVEL = { quiet: 'silencioso', nominal: 'equilibrado', hot: 'agressivo' };

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
