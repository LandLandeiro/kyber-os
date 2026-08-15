/* =====================================================================
   KYBER — chrome
   Liga o chrome (header, régua, rodapé) ao state. Nenhuma tela escreve
   no chrome diretamente: escreve no state, e o chrome reage.
   ===================================================================== */

import { state } from './state.js';
import { glifoMarkup, etiquetaHTML, ehFace } from './glyphs.js';

const app = document.getElementById('app');
const el = {};
for (const node of document.querySelectorAll('[data-chrome]')) {
  el[node.dataset.chrome] = node;
}

/* ---------------------------------------------------------------------
   Escala — o documento é sempre 1920×1080; a janela é que se adapta.
   Nunca por media query de font-size: a escala tipográfica é absoluta.
   --------------------------------------------------------------------- */
const BASE_W = 1920;
const BASE_H = 1080;

function fit() {
  const scale = Math.min(innerWidth / BASE_W, innerHeight / BASE_H);
  app.style.setProperty('--app-scale', scale);
  // Deslocamento aplicado antes da escala, portanto já em px de tela.
  app.style.setProperty('--app-x', `${(innerWidth  - BASE_W * scale) / 2}px`);
  app.style.setProperty('--app-y', `${(innerHeight - BASE_H * scale) / 2}px`);
}

addEventListener('resize', fit);
fit();

/* ---------------------------------------------------------------------
   Régua ESTADO DA MÁQUINA.

   Duas fontes descrevem a régua, e a precedência entre elas é o que
   separa medição de palpite:

     MEDIÇÃO   `intensity` + `watts` — o que a máquina está fazendo.
               Manda sempre que há jogo em execução.
     PREVISÃO  `preview` — o que a máquina faria com o título em foco.
               Só vale com a sessão vazia, e o rótulo diz que é previsão.

   `profile` continua sendo o nível da máquina para quem consome fora da
   régua (ficha, editor). O nível que a régua PINTA sai da intensidade
   efetiva, não desta chave — senão previsão e medição brigariam pela
   mesma variável.

   Os limiares (2/8 e 5/8) e a escala 0..8 são o modelo de perfil do
   protótipo da Etapa 1, não números escolhidos aqui.
   --------------------------------------------------------------------- */
const PROFILES = {
  quiet:   'SILENCIOSO',
  nominal: 'EQUILIBRADO',
  hot:     'AGRESSIVO',
};

const GAUGE_LABEL = {
  measured: 'ESTADO DA MÁQUINA',
  preview:  'ESTADO DA MÁQUINA · PREVISTO',
  forced:   'ESTADO DA MÁQUINA · SIMULADO',
};

/* O foco assenta antes de a régua reagir. O D-pad repete a cada 110ms e o
   cursor leva 320ms para chegar: sem esta espera ele nunca chega ao
   destino e a única coisa que se move sozinha no sistema vira tremor
   contínuo enquanto se varre a prateleira. Varrendo rápido, a régua fica
   parada; parando num título, ela desliza uma vez. */
const SETTLE_MS = 200;

/* Posição assumida quando se pede um nível sem dizer a intensidade. */
const DEFAULT_INTENSITY = { quiet: .14, nominal: .50, hot: .86 };

// Tolera o nome por extenso digitado no console.
const ALIASES = {
  SILENCIOSO: 'quiet', EQUILIBRADO: 'nominal', AGRESSIVO: 'hot',
};

function normalizeProfile(value) {
  const key = String(value ?? '');
  if (key in PROFILES) return key;
  return ALIASES[key.toUpperCase()] ?? 'nominal';
}

const levelOf = (i) => (i <= 2 / 8 ? 'quiet' : i <= 5 / 8 ? 'nominal' : 'hot');
const clamp = (i) => Math.min(1, Math.max(0, i));

