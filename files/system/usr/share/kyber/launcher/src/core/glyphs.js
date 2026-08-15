/* =====================================================================
   KYBER — glifos de botão por família de controle

   A FUNÇÃO NUNCA MUDA. O botão de baixo confirma, o da direita volta, o
   de cima e o da esquerda são as ações contextuais. O que muda é só a
   gravação: o mesmo botão de baixo se chama Ⓐ num Xbox, ✕ num DualSense
   e B num controle da Nintendo.

   Por isso o código inteiro fala em NOME DE FUNÇÃO — 'A', 'B', 'X', 'Y',
   'LB', 'RB', 'GUIDE' — e só este módulo sabe desenhar. Trocar de família
   não muda uma linha de comportamento em lugar nenhum.

   DECISÃO CONSCIENTE: não implementamos a inversão japonesa do
   PlayStation, onde ○ confirma e ✕ volta. O layout ocidental é o que a
   Sony padronizou globalmente a partir do PS5, o `mapping: 'standard'` do
   navegador entrega o botão de baixo no índice 0 em qualquer região, e
   ler a região do usuário para inverter função — não só desenho — seria o
   único lugar do sistema onde o mesmo botão faz coisas diferentes. Se um
   dia entrar, entra como preferência explícita em Configurações, nunca
   por detecção automática.
   ===================================================================== */

import { state } from './state.js';

/* Vendor ID vem dentro do próprio `gamepad.id` e é o sinal mais confiável:
   o DualShock 4 se anuncia como "Wireless Controller", sem marca nenhuma
   no nome, e só o vendor 054c o distingue de um genérico. */
const VENDORES = {
  '054c': 'playstation',   /* Sony */
  '045e': 'xbox',          /* Microsoft */
  '057e': 'nintendo',      /* Nintendo */
  '28de': 'xbox',          /* Valve — layout ABXY */
};

const PALAVRAS = [
  ['playstation', ['dualsense', 'dualshock', 'playstation', 'ps5', 'ps4', 'ps3', 'sony']],
  ['nintendo',    ['nintendo', 'switch', 'joy-con', 'joycon', 'pro controller']],
  ['xbox',        ['xbox', 'xinput', 'microsoft', 'xpadneo']],
];

/**
 * Família a partir do `gamepad.id`.
 *
 * Fallback é `xbox` porque é o layout que o "Standard Gamepad" do W3C
 * descreve: um controle desconhecido em modo padrão responde como Xbox,
 * então desenhar como Xbox é a suposição que erra menos.
 */
export function familiaDe(id) {
  const texto = String(id ?? '').toLowerCase();

  const vendor = texto.match(/vendor:\s*([0-9a-f]{4})/i)?.[1];
  if (vendor && VENDORES[vendor]) return VENDORES[vendor];

  for (const [familia, palavras] of PALAVRAS) {
    if (palavras.some((p) => texto.includes(p))) return familia;
  }
  return texto ? 'generic' : 'xbox';
}

/* `generic` desenha como xbox — é o mesmo layout do mapping standard. */
const XBOX = { A: 'Ⓐ', B: 'Ⓑ', X: 'Ⓧ', Y: 'Ⓨ', LB: 'LB', RB: 'RB', GUIDE: 'GUIDE' };

const GLIFOS = {
  xbox: XBOX,
  generic: XBOX,
  /* Posições, não letras: ✕ é o de baixo, ○ o da direita. */
  playstation: { A: '✕', B: '○', X: '□', Y: '△', LB: 'L1', RB: 'R1', GUIDE: 'PS' },
  /* Nintendo inverte os pares em relação ao Xbox: o de baixo se chama B e
     o da direita se chama A. A função continua a mesma. */
  nintendo: { A: 'B', B: 'A', X: 'Y', Y: 'X', LB: 'L', RB: 'R', GUIDE: 'HOME' },
};

/* Instrução de pareamento, específica de cada família. */
export const PAREAMENTO = {
  playstation: { botoes: ['PS', 'SHARE'], marca: 'PlayStation' },
  xbox:        { botoes: ['PAIR'],        marca: 'Xbox' },
  nintendo:    { botoes: ['SYNC'],        marca: 'Nintendo' },
  generic:     { botoes: ['PAIR'],        marca: 'genérico' },
};

export const NOME_FAMILIA = {
  xbox: 'XBOX', playstation: 'PLAYSTATION', nintendo: 'NINTENDO', generic: 'GENÉRICO',
};

/* Aceita o nome de função ou a própria gravação canônica do Xbox, para o
   código antigo que declarava `glyph: '≡'` continuar valendo. */
const CANONICO = { 'Ⓐ': 'A', 'Ⓑ': 'B', 'Ⓧ': 'X', 'Ⓨ': 'Y', '≡': 'GUIDE' };

