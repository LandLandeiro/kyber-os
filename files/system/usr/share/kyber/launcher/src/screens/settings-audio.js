/* =====================================================================
   KYBER — 09b · seção ÁUDIO

   Seção viva: tem forma própria demais para o modelo genérico de
   seletores por causa do volume, que é a barra de degraus. O resto segue
   o idioma do hub.
   ===================================================================== */

import { DataAdapter } from '../data/adapter.js';
import { createStepsBar } from '../components/steps-bar.js';
import { vizinhosLaterais } from './format.js';

export async function renderAudio(host, { notice }) {
  let dados = await DataAdapter.sectionData('audio');

  const barra = createStepsBar({
    steps: 20,
    value: dados.volume,
    unit: '%',
    focusUp: "[data-audio='saida']",
    focusDown: "[data-audio='modo']",
    onChange: (v) => {
      dados.volume = v;
      DataAdapter.setSectionOption('audio', 'volume', v);
    },
  });

  desenhar();

  return { onAction, onMove: (dir) => barra.handleMove(dir) };

  function onAction(action) {
    if (action === 'x') { restaurar(); return true; }
    if (action !== 'a') return undefined;

    const opt = document.activeElement?.closest?.('[data-audio]');
    if (!opt) return undefined;

    const chave = opt.dataset.audio;
    const valor = opt.dataset.value;
    dados[chave] = valor;
    DataAdapter.setSectionOption('audio', chave, valor);
    marcar();
    return true;
  }

  async function restaurar() {
    for (const [k, v] of Object.entries({ saida: 'HDMI', volume: 14, modo: 'estéreo', som: 'ATIVO' })) {
      dados[k] = v;
      await DataAdapter.setSectionOption('audio', k, v);
    }
    barra.value = dados.volume;
    marcar();
    notice('ÁUDIO RESTAURADO AO PADRÃO');
  }

  /* Só os LEDs mudam: reconstruir o painel derrubaria o foco de quem
     acabou de escolher. */
  function marcar() {
    for (const opt of host.querySelectorAll('[data-audio]')) {
      opt.dataset.on = dados[opt.dataset.audio] === opt.dataset.value ? 'true' : 'false';
    }
  }

  function desenhar() {
    const dispositivo = (d, i) => `
      <div class="sel sel--device focusable" tabindex="0" role="button"
           data-audio="saida" data-value="${escape(d.id)}"
           data-on="${dados.saida === d.id ? 'true' : 'false'}"
           data-focus-down="[data-steps-bar]"
           ${vizinhosLaterais(i, dados.dispositivos.length,
              (j) => `[data-audio='saida'][data-value='${dados.dispositivos[j].id}']`)}
           aria-label="${escape(d.id)}">
        <span class="sel__led"></span>
        <span class="sel--device__text">
          <span class="sel--device__name">${escape(d.id)}</span>
          <span class="sel--device__sub">${escape(d.nome)}</span>
        </span>
      </div>`;

    /* Vizinho explícito para atravessar a barra de volume: ela ocupa a
       linha inteira, então seu centro fica longe do centro de qualquer
       seletor estreito e a heurística de geometria a descarta por ângulo.
       É exatamente o caso que o vizinho declarado existe para resolver. */
    const escolha = (chave, valor, i, lista) => `
      <div class="sel focusable" tabindex="0" role="button"
           data-audio="${chave}" data-value="${escape(valor)}"
           data-on="${dados[chave] === valor ? 'true' : 'false'}"
           ${chave === 'modo' ? `data-focus-up="[data-steps-bar]"` : ''}
           ${vizinhosLaterais(i, lista.length,
              (j) => `[data-audio='${chave}'][data-value='${lista[j]}']`)}
           aria-label="${escape(valor)}">
        <span class="sel__led"></span>
        <span class="sel__name">${escape(valor)}</span>
      </div>`;

    host.innerHTML = `
      <div class="panel__head">
        <h1 class="panel__title">Áudio</h1>
        <span class="panel__note">APLICA IMEDIATAMENTE</span>
      </div>

      <div class="panel__body" data-region="panel" data-region-flow="vertical"
           data-region-dim="off" data-region-left="sections">
        <div class="opt">
          <div class="opt__head">
            <span class="opt__label">SAÍDA DE ÁUDIO</span>
            <span class="opt__hint">o jogo segue a saída do sistema</span>
          </div>
          <div class="opt__row">${dados.dispositivos.map(dispositivo).join('')}</div>
        </div>

        <div class="opt">
          <div class="opt__head">
            <span class="opt__label">VOLUME PRINCIPAL</span>
            <span class="opt__hint">vinte degraus · D-pad ← → move um degrau</span>
          </div>
          <div class="opt__row" data-audio-volume></div>
        </div>

        <div class="opt">
          <div class="opt__head">
            <span class="opt__label">MODO DE SAÍDA</span>
            <span class="opt__hint">passthrough entrega o fluxo cru ao receptor</span>
          </div>
          <div class="opt__row">${(['estéreo', '5.1', 'passthrough']).map((v, i, l) => escolha('modo', v, i, l)).join('')}</div>
        </div>

        <div class="opt">
          <div class="opt__head">
            <span class="opt__label">SOM DA INTERFACE</span>
            <span class="opt__hint">retorno sonoro do foco e da confirmação</span>
          </div>
          <div class="opt__row">${(['ATIVO', 'SILENCIOSO']).map((v, i, l) => escolha('som', v, i, l)).join('')}</div>
        </div>
      </div>

      <div class="panel__facts">
        ${dados.facts.map((f) => `
          <div><div class="fact__label">${f.label}</div><div class="fact__value">${escape(f.value)}</div></div>
        `).join('')}
      </div>`;

    host.querySelector('[data-audio-volume]').append(barra.el);
  }
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
