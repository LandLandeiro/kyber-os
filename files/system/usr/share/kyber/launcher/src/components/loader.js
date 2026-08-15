/* =====================================================================
   KYBER — indicador de carregamento

   Três variantes, uma por tipo de espera, conforme a folha de uso da
   marca (docs/KYBER - marca.md):

     subida    1,6 s  acende de baixo, mantém, sai por cima
                      → boot e transições curtas
     varredura 1,4 s  leito permanente a 22 %, pulso curto subindo
                      → espera longa: download, verificação, aprovação
     camadas   1,8 s  a luz sobe e cada zona acende ao ser atravessada
                      → tela dedicada, com o símbolo grande

   POR QUE A GEOMETRIA ESTÁ AQUI E NÃO NUM <img>

   Os três SVGs entregues em src/assets/logo/ trazem o desenho mas NÃO
   trazem movimento: cada um tem um vão vazio onde deveriam estar os
   elementos <animate>. Um <img> não pode ser animado de fora, então a
   geometria vem inline e o movimento é CSS, escrito a partir da tabela
   da folha (durações, comportamento e curvas). Quando os SVGs vierem
   animados, este componente pode virar um <img> e as regras de
   `loader.css` somem junto.

   A fenda é sempre `state-hot` — a folha proíbe trocar a cor dela, e é o
   mesmo sinal da régua de estado.
   ===================================================================== */

const CORPO  = '44,0 88,24 88,72 44,96 0,72 0,24';
const ZONA_2 = '44,10.6 78.3,29.3 78.3,66.7 44,85.4 9.7,66.7 9.7,29.3';
const ZONA_3 = '44,23 66.9,35.5 66.9,60.5 44,73 21.1,60.5 21.1,35.5';

/* TRÊS OTIMIZAÇÕES, NÃO UM VETOR REDUZIDO.

   Cada faixa de tamanho é um desenho próprio, copiado do arquivo
   correspondente em src/assets/logo/. Reduzir o de 88 produz mingau de
   cinzas — a folha é explícita, e é por isso que a escolha é por
   largura, não por escala. */
const OTIMIZACOES = {
  /* kyber-simbolo-88.svg · 3 zonas · canal 16 · luz 8 · 40px e acima */
  88: { zonas: [CORPO, ZONA_2, ZONA_3], canal: [36, 16], luz: [40, 8] },
  /* kyber-simbolo-48.svg · 2 zonas · canal 18 · luz 9 · 32 a 40px */
  48: { zonas: [CORPO, ZONA_3], canal: [35, 18], luz: [39.5, 9] },
  /* kyber-simbolo-24.svg · 1 zona · canal 26 · luz 13 · abaixo de 32px */
  24: { zonas: [ZONA_3], canal: [31, 26], luz: [37.5, 13] },
};

const MINIMO = 20;   /* abaixo disto a fenda fecha e sobra um hexágono */

const otimizacaoPara = (size) => (size >= 40 ? 88 : size >= 32 ? 48 : 24);

let contador = 0;

/**
 * @param {'subida'|'varredura'|'camadas'} variante
 * @param {number} size  largura em px; escolhe a otimização sozinha.
 */
export function createLoader(variante = 'varredura', size = 88) {
  if (size < MINIMO) {
    throw new Error(`símbolo abaixo do mínimo de ${MINIMO}px (pedido: ${size}px)`);
  }
  const o = OTIMIZACOES[otimizacaoPara(size)];
  const id = `kl${++contador}`;
  const el = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  el.setAttribute('class', `loader loader--${variante}`);
  el.setAttribute('viewBox', '0 0 88 96');
  el.setAttribute('width', String(size));
  el.setAttribute('height', String(Math.round((size * 96) / 88)));
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', 'carregando');

  el.innerHTML = `
    <defs>
      <clipPath id="${id}"><polygon points="${CORPO}"/></clipPath>
      <clipPath id="${id}s"><rect x="${o.luz[0]}" y="0" width="${o.luz[1]}" height="96"/></clipPath>
      <linearGradient id="${id}p" x1="0" y1="1" x2="0" y2="0">
        <stop offset="0"    class="loader__stop" stop-opacity="0"/>
        <stop offset="0.55" class="loader__stop" stop-opacity="1"/>
        <stop offset="1"    class="loader__stop" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <g clip-path="url(#${id})">
      ${o.zonas.map((pts, i) => `
        <polygon class="loader__zona loader__zona--${o.zonas.length - i}" points="${pts}"/>`).join('')}
      <rect class="loader__canal" x="${o.canal[0]}" y="0" width="${o.canal[1]}" height="96"/>
      <g clip-path="url(#${id}s)">
        <rect class="loader__leito" x="${o.luz[0]}" y="0" width="${o.luz[1]}" height="96"/>
        <rect class="loader__luz" x="${o.luz[0]}" y="0" width="${o.luz[1]}" height="96"
              fill="${variante === 'varredura' ? `url(#${id}p)` : 'currentColor'}"/>
      </g>
    </g>`;
  return el;
}
