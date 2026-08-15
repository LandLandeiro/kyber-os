/* =====================================================================
   KYBER — tela 12 · Menu de energia

   Overlay aberto por SEGURAR o Guide. Lista vertical por inversão de
   linha, sem régua própria: a de baixo continua lá, atrás do scrim.

   Cada opção destrutiva nomeia o que vai encerrar. "encerra Hollow Tide
   e corta a energia" é diferente de "desligar" — a primeira diz a
   consequência, a segunda pede confiança.

   DESTRUTIVO NUNCA RECEBE FOCO INICIAL. O menu abria com DESLIGAR sob o
   cursor: com um jogo vivo, isso são dois inputs entre "jogando" e
   "sessão morta" — segurar o Guide e o polegar caindo no Ⓐ por reflexo,
   sem nada lido no meio. O foco entra em SUSPENDER, que é a ação
   reversível e a mais provável, e as três que cortam a energia pedem
   pressão de 2 s, a mesma da tela 10. É o padrão que a 17b já executa.

   CANCELAR saiu da lista. Ⓑ já fecha o menu, está gravado no rodapé do
   modal, e uma linha a mais só aumenta o custo de escolha de todas as
   outras.
   ===================================================================== */

import { state } from '../core/state.js';
import { glifoHTML } from '../core/glyphs.js';
import { DataAdapter } from '../data/adapter.js';
import { relogio } from './running.js';
import { criarSegurar, pintarBarra, SEGURAR_MS } from '../components/hold.js';

/* O micro-rótulo muda conforme exista sessão: sem jogo vivo não há o que
   encerrar, e prometer que encerra seria mentira.

   `destrutivo` marca o que corta a energia sem volta — fio âmbar na
   aresta esquerda e pressão de 2 s. MODO DESKTOP encerra a sessão mas
   não desliga nada: dá para voltar, então não leva o fio. */
const OPTIONS = [
  { id: 'poweroff', label: 'DESLIGAR', destrutivo: true,
    hint: (j) => (j ? `encerra ${j} e corta a energia` : 'corta a energia') },
  { id: 'reboot', label: 'REINICIAR', destrutivo: true,
    hint: (j) => (j ? `encerra ${j} e reinicia o sistema` : 'reinicia o sistema') },
  { id: 'suspend', label: 'SUSPENDER', inicial: true,
    hint: (j) => (j ? 'mantém a partida na memória · retoma em 2 s' : 'mantém o estado na memória · retoma em 2 s') },
  { id: 'windows', label: 'REINICIAR NO WINDOWS', destrutivo: true,
    hint: () => 'para jogos com anticheat · R6, Valorant' },
  { id: 'desktop', label: 'MODO DESKTOP',
    hint: (j) => (j ? `encerra ${j} e sai para o ambiente gráfico` : 'sai para o ambiente gráfico') },
];

const ehDestrutivo = (id) => !!OPTIONS.find((o) => o.id === id)?.destrutivo;