/* =====================================================================
   DESENHO

   Caractere tipográfico não serve: ✕ de fonte é um "x" com serifa óptica
   de texto, ○ é um zero, e cada um ocupa uma caixa diferente. Numa linha
   de rodapé isso vira ritmo irregular — trocar de controle mexeria no
   espaçamento da tela inteira.

   Então todo glifo de face é desenhado, num mesmo viewBox de 24 e com a
   MESMA espessura de traço. O símbolo do PlayStation aparece nu, como a
   Sony imprime; o do Xbox e o da Nintendo aparecem dentro do anel, como
   a Microsoft e a Nintendo imprimem. O que iguala as duas famílias não é
   a forma, é a caixa óptica e o peso do traço.

   Os tamanhos abaixo não são iguais de propósito: quadrado e triângulo
   de mesma medida não pesam o mesmo que um círculo. Os valores estão
   corrigidos opticamente, que é o que faz a linha parecer regular.
   ===================================================================== */

/* Espessura em px de tela, não em unidade do viewBox: com
   `vector-effect: non-scaling-stroke` na folha, o traço fica idêntico
   à borda de 2px do retângulo de etiqueta em QUALQUER tamanho. É isso
   que faz símbolo e sigla pesarem o mesmo na linha do rodapé. */
const TRACO = 2;

const anel = (r = 9.4) => `<circle cx="12" cy="12" r="${r}"/>`;

/* Letra dentro do anel, no mesmo peso do traço. `central` alinha pelo
   meio da caixa da fonte; o dy corrige a diferença entre esse meio e o
   centro óptico da caixa alta. */
const letra = (ch) =>
  `<text x="12" y="12" dy="0.5" text-anchor="middle" dominant-baseline="central"
         class="glifo__letra">${ch}</text>`;

const DESENHOS = {
  /* PlayStation — símbolo nu, sem anel. */
  ps_cross:    `<path d="M4.8 4.8 L19.2 19.2 M19.2 4.8 L4.8 19.2"/>`,
  ps_circle:   `<circle cx="12" cy="12" r="8.8"/>`,
  ps_square:   `<rect x="4.3" y="4.3" width="15.4" height="15.4" rx="1.4"/>`,
  ps_triangle: `<path d="M12 2.3 L20.8 17.5 L3.2 17.5 Z"/>`,
};

/* Cada família devolve o desenho do botão de face. Ombro e Guide não são
   símbolo: são etiqueta, e continuam em retângulo com texto em mono. */
const FACE = {
  xbox:        { A: anel() + letra('A'), B: anel() + letra('B'),
                 X: anel() + letra('X'), Y: anel() + letra('Y') },
  playstation: { A: DESENHOS.ps_cross,  B: DESENHOS.ps_circle,
                 X: DESENHOS.ps_square, Y: DESENHOS.ps_triangle },
  nintendo:    { A: anel() + letra('B'), B: anel() + letra('A'),
                 X: anel() + letra('Y'), Y: anel() + letra('X') },
};
FACE.generic = FACE.xbox;

/** Botão de face é símbolo desenhado; ombro e Guide são etiqueta. */
export const ehFace = (nome) =>
  ['A', 'B', 'X', 'Y'].includes(CANONICO[nome] ?? String(nome).toUpperCase());

/* Retângulo com texto em mono — a mesma caixa da tecla de teclado
   (ENTER, ESC), para que PS, GUIDE, HOME, L1 e LB caiam todos no mesmo
   ritmo do rodapé. */
export const etiquetaHTML = (texto) =>
  `<span class="glifo glifo--etiqueta">${texto}</span>`;

/** Marcação do glifo: SVG desenhado nas faces, etiqueta nas demais. */
export function glifoMarkup(nome) {
  const chave = CANONICO[nome] ?? String(nome).toUpperCase();
  if (!ehFace(chave)) return etiquetaHTML(glifo(chave));
  const desenho = (FACE[familiaAtual()] ?? FACE.xbox)[chave];
  return `<svg class="glifo glifo--face" viewBox="0 0 24 24" aria-hidden="true"
               stroke-width="${TRACO}">${desenho}</svg>`;
}

export const familiaAtual = () => state.get('padFamily') ?? 'xbox';

/** Gravação de um botão na família em uso. */
export function glifo(nome) {
  const chave = CANONICO[nome] ?? String(nome).toUpperCase();
  return (GLIFOS[familiaAtual()] ?? XBOX)[chave] ?? nome;
}

/** Gravação para embutir em HTML, que se atualiza sozinha ao trocar de
    família — sem isso uma tela aberta ficaria gravando o controle antigo. */
export function glifoHTML(nome) {
  const chave = CANONICO[nome] ?? String(nome).toUpperCase();
  return `<span class="glifo-slot" data-glifo="${chave}" role="img"
                aria-label="botão ${glifo(chave)}">${glifoMarkup(chave)}</span>`;
}

/** Elemento pronto, para quem monta DOM em vez de string. */
export function createGlyph(nome) {
  const host = document.createElement('span');
  host.className = 'glifo-slot';
  host.dataset.glifo = CANONICO[nome] ?? String(nome).toUpperCase();
  host.setAttribute('role', 'img');
  host.setAttribute('aria-label', `botão ${glifo(nome)}`);
  host.innerHTML = glifoMarkup(nome);
  return host;
}

/** Repinta toda gravação viva no documento. */
function repintar() {
  for (const el of document.querySelectorAll('[data-glifo]')) {
    el.innerHTML = glifoMarkup(el.dataset.glifo);
    el.setAttribute('aria-label', `botão ${glifo(el.dataset.glifo)}`);
  }
}

state.subscribe('padFamily', repintar);
