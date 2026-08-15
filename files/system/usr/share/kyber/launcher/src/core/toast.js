/* =====================================================================
   KYBER — tela 15 · Toasts

   Toast NÃO é tela e NÃO é overlay de foco: aparece por cima, informa e
   sai sozinho, sem nunca roubar o foco de onde a pessoa está. Por isso
   não passa pelo router — quem entra na pilha é o que prende o foco.

   TOAST NUNCA CAPTURA Ⓐ NEM Ⓨ. O mapa de navegação original mandava o
   contrário ("Ⓐ ou Ⓨ agem no toast do topo") e a auditoria de UX matou
   a regra: com um toast vivo, o Ⓐ deixava de abrir o jogo em foco sem
   nada avisar que o botão tinha trocado de dono. O caminho de 2 inputs
   até jogar virava 3, e levava a uma tela que ninguém pediu. Ⓐ e Ⓨ são
   da tela, sempre.

   Quando o toast tem ação, ela mora no RB e está ESCRITA dentro do
   próprio toast. Capturar um botão é aceitável quando está anunciado no
   mesmo lugar em que a pessoa está olhando; o pecado era o silêncio.
   Toast sem ação declarada não captura nada.

   UM VISÍVEL POR VEZ. Dois toasts abaixo do outro empilham informação
   que ninguém lê a 3 m e ainda tapam a tela. Os demais esperam a vez e
   viram contador no canto — a conta é honesta, nada se perde em
   silêncio.

   SUPERFÍCIE OPACA. Era vidro, e vidro só vale onde nós desenhamos o
   fundo — o toast é justamente a superfície que não escolhe o que fica
   atrás dela. Sobre capa de jogo o rótulo só passava 4,5:1 a partir de
   alpha .84, e a .84 já não é vidro. Opaco em toda parte, inclusive
   sobre o void: duas aparências para a mesma função seriam pior.
   ===================================================================== */

import { glifoHTML } from './glyphs.js';

const TOP = 170;          /* header 76 + régua 78 + folga 16 */
const DEFAULT_MS = 6000;  /* dispensa sozinho; ninguém precisa fechar */

let layer = null;
let contadorEl = null;
let vivo = null;          /* { node, timer, acao } — o único visível */
const fila = [];          /* os que esperam a vez */

function ensureLayer() {
  if (layer?.isConnected) return layer;
  layer = document.createElement('div');
  layer.className = 'toasts';
  layer.style.top = `${TOP}px`;
  contadorEl = document.createElement('div');
  contadorEl.className = 'toasts__count';
  contadorEl.hidden = true;
  layer.append(contadorEl);
  document.getElementById('app').append(layer);
  return layer;
}

function pintarContador() {
  if (!contadorEl) return;
  contadorEl.hidden = fila.length === 0;
  contadorEl.textContent = `+${fila.length}`;
}

/**
 * @param {object}  t
 * @param {string}  t.title  rótulo em mono caixa alta
 * @param {string}  t.body   uma frase, matéria de fato
 * @param {'info'|'device'|'error'} t.kind
 * @param {number} [t.ms]
 * @param {{ label: string, run: () => void }} [t.acao]
 *        ação opcional, gravada no RB e escrita dentro do toast
 *
 * `error` é o único que gasta cor: o quadrado em `state-hot` é um dos
 * usos adicionais que a identidade autoriza. Os outros dois são
 * acromáticos de propósito.
 *
 * @returns {() => void} dispensa este toast, esteja ele visível ou na fila
 */
export function toast(spec) {
  ensureLayer();
  const item = { ...spec, ms: spec.ms ?? DEFAULT_MS };

  if (vivo) {
    fila.push(item);
    pintarContador();
    return () => {
      const i = fila.indexOf(item);
      if (i >= 0) { fila.splice(i, 1); pintarContador(); }
    };
  }

  mostrar(item);
  return () => { if (vivo?.item === item) dispensar(); };
}

function mostrar(item) {
  const { title, body, kind = 'info', ms, acao } = item;

  const node = document.createElement('div');
  node.className = `toast toast--${kind}`;
  node.setAttribute('role', 'status');
  node.innerHTML = `
    <div class="toast__row">
      <span class="toast__mark"></span>
      <div class="toast__text">
        <div class="toast__title"></div>
        <div class="toast__body"></div>
      </div>
      ${acao ? `<span class="toast__acao">${glifoHTML('RB')} <span data-toast="acao"></span></span>` : ''}
    </div>
    <div class="toast__track"><div class="toast__bar"></div></div>`;

  node.querySelector('.toast__title').textContent = title;
  node.querySelector('.toast__body').textContent = body;
  if (acao) node.querySelector('[data-toast="acao"]').textContent = acao.label;

  /* O contador vive no fim da camada, então o toast entra ANTES dele:
     a conta é subordinada ao aviso, e lê-se depois. */
  layer.insertBefore(node, contadorEl);

  /* A barra conta o tempo que resta — é informação, não enfeite. */
  const bar = node.querySelector('.toast__bar');
  bar.style.transition = `width ${ms}ms linear`;
  requestAnimationFrame(() => { bar.style.width = '0%'; });

  vivo = { item, node, acao, timer: setTimeout(dispensar, ms) };
  pintarContador();
}

function dispensar() {
  if (!vivo) return;
  clearTimeout(vivo.timer);
  vivo.node.remove();
  vivo = null;
  const proximo = fila.shift();
  pintarContador();
  if (proximo) mostrar(proximo);
}

/**
 * RB no toast visível. Devolve true se consumiu o botão — o main só
 * chama isto para 'rb', e só um toast que DECLAROU ação responde.
 * Sem ação declarada, o botão segue para a tela, como Ⓐ e Ⓨ sempre
 * seguem.
 */
export function toastAction(action) {
  if (action !== 'rb' || !vivo?.acao) return false;
  const { run } = vivo.acao;
  dispensar();
  run();
  return true;
}

export function clearToasts() {
  if (vivo) { clearTimeout(vivo.timer); vivo.node.remove(); vivo = null; }
  fila.length = 0;
  pintarContador();
}
