/* =====================================================================
   KYBER — tela 17 · Jogo em execução

   É o estado do launcher quando existe sessão: o hero da biblioteca dá
   lugar ao bloco EM EXECUÇÃO e a prateleira desce para o rodapé da tela,
   a 40% de opacidade — presente, secundária, ainda navegável.

   O painel de telemetria é OPACO (`surface-1`) mesmo estando sobre a
   capa. É a lei do vidro pelo avesso: só desenhamos vidro onde nós
   desenhamos o fundo, e capa de jogo não é fundo nosso.
   ===================================================================== */

import { state } from '../core/state.js';
import { DataAdapter } from '../data/adapter.js';
import { coverElement } from './cover.js';
import { createDetail } from './detail.js';
import { createConfirmClose } from './confirm-close.js';
import { horas, createNotice, sortGames } from './format.js';

const HINTS = [
  { glyph: 'A', label: 'RETOMAR' },
  { glyph: 'X', label: 'CAPTURA' },
  { glyph: 'GUIDE', label: 'SEGURAR · ENERGIA', key: 'SHIFT+TAB' },
];

/** Cronômetro de sessão no formato 01:12:44. */
export function relogio(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((n) => String(n).padStart(2, '0')).join(':');
}

export async function createRunning({ router }) {
  const live = state.get('runningGame');
  const game = await DataAdapter.getGame(live.appid);
  const machine = await DataAdapter.getState();
  const sessions = await DataAdapter.sessions(live.appid);
  const others = sortGames(
    (await DataAdapter.listGames()).filter((g) => g.appid !== live.appid),
    'recentes'
  );

  const settings = await DataAdapter.settings();
  const contextLine =
    `${settings.compositor.toUpperCase()} · ${settings.resolution} · ${settings.refresh}`;
  const notice = createNotice(contextLine);

  const el = template(game, machine, sessions, others);
  const clockEl = el.querySelector('[data-running="clock"]');
  const shelf = el.querySelector('[data-region="shelf"]');

  const art = el.querySelector('[data-running="art"]');
  const noart = el.querySelector('[data-running="noart"]');
  noart.hidden = true;
  art.append(
    coverElement(game, DataAdapter.coverUrl(game.appid, 'hero'), 'wide', () => {
      noart.hidden = false;
    })
  );

  let timer = 0;

  return { el, onEnter, onLeave, onAction, unmount };

  /* ---------- ciclo de vida ---------- */

  function onEnter() {
    state.set('screenName', 'JOGO EM EXECUÇÃO');
    state.set('hints', HINTS);
    notice.restore();
    tick();
  }

  function onLeave() {
    notice.stop();
    clearInterval(timer);
  }

  function unmount() {
    notice.stop();
    clearInterval(timer);
  }

  /* O cronômetro é a única coisa que se move sozinha nesta tela, e move
     porque o tempo está passando de verdade — não é animação. */
  function tick() {
    clearInterval(timer);
    const paint = () => {
      const atual = state.get('runningGame');
      if (!atual) return;
      clockEl.textContent = relogio(Date.now() - atual.startedAt);
    };
    paint();
    timer = setInterval(paint, 1000);
  }

  /* ---------- ações ---------- */

  function onAction(action) {
    if (action === 'x') { notice('CAPTURA DE TELA · NÃO IMPLEMENTADA'); return; }
    if (action !== 'a') return;

    const alvo = document.activeElement;
    const acao = alvo?.dataset?.action;

    if (acao === 'resume') { notice('RETOMAR · O JOGO ASSUMIRIA A TELA'); return; }
    if (acao === 'close')  { router.push(createConfirmClose, game.appid); return; }

    const card = alvo?.closest?.('[data-appid]');
    if (card) router.push(createDetail, Number(card.dataset.appid));
  }
}

function template(game, machine, sessions, others) {
  const section = document.createElement('section');
  section.className = 'running screen__page';

  const cell = (label, value) => `
    <div class="telemetry__cell">
      <div class="telemetry__label">${label}</div>
      <div class="telemetry__value">${value}</div>
    </div>`;

  const linha = (s) => `
    <div class="sessions__row${s.muted ? ' sessions__row--muted' : ''}">
      <span class="sessions__label">${s.label}</span>
      <span class="sessions__value">${s.value}</span>
    </div>`;

  section.innerHTML = `
    <div class="running__head">
      <div class="running__text">
        <div class="running__badge">
          <span class="running__dot"></span>
          <span class="running__state">EM EXECUÇÃO</span>
          <span class="running__meta">· ${game.catalog} · ${game.genre}</span>
        </div>

        <h1 class="running__title">${escape(game.name)}</h1>

        <div class="running__counters">
          <div>
            <div class="running__label">SESSÃO ATUAL</div>
            <div class="running__clock" data-running="clock">00:00:00</div>
          </div>
          <span class="running__rule"></span>
          <div>
            <div class="running__label">TOTAL</div>
            <div class="running__total">${horas(game.hoursTotal)}</div>
          </div>
        </div>
      </div>

      <div class="running__panel">
        <div class="running__art" data-running="art"></div>
        <div class="running__scrim"></div>
        <div class="corner corner--tl"></div>
        <div class="running__noart" data-running="noart" hidden>SEM ARTE · CAPA GERADA</div>

        <div class="telemetry">
          ${cell('QUADROS', machine.fps ?? '—')}
          ${cell('GOVERNOR', game.profile.governor)}
          ${cell('GPU', game.profile.gpuLevel)}
          ${cell('PRIORIDADE', game.profile.priority)}
        </div>
      </div>
    </div>

    <div class="running__body">
      <div class="running__side" data-region="actions" data-region-flow="horizontal"
           data-region-dim="off" data-region-right="shelf">
        <div class="running__actions">
          <div class="btn btn--primary focusable" tabindex="0" role="button"
               data-action="resume" data-focus-initial>VOLTAR AO JOGO</div>
          <div class="btn focusable" tabindex="0" role="button"
               data-action="close">FECHAR JOGO</div>
        </div>

        <p class="running__warn">Fechar encerra a partida e reverte o perfil de performance. Progresso não salvo é perdido.</p>

        <div class="sessions">
          <div class="sessions__head">
            <span>SESSÕES RECENTES</span>
            <span>SAVE NA NUVEM · OK</span>
          </div>
          ${sessions.map(linha).join('')}
        </div>
      </div>

      <div class="running__library">
        <div class="running__library-head">
          <span>BIBLIOTECA · DISPONÍVEL</span>
          <span>${others.length} TÍTULOS</span>
        </div>
        <div class="mini-shelf" data-region="shelf" data-region-flow="horizontal"
             data-region-left="actions"></div>
      </div>
    </div>`;

  const shelf = section.querySelector('[data-region="shelf"]');
  shelf.append(...others.map(miniCard));
  return section;
}

function miniCard(game) {
  const node = document.createElement('div');
  node.className = 'mini focusable focusable--cover';
  node.tabIndex = 0;
  node.setAttribute('role', 'button');
  node.setAttribute('aria-label', game.name);
  node.dataset.appid = game.appid;

  const art = document.createElement('div');
  art.className = 'mini__art';
  art.append(coverElement(game, DataAdapter.coverUrl(game.appid, 'cover'), 'tile'));

  const name = document.createElement('div');
  name.className = 'mini__name';
  name.textContent = game.name;

  node.append(art, name);
  return node;
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