export async function createPower({ router }) {
  const settings = await DataAdapter.settings();
  const live = state.get('runningGame');

  const el = template(settings, live);
  const clockEl = el.querySelector('[data-power="clock"]');
  const hintEl = el.querySelector('[data-power="hint"]');

  const doisSeg = (SEGURAR_MS / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 1 });

  /* A gravação do rodapé é contextual: só pede pressão quando o foco
     está sobre uma linha que exige pressão. Anunciar as duas regras o
     tempo todo faria a linha vazar do painel e ensinaria menos. */
  const hintBase = () => {
    const id = document.activeElement?.closest?.('[data-power]')?.dataset?.power;
    return ehDestrutivo(id)
      ? `SEGURE ${glifoHTML('A')} POR ${doisSeg} s · ${glifoHTML('B')} FECHAR`
      : `${glifoHTML('A')} CONFIRMAR · ${glifoHTML('B')} FECHAR`;
  };

  const repintarHint = () => {
    if (hintEl.dataset.alert === 'true') return;   /* anúncio tem a vez */
    hintEl.innerHTML = hintBase();
  };

  let timer = 0;
  let noticeTimer = 0;
  let alvoSegurando = null;   /* linha que está sob pressão agora */

  /* Mesma mecânica da tela 10 — o que muda é só a caixa que ela pinta. */
  const segurar = criarSegurar({
    onProgresso: (t) => pintarBarra(alvoSegurando, t),
    onConcluir: () => { const id = alvoSegurando?.dataset?.power; pararSegurar(); executar(id); },
  });

  /* A descida e a subida de Ⓐ, que `kyber:action` sozinho não distingue. */
  const onPress = (e) => {
    const { action, down } = e.detail;
    if (action !== 'a') return;
    const row = document.activeElement?.closest?.('[data-power]');
    if (!row || !ehDestrutivo(row.dataset.power)) return;
    if (down) iniciarSegurar(row);
    else pararSegurar();
  };

  /* `power: true` evita que segurar o Guide empilhe um menu sobre o
     outro — o gesto é o mesmo e a repetição do Gamepad é agressiva. */
  return { el, overlay: true, power: true, onEnter, onLeave, onAction, unmount };

  function onEnter() {
    window.addEventListener('kyber:press', onPress);
    el.addEventListener('kyber:focus', aoMoverFoco);
    repintarHint();
    if (!live) return;
    const paint = () => {
      const atual = state.get('runningGame');
      if (atual) clockEl.textContent = `SESSÃO ATIVA ${relogio(Date.now() - atual.startedAt)}`;
    };
    paint();
    timer = setInterval(paint, 1000);
  }

  function onLeave() {
    clearInterval(timer);
    clearTimeout(noticeTimer);
    pararSegurar();
    window.removeEventListener('kyber:press', onPress);
    el.removeEventListener('kyber:focus', aoMoverFoco);
  }

  function unmount() { onLeave(); }

  /* ---------- segurar Ⓐ ---------- */

  function aoMoverFoco() {
    /* Sair de uma linha sob pressão cancela: a conta não corre atrás de
       um alvo que não está mais em foco. */
    pararSegurar();
    repintarHint();
  }

  function iniciarSegurar(row) {
    alvoSegurando = row;
    row.dataset.holding = 'true';
    segurar.iniciar();
  }

  function pararSegurar() {
    segurar.cancelar();
    if (alvoSegurando) {
      pintarBarra(alvoSegurando, 0);
      delete alvoSegurando.dataset.holding;
    }
    alvoSegurando = null;
  }

  /* ---------- ações ---------- */

  function onAction(action) {
    if (action !== 'a') return;
    const row = document.activeElement?.closest?.('[data-power]');
    if (!row) return;
    /* Linha destrutiva não responde ao toque: quem manda nela é o tempo
       de pressão, medido em kyber:press. */
    if (ehDestrutivo(row.dataset.power)) return;
    executar(row.dataset.power);
  }

  /* Nenhuma destas ações existe ainda. Anunciar no próprio modal, e não
     no rodapé do chrome, porque o rodapé está atrás do scrim. */
  function executar(id) {
    const opcao = OPTIONS.find((o) => o.id === id);
    if (!opcao) return;
    hintEl.textContent = `${opcao.label} · NÃO IMPLEMENTADO`;
    hintEl.dataset.alert = 'true';
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => {
      hintEl.dataset.alert = 'false';
      repintarHint();
    }, 2400);
  }
}

function template(settings, live) {
  const root = document.createElement('div');
  root.className = 'power glass-scrim';

  const nome = live?.name ?? null;
  const doisSeg = (SEGURAR_MS / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 1 });

  /* A face é desenhada duas vezes nas linhas destrutivas: a de cima é
     recortada pelo avanço da pressão, para o texto inverter junto com o
     preenchimento em vez de sumir dentro dele. */
  const face = (opt, hint, over) => `
    <span class="power__face${over ? ' power__face--over' : ''}"
          ${over ? 'data-hold="clip" data-hold-over' : ''}>
      <span class="power__mark"></span>
      <span class="power__text">
        <span class="power__label">${opt.label}</span>
        ${hint ? `<span class="power__hint">
          <span data-power="hintbase">${hint}</span>
          <span class="power__count" data-power="count">
            <span data-hold="elapsed">0,0 s DE ${doisSeg} s</span> · SOLTE PARA CANCELAR
          </span>
        </span>` : ''}
      </span>
    </span>`;

  const linha = (opt) => {
    const hint = opt.hint(nome);
    return `
      <div class="power__row row-invert" tabindex="0" role="button"
           data-power="${opt.id}"
           ${opt.destrutivo ? 'data-destructive="true"' : ''}
           ${opt.inicial ? 'data-focus-initial' : ''}
           aria-label="${opt.label}${opt.destrutivo ? ` — segure ${doisSeg} segundos` : ''}">
        ${opt.destrutivo ? '<span class="power__fill" data-hold="fill"></span>' : ''}
        ${face(opt, hint, false)}
        ${opt.destrutivo ? face(opt, hint, true) : ''}
      </div>`;
  };

  root.innerHTML = `
    <div class="power__panel glass-overlay">
      <div class="power__head">
        <span class="power__kicker">ENERGIA</span>
        <span class="power__build">${settings.build}</span>
      </div>

      <div class="power__list" data-region="power" data-region-flow="vertical"
           data-region-dim="off">
        ${OPTIONS.map(linha).join('')}
      </div>

      <div class="power__foot">
        <span data-power="hint" data-alert="false">${glifoHTML('A')} CONFIRMAR · ${glifoHTML('B')} FECHAR</span>
        <span data-power="clock">${live ? 'SESSÃO ATIVA 00:00:00' : 'SEM SESSÃO ATIVA'}</span>
      </div>
    </div>`;
  return root;
}
