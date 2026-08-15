/* =====================================================================
   KYBER — tela 05 · Primeira execução

   Passo 1 de 4. Checklist do que a máquina encontrou sozinha, à direita;
   a tese do produto à esquerda. Sem régua: é tela de boot, e a decisão
   está registrada na identidade visual.

   Os quatro estados do checklist ficam acromáticos. O mockup usa verde
   para OK e azul para ATIVO, o que seriam quatro ocorrências da rampa de
   estado numa tela só — e a rampa é reservada ao estado da máquina, não
   a "deu certo". Luminância diz a mesma coisa sem gastar o orçamento.
   ===================================================================== */

import { state } from '../core/state.js';
import { glifoHTML } from '../core/glyphs.js';
import { DataAdapter } from '../data/adapter.js';

const HINTS = [{ glyph: 'A', label: 'CONTINUAR' }];

export async function createWelcome({ firstRun, input }) {
  const settings = await DataAdapter.settings();
  const jogos = await DataAdapter.listGames();
  const disco = await DataAdapter.storage();

  const controle = input?.activePad;

  const itens = [
    { nome: 'Controle detectado',
      dado: controle
        ? `${String(controle.id).replace(/\s*\([^)]*\)\s*$/, '').toUpperCase()} · GAMEPAD API`
        : 'NENHUM · TECLADO NAVEGA',
      estado: controle ? 'OK' : 'PENDENTE', forte: Boolean(controle) },
    { nome: 'Saída de vídeo',
      dado: `${settings.resolution} · ${settings.refresh} · VRR ATIVO`,
      estado: 'OK', forte: true },
    { nome: 'Bibliotecas encontradas',
      dado: `STEAM · ${jogos.length} TÍTULOS · ${Math.round(disco.usedGB)} GB`,
      estado: 'OK', forte: true },
    { nome: 'gameprofiled',
      dado: 'PERFIS PADRÃO EM MODO EQUILIBRADO',
      estado: 'ATIVO', forte: false },
  ];

  const el = document.createElement('section');
  el.className = 'welcome screen__page';
  el.innerHTML = `
    <div class="welcome__tese">
      <div class="welcome__kicker">PRIMEIRA EXECUÇÃO · ${settings.build.replace('KYBER · ', '')} · KERNEL ${settings.kernel.toUpperCase()}</div>
      <div class="welcome__mark">KYBER</div>
      <p class="welcome__claim">Sem ambiente gráfico. Sem janelas. A biblioteca é o sistema.</p>
    </div>

    <div class="welcome__check">
      <div class="checklist">
        ${itens.map((i) => `
          <div class="checklist__row">
            <div>
              <div class="checklist__name">${i.nome}</div>
              <div class="checklist__data">${i.dado}</div>
            </div>
            <div class="checklist__state${i.forte ? '' : ' checklist__state--soft'}">${i.estado}</div>
          </div>`).join('')}
      </div>

      <div class="welcome__actions" data-region="welcome" data-region-flow="horizontal"
           data-region-dim="off">
        <div class="btn btn--primary focusable" tabindex="0" role="button"
             data-welcome="start" data-focus-initial>COMEÇAR</div>
      </div>
      <div class="welcome__hint">${glifoHTML('A')} CONFIRMAR</div>
    </div>`;

  return { el, chrome: 'boot', onEnter, onAction };

  function onEnter() {
    state.set('screenName', 'PRIMEIRA EXECUÇÃO');
    state.set('bootStep', { n: 1, total: 4, label: 'BOAS-VINDAS' });
    state.set('hints', HINTS);
    state.set('context', `${settings.compositor.toUpperCase()} · ${settings.resolution} · ${settings.refresh}`);
  }

  function onAction(action) {
    if (action === 'a') { firstRun.avancar(); return true; }
    /* Ⓑ no primeiro passo não tem para onde voltar. */
    if (action === 'b') return true;
    return undefined;
  }
}
