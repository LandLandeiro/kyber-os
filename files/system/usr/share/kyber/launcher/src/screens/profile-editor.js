/* =====================================================================
   KYBER — tela 04 · Editor de perfil de performance

   Quatro grupos de seletores à esquerda, leitura em tempo real à
   direita. Cada grupo nomeia o mecanismo real do sistema por baixo:
   `power_dpm_force_performance_level` não é jargão gratuito, é o que o
   daemon escreve de verdade — e esconder isso empobreceria a tela.

   A régua entra em modo SIMULADO enquanto esta tela está montada, mesmo
   com jogo rodando. Editar é montar um cenário, não medir a máquina; e
   quem pediu a simulação tem direito de ver o resultado dela na régua.
   Sair sem salvar devolve a régua ao que era, porque a ficha por baixo
   repõe a própria previsão ao voltar.
   ===================================================================== */

import { state } from '../core/state.js';
import { DataAdapter } from '../data/adapter.js';
import { NIVEL, createNotice } from './format.js';
import { toast } from '../core/toast.js';

const HINTS = [
  { glyph: 'A', label: 'SELECIONAR' },
  { glyph: 'B', label: 'DESCARTAR' },
  { glyph: 'X', label: 'RESTAURAR PADRÃO' },
];

export async function createProfileEditor({ router }, appid) {
  const game = await DataAdapter.getGame(appid);
  const padrao = await DataAdapter.defaultProfile(appid);
  const grupos = DataAdapter.profileOptions();

  /* Cópia local: nada sai daqui sem SALVAR. */
  let perfil = { ...game.profile };

  const notice = createNotice(`steam://rungameid/${game.appid}`);
  const el = template(game, grupos);
  const dom = {
    nivel:   el.querySelector('[data-editor="nivel"]'),
    barra:   el.querySelector('[data-editor="barra"]'),
    watts:   el.querySelector('[data-editor="watts"]'),
    ruido:   el.querySelector('[data-editor="ruido"]'),
    quadros: el.querySelector('[data-editor="quadros"]'),
    latencia:el.querySelector('[data-editor="latencia"]'),
  };

  pintar();

  return { el, onEnter, onLeave, onAction, unmount };

  /* ---------- ciclo de vida ---------- */

  function onEnter() {
    state.set('screenName', 'PERFIL DE PERFORMANCE');
    state.set('hints', HINTS);
    notice.restore();
    simular();
  }

  function onLeave() { notice.stop(); }
  function unmount() { notice.stop(); }

  /* ---------- ações ---------- */

  function onAction(action) {
    if (action === 'x') { restaurar(); return true; }
    if (action !== 'a') return undefined;

    const alvo = document.activeElement;

    const opt = alvo?.closest?.('[data-option]');
    if (opt) {
      perfil = { ...perfil, [opt.dataset.group]: opt.dataset.option };
      pintar();
      return true;
    }

    if (alvo?.dataset?.editor === 'save')    { salvar(); return true; }
    if (alvo?.dataset?.editor === 'discard') { router.pop(); return true; }
    return undefined;
  }

  function restaurar() {
    perfil = { ...padrao };
    pintar();
    notice('PERFIL RESTAURADO AO PADRÃO DO TÍTULO');
  }

  async function salvar() {
    await DataAdapter.setProfile(appid, perfil);
    const est = DataAdapter.estimateProfile(perfil);
    router.pop();
    toast({
      kind: 'info',
      title: 'PERFIL SALVO',
      body: `${game.name} · ${NIVEL[est.level].toLowerCase()} · estimativa de ${est.watts} W`,
    });
  }

  /* ---------- leitura em tempo real ---------- */

  function pintar() {
    const est = DataAdapter.estimateProfile(perfil);

    for (const botao of el.querySelectorAll('[data-option]')) {
      const aceso = perfil[botao.dataset.group] === botao.dataset.option;
      botao.dataset.on = aceso ? 'true' : 'false';
    }

    dom.nivel.textContent = NIVEL[est.level];
    dom.barra.style.width = `${(est.intensity * 100).toFixed(1)}%`;
    dom.watts.textContent = est.watts;
    dom.ruido.textContent = est.noise;
    dom.quadros.textContent = est.frames;
    dom.latencia.textContent = est.latency;

    simular(est);
  }

  function simular(est = DataAdapter.estimateProfile(perfil)) {
    state.set('preview', { intensity: est.intensity, watts: est.watts, force: true });
  }
}

function template(game, grupos) {
  const section = document.createElement('section');
  section.className = 'editor screen__page';

  const grupo = (g) => `
    <div class="group">
      <div class="group__head">
        <span class="group__label">${g.label}</span>
        <span class="group__hint">${escape(g.hint)}</span>
      </div>
      <div class="group__row">
        ${g.options.map((o) => `
          <div class="opt-btn focusable" tabindex="0" role="button"
               data-group="${g.key}" data-option="${escape(o)}"
               data-on="false" aria-label="${escape(o)}">
            <span class="opt-btn__led"></span>
            <span class="opt-btn__name">${escape(o)}</span>
          </div>`).join('')}
      </div>
    </div>`;

  const linha = (rotulo, chave) => `
    <div class="reading__row">
      <span>${rotulo}</span>
      <span data-editor="${chave}"></span>
    </div>`;

  section.innerHTML = `
    <div class="editor__left" data-region="groups" data-region-flow="vertical"
         data-region-dim="off" data-region-right="editor-actions">
      <div class="editor__kicker">PERFIL POR JOGO · ${escape(game.name)}</div>
      <h1 class="editor__title">Performance</h1>
      <div class="groups">${grupos.map(grupo).join('')}</div>
    </div>

    <div class="reading">
      <div class="reading__kicker">LEITURA EM TEMPO REAL</div>
      <div class="reading__level" data-editor="nivel"></div>
      <div class="reading__track"><div class="reading__fill" data-editor="barra"></div></div>

      <div class="reading__watts">
        <span class="reading__watts-value" data-editor="watts"></span>
        <span class="reading__watts-unit">W · pacote</span>
      </div>
      <div class="reading__source">ESTIMATIVA DO GAMEPROFILED</div>

      <div class="reading__rows">
        ${linha('Ruído do ventilador', 'ruido')}
        ${linha('Quadros estimados', 'quadros')}
        ${linha('Latência de entrada', 'latencia')}
      </div>

      <div class="reading__actions" data-region="editor-actions"
           data-region-flow="horizontal" data-region-dim="off"
           data-region-left="groups">
        <div class="btn btn--primary focusable" tabindex="0" role="button"
             data-editor="save">SALVAR</div>
        <div class="btn btn--quiet focusable" tabindex="0" role="button"
             data-editor="discard">B</div>
      </div>
    </div>`;

  section.querySelector('[data-option]')?.setAttribute('data-focus-initial', '');
  return section;
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
