/* =====================================================================
   KYBER — tela 09 · Configurações

   Hub com DOIS NÍVEIS DE FOCO. A coluna de seções à esquerda e o painel
   à direita são regiões distintas: D-pad → entra no painel, ← volta à
   coluna, Ⓑ sai do hub. A seção ativa continua invertida enquanto o foco
   está no painel — selecionado e focado são coisas diferentes e coexistem
   na mesma tela.

   Trocar de seção pelo foco, e não por Ⓐ, é deliberado: percorrer a
   coluna já mostra o painel de cada seção, o que economiza um botão em
   toda visita.
   ===================================================================== */

import { state } from '../core/state.js';
import { DataAdapter } from '../data/adapter.js';
import { createStorage } from './storage.js';
import { createDownloads } from './downloads.js';
import { createUpdate } from './update.js';
import { renderBluetooth } from './bluetooth.js';
import { renderAudio } from './settings-audio.js';
import { renderNetwork } from './settings-network.js';
import { renderAppearance } from './settings-appearance.js';
import { createNotice, vizinhosLaterais } from './format.js';

const HINTS = [
  { glyph: 'A', label: 'SELECIONAR' },
  { glyph: 'B', label: 'VOLTAR' },
];

/* Seções com forma própria demais para o modelo genérico de seletores:
   cada uma se desenha e diz o que seus botões fazem. VÍDEO e SISTEMA
   continuam no modelo genérico, que é o que elas são. */
const VIVAS = {
  audio:     { render: renderAudio,      hints: ['x'] },
  rede:      { render: renderNetwork,    hints: ['y-procurar'] },
  bluetooth: { render: renderBluetooth,  hints: ['y-parear'] },
  aparencia: { render: renderAppearance, hints: ['x'] },
};

const HINT_A = { glyph: 'A', label: 'SELECIONAR' };
const HINT_B = { glyph: 'B', label: 'VOLTAR' };

const HINTS_EXTRA = {
  x:          { glyph: 'X', label: 'RESTAURAR PADRÃO' },
  'y-parear': { glyph: 'Y', label: 'PAREAR NOVO' },
  'y-procurar': { glyph: 'Y', label: 'PROCURAR' },
};

