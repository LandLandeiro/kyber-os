/* =====================================================================
   KYBER — tela 16a · Pareamento de controle

   Passo 3 de 4, e o único passo do fluxo que pode não acontecer: se já
   houver controle conectado quando o fluxo chega aqui, ela é pulada.

   Esta é a tela onde teclado e controle serem cidadãos de igual peso
   deixa de ser princípio e vira requisito: por definição não existe
   controle pareado, então o rodapé ensina a saída pelo teclado em vez
   de gravar botões que ninguém pode apertar.

   E ela reage ao rádio de verdade: parear um controle enquanto a tela
   está aberta faz o fluxo seguir sozinho, porque a pessoa já provou o
   que a tela pedia.
   ===================================================================== */

import { state } from '../core/state.js';
import { DataAdapter } from '../data/adapter.js';
import { createLoader } from '../components/loader.js';
import { PAREAMENTO, familiaAtual } from '../core/glyphs.js';

const HINTS = [{ glyph: 'A', label: 'PULAR', key: 'ENTER' }];

export async function createPairing({ firstRun, input }) {
  const bt = await DataAdapter.bluetooth();

  const el = template(state.get('controllers') > 0 ? familiaAtual() : null);
  /* Tela dedicada à espera, com espaço para o símbolo grande: camadas. */
  el.querySelector('[data-pair="loader"]').append(createLoader('camadas', 44));

  const lista = el.querySelector('[data-pair="lista"]');
  const estado = el.querySelector('[data-pair="estado"]');

  /* O gatilho é o rádio, não um botão: assim que um controle aparece, o
     passo está cumprido e o fluxo anda. */
  const aoParear = (e) => {
    if (!e.detail.connected) return;
    estado.textContent = 'CONTROLE PAREADO';
    setTimeout(() => firstRun.avancar(), 700);
  };

  return { el, chrome: 'boot', onEnter, onLeave, onAction, unmount };

  function onEnter() {
    state.set('screenName', 'ENTRADA');
    state.set('bootStep', { n: 3, total: 4, label: 'CONTROLE' });
    state.set('hints', HINTS);
    state.set('context', 'BUSCA CONTÍNUA · BLUETOOTH 5.3');
    window.addEventListener('kyber:pad', aoParear);
    desenharDispositivos();
  }

  function onLeave() { window.removeEventListener('kyber:pad', aoParear); }
  function unmount() { onLeave(); }

  function onAction(action) {
    /* Ⓐ pula: quem só tem teclado precisa poder seguir. */
    if (action === 'a') { firstRun.avancar(); return true; }
    if (action === 'b') { firstRun.voltar(); return true; }
    return undefined;
  }

  function desenharDispositivos() {
    const achados = [
      { nome: 'Teclado do notebook', tipo: 'TECLADO · NÃO É CONTROLE', sinal: '−71 dBm' },
      ...bt.others.map((d) => ({ nome: d.name, tipo: `${d.kind} · NÃO É CONTROLE`, sinal: d.signal })),
    ];
    lista.innerHTML = achados.map((d) => `
      <div class="pair__achado">
        <div>
          <div class="pair__achado-nome">${escape(d.nome)}</div>
          <div class="pair__achado-tipo">${escape(d.tipo)}</div>
        </div>
        <div class="pair__achado-sinal">${escape(d.sinal)}</div>
      </div>`).join('');
  }
}

/* A combinação de pareamento é de cada fabricante. Sem controle detectado
   — que é o estado normal desta tela — não há como saber qual está na mão,
   então ela mostra as duas mais prováveis em vez de chutar uma. */
function instrucao(familia) {
  const mostra = familia ? [familia] : ['playstation', 'xbox'];
  return mostra.map((f) => {
    const { botoes, marca } = PAREAMENTO[f] ?? PAREAMENTO.generic;
    return `
      <div class="pair__combo">
        <span class="pair__marca">${marca}</span>
        <span class="pair__teclas">
          ${botoes.map((b, i) => `
            ${i ? '<span class="pair__mais">+</span>' : ''}
            <span class="pair__tecla">${b}</span>`).join('')}
        </span>
      </div>`;
  }).join('');
}

function template(familia) {
  const section = document.createElement('section');
  section.className = 'pair screen__page';
  section.innerHTML = `
    <div class="pair__instrucao">
      <div class="pair__kicker">PAREAMENTO</div>
      <!-- A instrução grande não pode contar botões: Xbox pareia com um
           só e PlayStation com dois. O que vale para todos é o sinal de
           que deu certo, e é isso que o display promete. -->
      <h1 class="pair__title">SEGURE ATÉ<br>A LUZ PISCAR</h1>

      ${instrucao(familia)}

      <p class="pair__desc">Três segundos bastam. O KYBER encontra qualquer controle Bluetooth padrão.</p>

      <div class="pair__alternativas">TAMBÉM ACEITA CABO USB-C<br>TECLADO E MOUSE FUNCIONAM COMO ALTERNATIVA</div>

      <!-- O rodapé promete "ENTER CONFIRMA", então precisa existir algo
           para confirmar. Sem este alvo o anel de foco não teria onde
           morar numa tela que, por definição, não tem controle. -->
      <div class="pair__acao" data-region="pair" data-region-flow="horizontal"
           data-region-dim="off">
        <div class="btn focusable" tabindex="0" role="button"
             data-pair="pular" data-focus-initial>CONTINUAR SEM CONTROLE</div>
      </div>
    </div>

    <div class="pair__radar">
      <div class="pair__radar-topo">
        <span class="pair__label" data-pair="estado">PROCURANDO CONTROLES</span>
        <span data-pair="loader"></span>
      </div>

      <div class="pair__desenho">
        <div class="pair__corpo"></div>
        <div class="pair__grip pair__grip--esq"></div>
        <div class="pair__grip pair__grip--dir"></div>
      </div>

      <div class="pair__label pair__label--lista">DISPOSITIVOS ENCONTRADOS</div>
      <div class="pair__lista" data-pair="lista"></div>

      <div class="pair__rodape">
        <span>BUSCA CONTÍNUA</span>
        <span>BLUETOOTH 5.3</span>
      </div>
    </div>`;
  return section;
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
