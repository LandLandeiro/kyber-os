/* =====================================================================
   KYBER — tela 13 · Busca

   Consulta espelhada no topo, resultados no meio, teclado ancorado
   embaixo. O D-pad ↑ sai do teclado para a lista sem fechar nada: o
   teclado é camada dentro da tela, não uma tela por cima dela.

   Ⓑ é contextual por região, e isso está gravado nas próprias teclas:
   com o foco no teclado, Ⓑ APAGA; com o foco na lista, Ⓑ fecha a busca.
   ===================================================================== */

import { state } from '../core/state.js';
import { glifo, glifoHTML } from '../core/glyphs.js';
import { DataAdapter } from '../data/adapter.js';
import { createKeyboard } from '../components/keyboard.js';
import { generatedCover } from './cover.js';
import { horas, NIVEL, createNotice } from './format.js';
import { createDetail } from './detail.js';

const HINTS = [
  { glyph: 'A', label: 'ABRIR' },
  { glyph: 'B', label: 'FECHAR BUSCA' },
];

export async function createSearch({ router, focus }) {
  const total = (await DataAdapter.listGames()).length;
  const notice = createNotice(`BUSCA EM ${total} TÍTULOS`);

  const el = template();
  const valorEl = el.querySelector('[data-search="value"]');
  const contaEl = el.querySelector('[data-search="count"]');
  const listaEl = el.querySelector('[data-region="results"]');
  const restoEl = el.querySelector('[data-search="rest"]');

  const teclado = createKeyboard({
    focus,
    mode: 'inline',
    region: 'keyboard',
    regionUp: 'results',
    actions: ['numeros', 'espaco', 'apagar'],
    /* Quem abre a busca veio digitar: o foco começa no teclado e o
       D-pad ↑ leva aos resultados quando houver o que escolher. */
    initialFocus: true,
    hint: { label: 'RESULTADOS', engraving: 'D-PAD ↑' },
    onChange: (v) => { valorEl.textContent = v.toUpperCase(); buscar(v); },
  });
  el.querySelector('[data-search="kb"]').append(teclado.el);

  buscar('');

  return { el, onEnter, onLeave, onAction, unmount };

  function onEnter() {
    state.set('screenName', 'BUSCA');
    state.set('hints', HINTS);
    notice.restore();
  }
  function onLeave() { notice.stop(); }
  function unmount() { notice.stop(); }

  function onAction(action) {
    /* O teclado tem a primeira palavra enquanto está com o foco. */
    if (teclado.handleAction(action)) return true;

    if (action === 'a') {
      const row = document.activeElement?.closest?.('[data-appid]');
      if (row) { router.push(createDetail, Number(row.dataset.appid)); return true; }
    }
    return undefined;
  }

  async function buscar(consulta) {
    const achados = await DataAdapter.search(consulta);
    contaEl.textContent = consulta
      ? `${achados.length} RESULTADO${achados.length === 1 ? '' : 'S'} DE ${total}`
      : `${total} TÍTULOS`;

    const visiveis = achados.slice(0, 3);
    listaEl.replaceChildren(...visiveis.map((g) => linha(g, consulta)));

    restoEl.textContent = !consulta
      ? `${achados.length} TÍTULOS · DIGITE PARA FILTRAR · D-PAD ↑ SAI PARA A LISTA`
      : achados.length === 0
        ? `NENHUM TÍTULO COM ESSE COMEÇO · ${glifo('B')} APAGA`
        : achados.length > 3
          ? `MAIS ${achados.length - 3} ABAIXO · D-PAD ↑ SAI DO TECLADO PARA A LISTA`
          : 'FIM DOS RESULTADOS · D-PAD ↑ SAI DO TECLADO PARA A LISTA';

  }

  function linha(game, consulta) {
    const node = document.createElement('div');
    node.className = 'result row-invert';
    node.tabIndex = 0;
    node.setAttribute('role', 'button');
    node.setAttribute('aria-label', game.name);
    node.dataset.appid = game.appid;

    const est = DataAdapter.estimateProfile(game.profile);
    const vivo = state.get('runningGame')?.appid === game.appid;

    node.innerHTML = `
      <div class="result__thumb"></div>
      <div class="result__name">${destacar(game.name, consulta)}</div>
      <div class="result__genre">${game.genre}</div>
      <div class="result__hours">${game.hoursTotal ? horas(game.hoursTotal) : '—'}</div>
      <div class="result__state">${
        vivo ? 'EM EXECUÇÃO' : game.installed ? NIVEL[est.level] : 'NÃO INSTALADO'
      }</div>`;
    node.querySelector('.result__thumb').append(generatedCover(game, 'tile'));
    return node;
  }
}

/* Sublinha o trecho que casou, para o olho conferir por que aquela linha
   está ali. */
function destacar(nome, consulta) {
  const q = consulta.trim();
  if (!q) return escape(nome);
  const i = nome.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return escape(nome);
  return `${escape(nome.slice(0, i))}<span class="hit">${escape(nome.slice(i, i + q.length))}</span>${escape(nome.slice(i + q.length))}`;
}

function template() {
  const section = document.createElement('section');
  section.className = 'search screen__page';
  section.innerHTML = `
    <div class="query">
      <div class="query__label">CONSULTA</div>
      <div class="mirror">
        <span class="mirror__value" data-search="value"></span>
        <span class="mirror__caret"></span>
      </div>
      <div class="query__count" data-search="count"></div>
    </div>

    <div class="results">
      <div class="results__head">
        <div>Nº</div><div>TÍTULO</div><div>GÊNERO</div>
        <div class="results__right">HORAS</div>
        <div class="results__right">ESTADO</div>
      </div>
      <div class="results__list" data-region="results" data-region-flow="vertical"
           data-region-dim="off" data-region-down="keyboard"></div>
      <div class="results__rest texture">
        <span data-search="rest"></span>
        <span>${glifoHTML('A')} ABRIR · ${glifoHTML('B')} FECHAR BUSCA</span>
      </div>
    </div>

    <div class="search__kb" data-search="kb"></div>`;
  return section;
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
