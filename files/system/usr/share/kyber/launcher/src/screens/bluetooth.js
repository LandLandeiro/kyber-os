/* =====================================================================
   KYBER — tela 16b · Bluetooth

   Painel da seção BLUETOOTH do hub. Os controles listados são os que a
   Gamepad API está reportando AGORA — não há controle fictício aqui.

   O que o navegador expõe é identificação, layout e contagem de botões.
   Carga de bateria e potência de sinal NÃO são expostas, e a tela diz
   isso em vez de desenhar uma barra inventada: instrumento que mostra
   número que não mediu é pior que instrumento que admite não saber.
   Fone e teclado vêm do mock porque são do rádio do console, fora do
   alcance do navegador.
   ===================================================================== */

import { DataAdapter } from '../data/adapter.js';
import { toast } from '../core/toast.js';
import { familiaDe, NOME_FAMILIA, glifoHTML } from '../core/glyphs.js';

export async function renderBluetooth(host, { input, notice }) {
  const dados = await DataAdapter.bluetooth();

  desenhar();
  window.addEventListener('kyber:pad', desenhar);

  return { onAction, dispose: () => window.removeEventListener('kyber:pad', desenhar) };

  /* ---------- ações ---------- */

  function onAction(action) {
    if (action === 'y') {
      notice('PAREAR NOVO · TELA DE PAREAMENTO NÃO IMPLEMENTADA');
      return true;
    }
    if (action !== 'a') return undefined;

    const alvo = document.activeElement?.closest?.('[data-bt]');
    if (!alvo) return undefined;

    /* Um controle que o navegador está reportando não some porque a
       interface mandou: quem pareia e despareia é o rádio do sistema. */
    if (alvo.dataset.bt === 'pad') {
      notice('ESQUECER CONTROLE · O NAVEGADOR NÃO DESPAREIA DISPOSITIVO');
      return true;
    }
    if (alvo.dataset.bt === 'device') {
      const id = alvo.dataset.id;
      const nome = alvo.dataset.name;
      DataAdapter.forgetDevice(id).then(async () => {
        dados.others = (await DataAdapter.bluetooth()).others;
        desenhar();
        toast({ kind: 'device', title: 'DISPOSITIVO ESQUECIDO', body: `${nome} · removido da memória do rádio` });
      });
      return true;
    }
    return undefined;
  }

  /* ---------- desenho ---------- */

  function pads() {
    const vivos = navigator.getGamepads?.() ?? [];
    return [...input.pads.entries()].map(([index, p]) => {
      const bruto = vivos[index];
      return {
        index,
        name: String(p.id).replace(/\s*\([^)]*\)\s*$/, '').trim() || 'controle genérico',
        mapping: p.mapping === 'standard' ? 'LAYOUT PADRÃO' : 'LAYOUT DESCONHECIDO',
        familia: NOME_FAMILIA[familiaDe(p.id)],
        buttons: bruto?.buttons?.length ?? 0,
        axes: bruto?.axes?.length ?? 0,
        ativo: index === input.padIndex,
      };
    });
  }

  function desenhar() {
    const lista = pads();

    const controles = lista.length
      ? lista.map((p) => `
          <div class="bt-row focusable" tabindex="0" role="button"
               data-bt="pad" aria-label="${escape(p.name)}">
            <div class="bt-row__id">
              <div class="bt-row__name">${escape(p.name)}</div>
              <div class="bt-row__meta">CONTROLE ${p.index + 1} · ${p.familia} · ${p.mapping} · ${p.buttons} BOTÕES</div>
            </div>
            <div class="bt-row__col">
              <div class="bt-row__label">${p.ativo ? 'CONECTADO · DIRIGINDO' : 'CONECTADO'}</div>
              <div class="bt-row__value">via Gamepad API</div>
            </div>
            <div class="bt-row__col">
              <div class="bt-row__label">BATERIA</div>
              <div class="bt-row__value bt-row__value--unknown">não exposta</div>
            </div>
            <div class="bt-row__action"><span class="tag">ESQUECER</span></div>
          </div>`).join('')
      : `<div class="bt-empty texture">
           <span>NENHUM CONTROLE CONECTADO · A NAVEGAÇÃO ESTÁ NO TECLADO</span>
           <span>${glifoHTML('Y')} ATIVAR MODO DE PAREAMENTO</span>
         </div>`;

    const outros = dados.others.length
      ? dados.others.map((d) => `
          <div class="bt-device focusable" tabindex="0" role="button"
               data-bt="device" data-id="${d.id}" data-name="${escape(d.name)}"
               aria-label="${escape(d.name)}">
            <div>
              <div class="bt-device__name">${escape(d.name)}</div>
              <div class="bt-device__meta">${d.kind} · ${d.state}</div>
            </div>
            <div class="bt-device__signal">${d.signal}</div>
          </div>`).join('')
      : `<div class="bt-empty texture">
           <span>NENHUM OUTRO DISPOSITIVO NA MEMÓRIA</span>
           <span>${glifoHTML('Y')} ATIVAR MODO DE PAREAMENTO</span>
         </div>`;

    host.innerHTML = `
      <div class="panel__head">
        <h1 class="panel__title">Bluetooth</h1>
        <span class="panel__note">${lista.length ? 'RÁDIO ATIVO' : 'RÁDIO ATIVO · SEM CONTROLE'}</span>
      </div>

      <div class="panel__body bt" data-region="panel" data-region-flow="vertical"
           data-region-dim="off" data-region-left="sections">
        <div class="bt__label">CONTROLES PAREADOS</div>
        ${controles}
        <p class="bt__note">O navegador expõe identificação, layout e contagem de botões. Carga de bateria e potência de sinal ficam do lado do sistema e não chegam até aqui.</p>

        <div class="bt__label bt__label--spaced">OUTROS DISPOSITIVOS</div>
        ${outros}
      </div>

      <div class="panel__facts">
        <div><div class="fact__label">RÁDIO</div><div class="fact__value">${dados.radio.name}</div></div>
        <div><div class="fact__label">LATÊNCIA DE ENTRADA</div><div class="fact__value">${dados.radio.latency}</div></div>
        <div><div class="fact__label">MODO DE PAREAMENTO</div><div class="fact__value">${glifoHTML('Y')} ${dados.radio.pairing}</div></div>
      </div>`;
  }
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
