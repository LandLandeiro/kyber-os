/* =====================================================================
   KYBER — 09c · seção REDE

   Dois estados, e não é o usuário quem escolhe: cabo espetado desliga o
   rádio, e a tela conta o que já aconteceu em vez de oferecer um botão
   que finge decidir. Trocar o estado no protótipo é
   `kyber.data.setSectionOption('rede', 'link', 'cabo')`.

   A senha reusa o teclado virtual em modo camada — o mesmo componente da
   busca, montado por `wifi.js`. Nada aqui duplica teclado.
   ===================================================================== */

import { DataAdapter } from '../data/adapter.js';
import { glifoHTML } from '../core/glyphs.js';
import { createWifi } from './wifi.js';
import { vizinhosLaterais } from './format.js';

export async function renderNetwork(host, { router, notice }) {
  let dados = await DataAdapter.sectionData('rede');

  desenhar();

  return { onAction };

  function onAction(action) {
    if (action === 'y') { notice('PROCURAR REDES · VARREDURA NÃO IMPLEMENTADA'); return true; }
    if (action !== 'a') return undefined;

    const alvo = document.activeElement;

    const rede = alvo?.closest?.('[data-ssid]');
    if (rede) {
      /* Conectar pede senha, e senha é o teclado virtual em camada. */
      router.push(createWifi, rede.dataset.ssid);
      return true;
    }

    const opt = alvo?.closest?.('[data-rede]');
    if (opt) {
      const chave = opt.dataset.rede;
      const valor = opt.dataset.value;
      dados[chave] = valor;
      DataAdapter.setSectionOption('rede', chave, valor);
      marcar();
      if (chave === 'enderecamento' && valor === 'manual') {
        notice('ENDEREÇAMENTO MANUAL · TECLADO DE IP NÃO IMPLEMENTADO');
      }
      return true;
    }
    return undefined;
  }

  function marcar() {
    for (const opt of host.querySelectorAll('[data-rede]')) {
      opt.dataset.on = dados[opt.dataset.rede] === opt.dataset.value ? 'true' : 'false';
    }
  }

  function escolha(chave, valor, i, lista) {
    return `
      <div class="sel focusable" tabindex="0" role="button"
           data-rede="${chave}" data-value="${escape(valor)}"
           data-on="${dados[chave] === valor ? 'true' : 'false'}"
           ${vizinhosLaterais(i, lista.length,
              (j) => `[data-rede='${chave}'][data-value='${lista[j]}']`)}
           aria-label="${escape(valor)}">
        <span class="sel__led"></span>
        <span class="sel__name">${escape(valor)}</span>
      </div>`;
  }

  function desenhar() {
    const cabo = dados.link === 'cabo';
    const f = cabo ? dados.cabo.facts : dados.wifi.facts;

    host.innerHTML = `
      <div class="panel__head">
        <h1 class="panel__title">Rede</h1>
        <span class="panel__note">CONECTADO POR ${cabo ? 'CABO' : 'WI-FI'}</span>
      </div>

      <div class="panel__body" data-region="panel" data-region-flow="vertical"
           data-region-dim="off" data-region-left="sections">
        ${cabo ? corpoCabo(dados) : corpoWifi(dados)}
      </div>

      <div class="panel__facts">
        ${f.map((x) => `
          <div><div class="fact__label">${x.label}</div><div class="fact__value">${escape(x.value)}</div></div>
        `).join('')}
      </div>`;
  }

  function corpoWifi(d) {
    const w = d.wifi;
    return `
      <div class="net-card">
        <div class="net-card__row">
          <div class="net-card__id">
            <div class="net-card__label">CONEXÃO ATUAL</div>
            <div class="net-card__ssid">${escape(w.ssid)}</div>
            <div class="net-card__meta">${w.ip} · ${w.seguranca} · canal ${w.canal}</div>
          </div>
          <div class="net-card__stats">
            ${estatistica('SINAL', w.sinal, 'dBm')}
            ${estatistica('LINK', w.linkGB, 'GB/s')}
          </div>
        </div>
      </div>

      <div class="opt__head opt__head--between">
        <span class="opt__label">REDES DISPONÍVEIS</span>
        <span class="opt__hint">${glifoHTML('A')} CONECTAR ABRE O TECLADO · ${glifoHTML('Y')} PROCURAR</span>
      </div>

      <div class="net-list">
        ${d.redes.map((r) => `
          <div class="net-row row-invert" tabindex="0" role="button"
               data-ssid="${escape(r.ssid)}" aria-label="${escape(r.ssid)}">
            <span class="net-row__name">
              <span class="net-row__dot${r.conectada ? ' net-row__dot--on' : ''}"></span>
              ${escape(r.ssid)}
            </span>
            <span class="net-row__sec">${escape(r.seguranca)}</span>
            <span class="net-row__signal">${r.sinal} dBm</span>
          </div>`).join('')}
      </div>`;
  }

  function corpoCabo(d) {
    const c = d.cabo;
    return `
      <div class="net-card">
        <div class="verified">
          <span class="verified__mark"></span>
          <span class="verified__text">ETHERNET ATIVA · NADA A CONFIGURAR</span>
        </div>
        <div class="net-card__row net-card__row--divided">
          <div class="net-card__id">
            <div class="net-card__label">ENDEREÇO ATRIBUÍDO</div>
            <div class="net-card__ip">${c.ip}</div>
            <div class="net-card__meta">${escape(c.concessao)}</div>
          </div>
          <div class="net-card__stats">
            ${estatistica('LINK', c.linkGB, 'GB/s')}
            ${estatistica('LATÊNCIA', c.latencia, 'ms')}
          </div>
        </div>
      </div>

      <div class="opt">
        <div class="opt__head">
          <span class="opt__label">RÁDIO WI-FI</span>
          <span class="opt__hint">desligado enquanto o cabo estiver conectado</span>
        </div>
        <div class="opt__row">${(['DESLIGADO', 'MANTER LIGADO']).map((v, i, l) => escolha('radio', v, i, l)).join('')}</div>
      </div>

      <div class="opt">
        <div class="opt__head">
          <span class="opt__label">ENDEREÇAMENTO</span>
          <span class="opt__hint">manual abre o teclado para IP, máscara e DNS</span>
        </div>
        <div class="opt__row">${(['dhcp', 'manual']).map((v, i, l) => escolha('enderecamento', v, i, l)).join('')}</div>
      </div>`;
  }
}

const estatistica = (rotulo, valor, unidade) => `
  <div class="net-stat">
    <div class="net-card__label">${rotulo}</div>
    <div class="net-stat__value">${valor}<span class="net-stat__unit"> ${unidade}</span></div>
  </div>`;

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
