/* =====================================================================
   KYBER — tela 01 · Biblioteca (vitrine, Direção A)

   Bloco hero do título selecionado + prateleira horizontal de capas.
   Seis capas visíveis por fileira, com o começo da sétima aparecendo à
   direita: é o que diz que a lista continua, sem barra de rolagem.

   O hero segue o FOCO, não um clique. `focus.js` dispara `kyber:focus`
   ao mover o foco; a tela escuta e repinta. Não há nenhum caminho que
   dependa de ponteiro.

   A seleção vive em `state.selectedGame` porque atravessa telas: o
   índice (01b) abre no mesmo título e a ficha (02) mostra esse título.
   ===================================================================== */

import { state } from '../core/state.js';
import { DataAdapter } from '../data/adapter.js';
import { coverElement } from './cover.js';
import { createDetail } from './detail.js';
import { createSearch } from './search.js';
import { createIndexView } from './index-view.js';
import { gb, ultimoAcesso, createNotice, sortGames } from './format.js';

const SORTS = [
  { key: 'recentes', label: 'RECENTES' },
  { key: 'nome',     label: 'NOME' },
  { key: 'tamanho',  label: 'TAMANHO' },
];

const HINTS = [
  { glyph: 'A', label: 'ABRIR' },
  { glyph: 'Y', label: 'ÍNDICE' },
  { glyph: 'X', label: 'BUSCAR' },
  { glyph: 'GUIDE', label: 'SISTEMA' },
];

/* Telas que a interface promete e ainda não existem. Cada uma anuncia o
   que falta em vez de fingir que funciona. */