export async function createSettings({ router, input }) {
  const config = await DataAdapter.settings();
  const notice = createNotice(`${config.image} · KERNEL ${config.kernel} · MESA 25.2`);

  let atual = 0;
  let secaoViva = null;      /* seção com comportamento próprio (16b) */

  const el = template(config);
  const painel = el.querySelector('[data-settings="panel"]');
  const colunaEl = el.querySelector('[data-region="sections"]');

  renderPanel();

  el.addEventListener('kyber:focus', (e) => {
    const row = e.target.closest('[data-section]');
    if (!row) return;
    const i = Number(row.dataset.section);
    if (i === atual) return;
    atual = i;
    marcarSecao();
    renderPanel();
  });

  /* `settings: true` faz o toque no Guide não empilhar um hub sobre o
     outro — o gesto é o mesmo que abriu este. */
  return { el, settings: true, onEnter, onLeave, onAction, onMove, unmount };

  function onEnter() {
    state.set('screenName', 'CONFIGURAÇÕES');
    state.set('hints', HINTS);
    notice.restore();
  }
  function onLeave() { notice.stop(); }
  function unmount() { notice.stop(); secaoViva?.dispose?.(); }

  /* O movimento também passa pela seção viva primeiro: é assim que a
     barra de degraus fica com ← → sem o foco escorregar. */
  function onMove(dir) {
    return secaoViva?.onMove?.(dir) === true;
  }

  function onAction(action) {
    /* A seção viva tem a primeira palavra: é ela que sabe o que Ⓨ faz. */
    const tratado = secaoViva?.onAction?.(action);
    if (tratado) return true;

    if (action !== 'a') return undefined;
    const alvo = document.activeElement;

    /* Opção de seletor: aplica e repinta. */
    const opt = alvo?.closest?.('[data-option]');
    if (opt) {
      const grupo = opt.dataset.group;
      const valor = opt.dataset.option;
      DataAdapter.setOption(config.sections[atual].id, grupo, valor).then(() => {
        const g = config.sections[atual].groups.find((x) => x.key === grupo);
        if (g) g.value = valor;
        aplicarEfeito(config.sections[atual].id, grupo, valor);
        renderPanel();
      });
      return true;
    }

    /* Linha que leva a outra tela. */
    const link = alvo?.closest?.('[data-link]');
    if (link) { abrir(link.dataset.link, link.dataset.label); return true; }

    return undefined;
  }

  function abrir(id, rotulo) {
    if (id === 'storage')   { router.push(createStorage); return; }
    if (id === 'downloads') { router.push(createDownloads); return; }
    if (id === 'update')    { router.push(createUpdate); return; }
    notice(`${rotulo} · NÃO IMPLEMENTADO`);
  }

  /* Aparência mexe de verdade no launcher — seria estranho uma seção
     inteira que não faz nada. */
  function aplicarEfeito(sectionId, key, valor) {
    if (sectionId !== 'aparencia') return;
    if (key === 'vista') state.set('defaultView', valor === 'ÍNDICE' ? 'index' : 'library');
    if (key === 'ordem') {
      state.set('librarySort', ['RECENTES', 'NOME', 'TAMANHO'].indexOf(valor));
    }
  }

  function marcarSecao() {
    for (const row of colunaEl.querySelectorAll('[data-section]')) {
      row.dataset.selected = Number(row.dataset.section) === atual ? 'true' : 'false';
    }
  }

  /* ---------- painel ---------- */

  async function renderPanel() {
    const s = config.sections[atual];
    marcarSecao();

    secaoViva?.dispose?.();
    secaoViva = null;

    const viva = VIVAS[s.id];
    if (viva) {
      state.set('hints', [HINT_A, HINT_B, ...viva.hints.map((h) => HINTS_EXTRA[h])]);
      secaoViva = await viva.render(painel, { input, notice, router });
      return;
    }
    state.set('hints', HINTS);

    const grupos = (s.groups ?? []).map((g) => `
      <div class="opt">
        <div class="opt__head">
          <span class="opt__label">${g.label}</span>
          <span class="opt__hint">${g.hint}</span>
        </div>
        <div class="opt__row">
          ${g.options.map((o, i) => `
            <div class="sel focusable" tabindex="0" role="button"
                 data-group="${g.key}" data-option="${escape(o)}"
                 ${vizinhosLaterais(i, g.options.length,
                    (j) => `[data-group='${g.key}'][data-option='${g.options[j]}']`)}
                 aria-label="${escape(o)}">
              <span class="sel__led${o === g.value ? ' sel__led--on' : ''}"></span>
              <span class="sel__name">${escape(o)}</span>
            </div>`).join('')}
        </div>
      </div>`).join('');

    const links = (s.links ?? []).map((l) => `
      <div class="link row-invert" tabindex="0" role="button"
           data-link="${l.id}" data-label="${escape(l.label)}"
           aria-label="${escape(l.label)}">
        <span class="link__text">
          <span class="link__label">${escape(l.label)}</span>
          <span class="link__hint">${escape(l.hint)}</span>
        </span>
        <span class="link__go">${l.target ? 'ABRIR' : 'NÃO IMPLEMENTADO'}</span>
      </div>`).join('');

    /* UMA região para o painel inteiro, não uma por grupo: assim a
       geometria resolve tanto o passo lateral entre opções do mesmo
       grupo quanto o salto vertical entre grupos, e só a saída pela
       esquerda cai no salto declarado para a coluna. */
    painel.innerHTML = `
      <div class="panel__head">
        <h1 class="panel__title">${escape(s.title)}</h1>
        <span class="panel__note">${escape(s.note)}</span>
      </div>
      <div class="panel__body" data-region="panel" data-region-flow="vertical"
           data-region-dim="off" data-region-left="sections">${grupos}${
        links ? `<div class="links">${links}</div>` : ''
      }</div>
      <div class="panel__facts">
        ${s.facts.map((f) => `
          <div><div class="fact__label">${f.label}</div><div class="fact__value">${escape(f.value)}</div></div>
        `).join('')}
      </div>`;

  }

}

function template(config) {
  const section = document.createElement('section');
  section.className = 'settings screen__page';
  section.innerHTML = `
    <div class="sections">
      <div class="sections__label">SEÇÕES</div>
      <div class="sections__list" data-region="sections" data-region-flow="vertical"
           data-region-dim="off" data-region-right="panel">
        ${config.sections.map((s, i) => `
          <div class="section-row row-invert" tabindex="0" role="button"
               data-section="${i}" data-selected="${i === 0 ? 'true' : 'false'}"
               ${i === 0 ? 'data-focus-initial' : ''} aria-label="${s.label}">
            <span class="section-row__n">${String(i + 1).padStart(2, '0')}</span>
            <span class="section-row__name">${s.label}</span>
          </div>`).join('')}
      </div>
      <div class="sections__foot">KERNEL ${config.kernel.toUpperCase()}<br>MESA 25.2 · PROTON EXP.<br>DISCO ${config.disk.usedGB} / ${config.disk.totalGB} GB</div>
    </div>
    <div class="panel" data-settings="panel"></div>`;
  return section;
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
