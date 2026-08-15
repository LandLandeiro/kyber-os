/* =====================================================================
   KYBER — 09d · seção APARÊNCIA

   Três seletores e a fresta de luz do gabinete. A fresta é o único
   controle de toda a interface que atua sobre o objeto físico, e a
   prévia usa o âmbar de verdade: a identidade diz que é a mesma cor no
   gabinete e no pixel, e uma prévia acromática mentiria sobre o que o
   botão faz. Por ora só persiste no mock — não há hardware do outro lado.
   ===================================================================== */

import { state } from '../core/state.js';
import { glifoHTML } from '../core/glyphs.js';
import { DataAdapter } from '../data/adapter.js';
import { vizinhosLaterais } from './format.js';

export async function renderAppearance(host, { notice }) {
  let dados = await DataAdapter.sectionData('aparencia');

  desenhar();

  return { onAction };

  function onAction(action) {
    if (action === 'x') { restaurar(); return true; }
    if (action !== 'a') return undefined;

    const opt = document.activeElement?.closest?.('[data-aparencia]');
    if (!opt) return undefined;

    aplicar(opt.dataset.aparencia, opt.dataset.value);
    return true;
  }

  async function aplicar(chave, valor) {
    await DataAdapter.setSectionOption('aparencia', chave, valor);
    dados = await DataAdapter.sectionData('aparencia');

    /* Duas destas mexem no launcher de verdade. */
    if (chave === 'vista') state.set('defaultView', valor === 'ÍNDICE' ? 'index' : 'library');
    if (chave === 'ordem') {
      state.set('librarySort', ['RECENTES', 'NOME', 'TAMANHO'].indexOf(valor));
    }
    if (chave === 'capa') {
      notice(valor === 'SEMPRE CAPA GERADA'
        ? 'CAPA GERADA EM TODOS OS TÍTULOS'
        : 'ARTE DA LOJA QUANDO HOUVER');
    }
    if (chave === 'fresta') {
      notice(`FRESTA ${valor} · SEM HARDWARE DO OUTRO LADO NESTE PROTÓTIPO`);
    }
    marcar();
  }

  async function restaurar() {
    for (const [k, v] of Object.entries({
      vista: 'VITRINE', ordem: 'RECENTES',
      capa: 'ARTE DA LOJA QUANDO HOUVER', fresta: 'DISCRETO',
    })) await aplicar(k, v);
    notice('APARÊNCIA RESTAURADA AO PADRÃO');
  }

  function marcar() {
    for (const opt of host.querySelectorAll('[data-aparencia]')) {
      const chave = opt.dataset.aparencia;
      const atual = chave === 'fresta' ? dados.fresta.nivel : dados[chave];
      opt.dataset.on = atual === opt.dataset.value ? 'true' : 'false';
    }
    const luz = host.querySelector('[data-fresta="luz"]');
    if (luz) luz.style.opacity = dados.fresta.opacidade;
    const rotulo = host.querySelector('[data-fresta="rotulo"]');
    if (rotulo) rotulo.textContent = dados.fresta.rotulo;
  }

  function escolha(chave, valor, atual, i, lista) {
    return `
      <div class="sel focusable" tabindex="0" role="button"
           data-aparencia="${chave}" data-value="${escape(valor)}"
           data-on="${atual === valor ? 'true' : 'false'}"
           ${vizinhosLaterais(i, lista.length,
              (j) => `[data-aparencia='${chave}'][data-value='${lista[j]}']`)}
           aria-label="${escape(valor)}">
        <span class="sel__led"></span>
        <span class="sel__name">${escape(valor)}</span>
      </div>`;
  }

  function grupo(rotulo, dica, chave, valores, atual) {
    return `
      <div class="opt">
        <div class="opt__head">
          <span class="opt__label">${rotulo}</span>
          <span class="opt__hint">${dica}</span>
        </div>
        <div class="opt__row">${valores.map((v, i) => escolha(chave, v, atual, i, valores)).join('')}</div>
      </div>`;
  }

  function desenhar() {
    host.innerHTML = `
      <div class="panel__head">
        <h1 class="panel__title">Aparência</h1>
        <span class="panel__note">QUATRO CONTROLES</span>
      </div>

      <div class="panel__body" data-region="panel" data-region-flow="vertical"
           data-region-dim="off" data-region-left="sections">
        ${grupo('VISTA PADRÃO DA BIBLIOTECA', `${glifoHTML('Y')} alterna a qualquer momento`,
                'vista', ['VITRINE', 'ÍNDICE'], dados.vista)}
        ${grupo('ORDENAÇÃO PADRÃO', 'LB e RB reordenam dentro da sessão',
                'ordem', ['RECENTES', 'NOME', 'TAMANHO'], dados.ordem)}
        ${grupo('COMPORTAMENTO DA CAPA', 'capa gerada mantém a grade previsível',
                'capa', ['ARTE DA LOJA QUANDO HOUVER', 'SEMPRE CAPA GERADA'], dados.capa)}

        <div class="fresta">
          <div class="fresta__head">
            <div class="opt__head">
              <span class="opt__label fresta__label">FRESTA DE LUZ DO GABINETE</span>
              <span class="opt__hint">a única coisa aqui que sai da tela</span>
            </div>
            <span class="fresta__badge">CONTROLA O HARDWARE</span>
          </div>

          <div class="opt__row fresta__row">
            ${(['DESLIGADO', 'DISCRETO', 'PLENO'])
              .map((v, i, l) => escolha('fresta', v, dados.fresta.nivel, i, l)).join('')}
          </div>

          <div class="fresta__preview">
            <span class="fresta__preview-label">PRÉVIA</span>
            <div class="fresta__slot">
              <div class="fresta__light" data-fresta="luz"
                   style="opacity:${dados.fresta.opacidade}"></div>
            </div>
            <span class="fresta__value" data-fresta="rotulo">${dados.fresta.rotulo}</span>
          </div>
        </div>

        <p class="aparencia__note">A escala da interface fica em <span>Vídeo</span>, ao lado da resolução. Tema claro e cores alternativas não existem: cor saturada é reservada ao estado da máquina.</p>
      </div>`;
  }
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
