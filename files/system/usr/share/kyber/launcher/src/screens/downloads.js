/* =====================================================================
   KYBER — tela 18 · Downloads

   Item ativo em destaque, fila embaixo. Ⓐ executa a ação da linha em
   foco; a fila vazia (18b) é outra tela, não um estado apagado desta.
   ===================================================================== */

import { state } from '../core/state.js';
import { glifoHTML } from '../core/glyphs.js';
import { DataAdapter } from '../data/adapter.js';
import { generatedCover } from './cover.js';
import { gb, createNotice } from './format.js';
import { toast } from '../core/toast.js';
import { createLoader } from '../components/loader.js';

const HINTS = [
  { glyph: 'A', label: 'EXECUTAR AÇÃO' },
  { glyph: 'B', label: 'VOLTAR' },
  { glyph: 'Y', label: 'LIMITE DE BANDA' },
];

export async function createDownloads({ router, focus }) {
  let fila = await DataAdapter.listDownloads();
  const disk = await DataAdapter.storage();
  const notice = createNotice('REDE 1 GB/S · WI-FI 6E · LIMITE DE BANDA DESATIVADO');

  const el = document.createElement('section');
  el.className = 'downloads screen__page';

  render();

  return { el, onEnter, onLeave, onAction, unmount };

  function onEnter() {
    state.set('screenName', 'DOWNLOADS');
    state.set('hints', HINTS);
    notice.restore();
  }
  function onLeave() { notice.stop(); }
  function unmount() { notice.stop(); }

  function onAction(action) {
    if (action === 'y') { notice('LIMITE DE BANDA · NÃO IMPLEMENTADO'); return true; }
    if (action !== 'a') return undefined;

    const alvo = document.activeElement;
    const acao = alvo?.dataset?.dl;
    if (!acao) return undefined;

    if (acao === 'check')   { notice('VERIFICAR AGORA · NÃO IMPLEMENTADO'); return true; }
    if (acao === 'history') { notice('HISTÓRICO DE DOWNLOADS · NÃO IMPLEMENTADO'); return true; }

    const id = alvo.dataset.id;
    executar(id, acao);
    return true;
  }

  async function executar(id, acao) {
    const alvo = fila.find((d) => d.id === id);
    await DataAdapter.downloadAction(id, acao);
    fila = await DataAdapter.listDownloads();

    if (acao === 'cancel' && alvo) {
      toast({ kind: 'info', title: 'DOWNLOAD CANCELADO',
              body: `${alvo.name} · ${gb(alvo.totalGB - alvo.doneGB)} não baixados` });
    }
    render();
  }

  /* ---------- desenho ---------- */

  function render() {
    el.replaceChildren();
    el.innerHTML = fila.length ? cheia() : vazia();

    if (fila.length) {
      el.querySelector('[data-dl="cover"]').append(generatedCover(fila[0], 'tile'));
      /* Espera longa e de duração desconhecida: varredura. Só enquanto
         de fato baixa — pausado não é espera, é estado parado. */
      if (fila[0].state === 'BAIXANDO') {
        el.querySelector('[data-dl="loader"]')?.append(createLoader('varredura', 26));
      }
      const primeiro = el.querySelector('[data-dl][tabindex]');
      primeiro?.setAttribute('data-focus-initial', '');
      if (el.isConnected) focus.mount(el);
    } else {
      el.querySelector('[data-dl="check"]')?.setAttribute('data-focus-initial', '');
      if (el.isConnected) focus.mount(el);
    }
  }

  function cheia() {
    const ativo = fila[0];
    const restantes = fila.slice(1);
    const pct = ((ativo.doneGB / ativo.totalGB) * 100).toFixed(1);
    const faltam = ativo.totalGB - ativo.doneGB;
    const seg = ativo.speedMB ? Math.round((faltam * 1024) / ativo.speedMB) : null;
    const livreApos = Math.round(disk.totalGB - disk.usedGB - faltam);

    const acoes = ativo.state === 'PAUSADO'
      ? [['resume', 'RETOMAR', true], ['cancel', 'CANCELAR', false]]
      : [['pause', 'PAUSAR', true], ['cancel', 'CANCELAR', false]];

    return `
      <div class="dl-active">
        <div class="dl-active__id">
          <div class="dl-active__cover" data-dl="cover"></div>
          <div class="dl-active__text">
            <div class="dl-active__kicker">
              <span class="dl-active__estado"><span data-dl="loader"></span>${ativo.state} · ${escape(ativo.kind)}</span>
              <span>${ativo.catalog} · APPID ${ativo.appid}</span>
            </div>
            <div class="dl-active__name">${escape(ativo.name)}</div>
            <div class="dl-bar"><div class="dl-bar__fill" style="width:${pct}%"></div>
              <div class="dl-bar__ticks"></div></div>
          </div>
        </div>

        <div class="dl-metrics">
          ${metric('BAIXADO', Math.round(ativo.doneGB), ` / ${ativo.totalGB} GB`, 'big')}
          ${metric('VELOCIDADE', ativo.speedMB, ' MB/s')}
          ${metric('RESTANTE', seg === null ? '—' : Math.floor(seg / 60), seg === null ? '' : ` min ${seg % 60} s`)}
          ${metric('DISCO APÓS', livreApos, ' GB livres')}
        </div>

        <div class="dl-actions" data-region="actions" data-region-flow="horizontal"
             data-region-dim="off" data-region-down="queue">
          ${acoes.map(([id, rotulo, primario]) => `
            <div class="btn${primario ? ' btn--primary' : ''} focusable" tabindex="0"
                 role="button" data-dl="${id}" data-id="${ativo.id}">${rotulo}</div>`).join('')}
          <div class="dl-actions__note">REDE 1 GB/s · WI-FI 6E<br>LIMITE DE BANDA DESATIVADO</div>
        </div>
      </div>

      <div class="queue">
        <div class="queue__head">
          <div>Nº</div><div>NA FILA</div>
          <div class="queue__right">TAMANHO</div>
          <div class="queue__right">ESTADO</div>
          <div class="queue__right">AÇÃO</div>
        </div>
        <div class="queue__list" data-region="queue" data-region-flow="vertical"
             data-region-dim="off" data-region-up="actions">
          ${restantes.map((d, i) => `
            <div class="queue__row row-invert" tabindex="0" role="button"
                 data-dl="prioritize" data-id="${d.id}" aria-label="${escape(d.name)}">
              <span class="queue__n">${String(i + 2).padStart(2, '0')}</span>
              <span class="queue__name">${escape(d.name)}</span>
              <span class="queue__size">${d.totalGB} GB</span>
              <span class="queue__state">${d.state}</span>
              <span class="queue__action"><span class="tag">PRIORIZAR</span></span>
            </div>`).join('')}
        </div>
        <div class="queue__rest texture">
          <span>${restantes.length
            ? `${glifoHTML('A')} PRIORIZA A LINHA EM FOCO`
            : 'NADA MAIS NA FILA'}</span>
          <span>${fila.reduce((s, d) => s + (d.totalGB - d.doneGB), 0)} GB RESTANTES NO TOTAL</span>
        </div>
      </div>`;
  }

  /* Tela 18b — fila vazia. Não é a 18 apagada: tem hierarquia própria. */
  function vazia() {
    return `
      <div class="dl-empty">
        <div class="dl-empty__text">
          <div class="dl-empty__kicker">FILA VAZIA</div>
          <h1 class="dl-empty__title">Nenhum download ativo</h1>
          <p class="dl-empty__body">Atualizações são baixadas automaticamente quando o console está em repouso.</p>
          <div class="dl-empty__rows">
            ${[['Última verificação', '22:31'], ['Baixado hoje', '60 GB'],
               ['Disco livre', `${Math.round(disk.totalGB - disk.usedGB)} GB`]]
              .map(([k, v]) => `<div class="dl-empty__row"><span>${k}</span><span>${v}</span></div>`).join('')}
          </div>
          <div class="dl-empty__actions" data-region="empty" data-region-flow="horizontal"
               data-region-dim="off">
            <div class="btn btn--primary focusable" tabindex="0" role="button"
                 data-dl="check">VERIFICAR AGORA</div>
            <div class="btn focusable" tabindex="0" role="button"
                 data-dl="history">HISTÓRICO</div>
          </div>
        </div>
        <div class="dl-empty__chart texture">
          <div class="corner corner--tl"></div>
          <div class="corner corner--br"></div>
          <div class="dl-empty__axis"></div>
          <div class="dl-empty__chart-label">TRÁFEGO DE REDE · ÚLTIMAS 24 H</div>
          <div class="dl-empty__bars">
            ${[6,4,9,5,3,12,38,64,22,8,5,14,47,10,6,4,9,28,55,31,12,7,5,9]
              .map((h) => `<span style="height:${h}%" data-strong="${h > 20}"></span>`).join('')}
          </div>
        </div>
      </div>`;
  }

  function metric(label, valor, unidade, size = '') {
    return `
      <div class="dl-metric${size ? ' dl-metric--big' : ''}">
        <div class="dl-metric__label">${label}</div>
        <div class="dl-metric__value">${valor}<span class="dl-metric__unit">${unidade}</span></div>
      </div>`;
  }
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
