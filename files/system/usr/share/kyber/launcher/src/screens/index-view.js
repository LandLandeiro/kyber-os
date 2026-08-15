/* =====================================================================
   KYBER — tela 01b · Índice (Direção B)

   Lista densa: nº, título, gênero, horas, último acesso e perfil. É a
   mesma biblioteca da vitrine lida como tabela, para quem sabe o que
   procura. Ⓨ alterna as duas preservando o título selecionado.

   Foco por INVERSÃO DE LINHA, não por anel: é o sinal mais forte a três
   metros numa lista densa e o mais barato de renderizar.

   ARMADILHA DOCUMENTADA — dentro de linha invertível, cor fixa em filho
   sobrevive à inversão e desaparece no branco. Por isso todo texto da
   linha é `color: inherit` e toda diferença de peso é `opacity`. O
   mesmo vale para a barra de perfil, que pinta com `currentColor`.

   Nove linhas de 88px cabem nos 850px de conteúdo (58 de cabeçalho de
   coluna + 9 × 88 = 850, exato). As demais chegam pela rolagem dirigida
   pelo foco — nada rola por acidente.
   ===================================================================== */

import { state } from '../core/state.js';
import { DataAdapter } from '../data/adapter.js';
import { generatedCover } from './cover.js';
import { horas, ultimoAcessoCurto, NIVEL, DEGRAUS, createNotice, sortGames } from './format.js';
import { createDetail } from './detail.js';
import { createSearch } from './search.js';
import { createLibrary } from './library.js';

const HINTS = [
  { glyph: 'A', label: 'ABRIR' },
  { glyph: 'Y', label: 'VITRINE' },
  { glyph: 'X', label: 'BUSCAR' },
  { glyph: 'GUIDE', label: 'SISTEMA' },
];

export async function createIndexView({ router }) {
  const games = sortGames(await DataAdapter.listGames(), 'recentes');

  const contextLine = `ORDENADO POR ÚLTIMO ACESSO · ${games.length} TÍTULOS`;
  const notice = createNotice(contextLine);

  let selected = state.get('selectedGame') ?? games[0]?.appid ?? null;

  const el = template();
  const list = el.querySelector('[data-region="index"]');
  list.replaceChildren(...games.map(row));

  const initial =
    list.querySelector(`[data-appid="${selected}"]`) ?? list.firstElementChild;
  initial?.setAttribute('data-focus-initial', '');

  el.addEventListener('kyber:focus', (e) => {
    const node = e.target.closest('[data-appid]');
    if (node) select(Number(node.dataset.appid));
  });

  return { el, onEnter, onLeave, onAction, unmount };

  function onEnter() {
    state.set('screenName', 'ÍNDICE');
    state.set('hints', HINTS);
    notice.restore();
    applyPreview();
  }

  function onLeave() { notice.stop(); }
  function unmount() { notice.stop(); }

  function onAction(action) {
    if (action === 'a') {
      if (selected !== null) router.push(createDetail, selected);
      return;
    }
    if (action === 'y') {
      router.replace(createLibrary);
      return;
    }
    if (action === 'x') { router.push(createSearch); return; }
  }

  function select(appid) {
    if (appid === selected) return;
    selected = appid;
    state.set('selectedGame', appid);
    applyPreview();
  }

  function applyPreview() {
    const game = games.find((g) => g.appid === selected);
    if (!game) return;
    const est = DataAdapter.estimateProfile(game.profile);
    state.set('preview', { intensity: est.intensity, watts: est.watts });
  }

  function row(game, i) {
    const node = document.createElement('div');
    node.className = 'index__row row-invert';
    node.tabIndex = 0;
    node.setAttribute('role', 'button');
    node.setAttribute('aria-label', game.name);
    node.dataset.appid = game.appid;

    const est = DataAdapter.estimateProfile(game.profile);

    node.innerHTML = `
      <div class="index__id">
        <span class="index__thumb"></span>
        <span class="index__n">${String(i + 1).padStart(2, '0')}</span>
      </div>
      <div class="index__title">${escape(game.name)}</div>
      <div class="index__genre">${game.genre}</div>
      <div class="index__hours">${horas(game.hoursTotal)}</div>
      <div class="index__last">${ultimoAcessoCurto(game.lastPlayed)}</div>
      <div class="index__profile">
        <span class="index__level">${NIVEL[est.level]}</span>
        <span class="steps steps--inherit">${[1, 2, 3]
          .map((n) => `<span class="step${n <= DEGRAUS[est.level] ? ' step--on' : ''}"></span>`)
          .join('')}</span>
      </div>`;

    /* A miniatura é sempre a capa gerada: a 52px a arte da loja vira
       borrão, e o padrão do título continua legível. */
    node.querySelector('.index__thumb').append(generatedCover(game, 'tile'));
    return node;
  }
}

function template() {
  const section = document.createElement('section');
  section.className = 'index screen__page';
  section.innerHTML = `
    <div class="index__head">
      <div>Nº</div>
      <div>TÍTULO</div>
      <div>GÊNERO</div>
      <div class="index__right">HORAS</div>
      <div class="index__right">ÚLTIMO</div>
      <div class="index__right">PERFIL</div>
    </div>
    <div class="index__list" data-region="index" data-region-flow="vertical"
         data-region-dim="off"></div>`;
  return section;
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