function resolveGauge() {
  const preview = state.get('preview');

  /* Jogo vivo tem precedência: com a sessão rodando, a régua é medição do
     que está acontecendo, não palpite sobre o que está em foco.

     `preview.force` é a exceção, e existe para o editor de perfil: ali o
     usuário está montando um cenário e pediu para ver o que aconteceria.
     Simular tem precedência sobre medir quando a simulação foi pedida. */
  const predicting = Boolean(preview) && (preview.force || !state.get('runningGame'));

  const intensity = predicting ? preview.intensity : state.get('intensity');
  const watts     = predicting ? preview.watts     : state.get('watts');

  /* Antes de o estado da máquina chegar não há o que desenhar — melhor a
     régua ficar como está do que apontar para um valor inventado. */
  if (typeof intensity !== 'number') return;

  const i = clamp(intensity);
  const level = levelOf(i);

  el.gauge.style.setProperty('--gauge-pos', `${(i * 100).toFixed(2)}%`);
  el.gauge.dataset.profile = level;
  el.profileName.textContent = PROFILES[level];
  el.gaugeLabel.textContent = GAUGE_LABEL[
    !predicting ? 'measured' : preview.force ? 'forced' : 'preview'
  ];
  if (typeof watts === 'number') el.watts.textContent = `${watts} W`;

  /* A primeira resolução entra sem transição: deslizar de um valor de
     marcação estática para o valor real seria movimento que não ensina
     nada. Da segunda em diante o cursor anima. */
  el.gauge.dataset.ready = 'true';
}

let settleTimer = 0;
let previewing = false;

state.subscribe('preview', (value) => {
  clearTimeout(settleTimer);

  /* Limpar a previsão (troca de tela) e a PRIMEIRA previsão entram na
     hora: não há tremor a suprimir antes de existir um destino anterior. */
  if (!value || !previewing) {
    previewing = Boolean(value);
    resolveGauge();
    return;
  }
  settleTimer = setTimeout(resolveGauge, SETTLE_MS);
});

state.subscribe('intensity', (value) => {
  state.set('profile', levelOf(clamp(Number(value) || 0)));
  resolveGauge();
});

state.subscribe('watts', resolveGauge);

/* `profile` e `intensity` descrevem a mesma coisa em resoluções
   diferentes; escrever qualquer uma pelo console move a régua. */
state.subscribe('profile', (value) => {
  const profile = normalizeProfile(value);
  const i = state.get('intensity');
  if (typeof i !== 'number' || levelOf(i) !== profile) {
    state.set('intensity', DEFAULT_INTENSITY[profile]);
  }
});

/* ---------------------------------------------------------------------
   Header — telemetria, jogo vivo e hora.
   --------------------------------------------------------------------- */
state.subscribe('cpuTemp', (t) => { el.cpu.textContent = `CPU ${t} °C`; });
state.subscribe('gpuTemp', (t) => { el.gpu.textContent = `GPU ${t} °C`; });

state.subscribe('controllers', (n) => {
  el.controllers.textContent = n > 0 ? `CONTROLE ${n}` : 'SEM CONTROLE';
  /* Conectar ou desconectar troca a gravação de todo o rodapé. */
  renderHints();
});

/* Trocar de família repinta o rodapé sem recarregar nada. */
state.subscribe('padFamily', renderHints);

/* Indicador de jogo vivo: SÓ o ponto é âmbar. O nome do jogo é text-mid —
   status permanente não consome orçamento de cor. Ausente sem jogo. */
state.subscribe('runningGame', (game) => {
  const live = Boolean(game);
  el.live.hidden = !live;
  el.liveRule.hidden = !live;
  if (live) el.liveName.textContent = game.name.toUpperCase();

  /* Começar ou encerrar sessão troca o regime da régua na hora — uma
     previsão a caminho não pode chegar depois e sobrescrever a medição. */
  clearTimeout(settleTimer);
  resolveGauge();
});