export async function createLibrary({ router, focus }) {
  const games = await DataAdapter.listGames();
  const settings = await DataAdapter.settings();

  const contextLine =
    `${settings.compositor.toUpperCase()} · ${settings.resolution} · ${settings.refresh}`;
  const notice = createNotice(contextLine);

  const el = template();
  const dom = {
    heroMeta:  el.querySelector('[data-hero="meta"]'),
    heroTitle: el.querySelector('[data-hero="title"]'),
    heroChips: el.querySelector('[data-hero="chips"]'),
    heroSub:   el.querySelector('[data-hero="sub"]'),
    heroArt:   el.querySelector('[data-hero="art"]'),
    heroNoArt: el.querySelector('[data-hero="noart"]'),
    count:     el.querySelector('[data-shelf="count"]'),
    sort:      el.querySelector('[data-shelf="sort"]'),
    shelf:     el.querySelector('[data-region="shelf"]'),
  };

  let selected = state.get('selectedGame') ?? null;

  dom.count.textContent = `TODOS OS TÍTULOS · ${games.length}`;
  renderShelf();

  el.addEventListener('kyber:focus', (e) => {
    const card = e.target.closest('[data-appid]');
    if (card) selectGame(Number(card.dataset.appid));
  });

  return { el, onEnter, onLeave, onAction, unmount };

  /* ---------- ciclo de vida ---------- */

  function onEnter() {
    state.set('screenName', 'BIBLIOTECA');
    state.set('hints', HINTS);
    notice.restore();
    applyPreview();
  }

  function onLeave() {
    notice.stop();
  }

  function unmount() {
    notice.stop();
  }

  /* ---------- ações ---------- */

  function onAction(action) {
    if (action === 'a') {
      if (selected !== null) router.push(createDetail, selected);
      return;
    }
    if (action === 'y') {
      router.replace(createIndexView);
      return;
    }
    if (action === 'lb' || action === 'rb') {
      const step = action === 'rb' ? 1 : SORTS.length - 1;
      state.set('librarySort', (sortIndex() + step) % SORTS.length);
      renderShelf();
      return;
    }
    if (action === 'x') { router.push(createSearch); return; }
    /* Ⓑ na biblioteca não faz nada: é a raiz da pilha, não há o que
       desempilhar. Silêncio é a resposta correta, não um aviso. */
  }

  /* ---------- prateleira ---------- */

  /* Declaração de função, não const: `renderShelf` roda na construção,
     antes desta linha, e uma arrow em const estaria na zona morta. */
  function sortIndex() { return state.get('librarySort') ?? 0; }

  function renderShelf() {
    dom.sort.textContent = `LB / RB ORDENAR: ${SORTS[sortIndex()].label}`;

    const ordered = sortGames(games, SORTS[sortIndex()].key);
    dom.shelf.replaceChildren(...ordered.map(card));

    const target =
      dom.shelf.querySelector(`[data-appid="${selected}"]`) ?? dom.shelf.firstElementChild;
    if (!target) return;

    target.setAttribute('data-focus-initial', '');
    /* Antes de montar, marcar o alvo basta — o trap do router foca por
       ele. Depois de montado, reordenar troca os nós e o foco precisa
       ser recolocado à mão. */
    if (el.isConnected) focus.focus(target);
    else selectGame(Number(target.dataset.appid));
  }

  function card(game) {
    const node = document.createElement('div');
    node.className = 'card focusable focusable--cover';
    node.tabIndex = 0;
    node.setAttribute('role', 'button');
    node.setAttribute('aria-label', game.name);
    node.dataset.appid = game.appid;

    const art = document.createElement('div');
    art.className = 'card__art';
    art.append(coverElement(game, DataAdapter.coverUrl(game.appid, 'cover')));

    const name = document.createElement('div');
    name.className = 'card__name';
    name.textContent = game.name;

    node.append(art, name);
    return node;
  }

  /* ---------- hero ---------- */

  function selectGame(appid) {
    if (appid === selected) return;
    selected = appid;
    state.set('selectedGame', appid);

    const game = games.find((g) => g.appid === appid);
    if (!game) return;

    dom.heroMeta.textContent =
      [game.catalog, game.year, game.genre, game.installed ? null : 'NÃO INSTALADO']
        .filter(Boolean)
        .join(' · ');

    dom.heroTitle.textContent = game.name;

    dom.heroChips.replaceChildren(
      ...[
        `GOV ${game.profile.governor}`,
        `GPU ${game.profile.gpuLevel}`,
        `FPS ${game.profile.fpsLimit}`,
        `PRIO ${game.profile.priority}`,
      ].map((text) => {
        const chip = document.createElement('div');
        chip.className = 'chip';
        chip.textContent = text;
        return chip;
      })
    );

    dom.heroSub.textContent = game.hoursTotal
      ? `${game.hoursTotal} h jogadas · ${ultimoAcesso(game.lastPlayed)} · ${gb(game.sizeGB)}`
      : `${ultimoAcesso(game.lastPlayed)} · ${gb(game.sizeGB)}`;

    /* O aviso segue o que foi de fato desenhado: com o CDN fora do ar a
       arte da loja falha e a capa gerada entra — e aí o aviso é verdade. */
    dom.heroNoArt.hidden = true;
    const url = DataAdapter.coverUrl(appid, 'hero');
    dom.heroArt.replaceChildren(
      coverElement(game, url, 'wide', () => {
        if (selected === appid) dom.heroNoArt.hidden = false;
      })
    );

    applyPreview();
  }

  /* A tela só PROPÕE: o que a máquina faria com este título. Quem decide
     se isso vai para a régua é o chrome — com jogo em execução a medição
     real tem precedência, e a espera de assentamento do foco também é
     responsabilidade dele. */
  function applyPreview() {
    const game = games.find((g) => g.appid === selected);
    if (!game) return;
    const est = DataAdapter.estimateProfile(game.profile);
    state.set('preview', { intensity: est.intensity, watts: est.watts });
  }
}

function template() {
  const section = document.createElement('section');
  section.className = 'library screen__page';
  section.innerHTML = `
    <div class="hero">
      <div class="hero__text">
        <div class="hero__meta" data-hero="meta"></div>
        <h1 class="hero__title" data-hero="title"></h1>
        <div class="hero__chips" data-hero="chips"></div>
        <div class="hero__sub" data-hero="sub"></div>
      </div>
      <div class="hero__panel">
        <div class="hero__art" data-hero="art"></div>
        <div class="hero__scrim"></div>
        <div class="corner corner--tl"></div>
        <div class="corner corner--br"></div>
        <div class="hero__noart" data-hero="noart" hidden>SEM ARTE · CAPA GERADA</div>
      </div>
    </div>

    <div class="shelf-block">
      <div class="shelf-head">
        <div class="shelf-head__count" data-shelf="count"></div>
        <div class="shelf-head__sort" data-shelf="sort"></div>
      </div>
      <div class="shelf" data-region="shelf" data-region-flow="horizontal"></div>
    </div>`;
  return section;
}