/* Modo de chrome — quem manda é a tela, via router. */
state.subscribe('chromeMode', (mode) => {
  app.dataset.chromeMode = mode ?? 'full';
});

/* Medidor de passo: barras preenchidas até o passo atual + rótulo. */
state.subscribe('bootStep', (passo) => {
  if (!passo) {
    el.stepBars.replaceChildren();
    el.stepLabel.textContent = '';
    return;
  }
  const { n, total, label } = passo;
  el.stepBars.replaceChildren(
    ...Array.from({ length: total }, (_, i) => {
      const barra = document.createElement('span');
      if (i < n) barra.dataset.done = 'true';
      return barra;
    })
  );
  el.stepLabel.textContent = `PASSO ${n} DE ${total} · ${label}`;
});

state.subscribe('screenName', (name) => {
  el.screenName.textContent = String(name).toUpperCase();
});

const clock = new Intl.DateTimeFormat('pt-BR', {
  hour: '2-digit', minute: '2-digit', hour12: false,
});

function tick() {
  const now = new Date();
  el.clock.textContent = clock.format(now);
  // Re-agenda na virada do minuto, não a cada segundo.
  setTimeout(tick, (60 - now.getSeconds()) * 1000 + 50);
}
tick();

/* ---------------------------------------------------------------------
   Rodapé — contextual por tela. A tela declara o que seus botões fazem;
   o chrome só desenha.

   E desenha o que existe na mão da pessoa: com controle conectado, a
   gravação do botão físico (círculo nas quatro faces, retângulo no que
   tem mais de uma letra). Sem controle, a tecla equivalente — teclado e
   controle são cidadãos de igual peso, e um rodapé gravando Ⓐ para quem
   só tem teclado é uma legenda mentindo.
   --------------------------------------------------------------------- */
const KEYBOARD = {
  A: 'ENTER', B: 'ESC', X: 'F', Y: 'E',
  GUIDE: 'TAB', LB: 'Q', RB: 'W',
};

let currentHints = [];

function renderHints() {
  const semControle = (state.get('controllers') ?? 0) === 0;

  el.hints.replaceChildren(
    ...currentHints.map(({ glyph, label, key, disabled }) => {
      const node = document.createElement('div');
      node.className = 'hint';
      if (disabled) node.dataset.disabled = 'true';

      /* `key` deixa a tela sobrescrever a tecla quando a equivalência
         não é direta — segurar o Guide é SHIFT+TAB, não TAB. */
      /* Com controle na mão, a gravação é a da família detectada: o
         rodapé não pode pedir um botão que não existe no aparelho. */
      /* Símbolo desenhado é gravação de botão de face do controle.
         Tecla de teclado é retângulo, tenha uma letra ou cinco —
         desenhar F dentro de um anel faria a legenda parecer um botão
         que não existe no aparelho. Ombro e Guide também são etiqueta:
         L1 e PS não têm símbolo, e forçá-los num anel quebraria o
         alinhamento da linha ao trocar de família. */
      const g = document.createElement('span');
      g.className = 'hint__glyph';
      g.innerHTML = semControle
        ? etiquetaHTML(key ?? KEYBOARD[glyph] ?? glyph)
        : glifoMarkup(glyph);
      if (!semControle && ehFace(glyph)) g.dataset.face = 'true';

      const l = document.createElement('span');
      l.className = 'hint__label';
      l.textContent = label;

      node.append(g, l);
      return node;
    })
  );
}

state.subscribe('hints', (hints) => {
  currentHints = hints ?? [];
  renderHints();
});

/* Aceita texto puro (contexto técnico permanente) ou { text, alert },
   usado pelos stubs para anunciar o que ainda não existe. */
state.subscribe('context', (value) => {
  const { text, alert } = typeof value === 'string' ? { text: value } : value ?? {};
  el.context.textContent = text ?? '';
  el.context.dataset.alert = alert ? 'true' : 'false';
});
