/* =====================================================================
   KYBER — capa gerada

   Usada quando o título não tem arte na loja (atalho local, CDN fora do
   ar, primeira execução sem rede). Padrão geométrico monocromático
   derivado do título, exatamente como manda a identidade visual:
   inicial em display a 13% de opacidade, número de catálogo em mono a 50%.

   SVG inline, sem imagem externa: o console precisa abrir a biblioteca
   com o cabo de rede na mão.

   Nenhuma cor literal — o padrão pinta por classe, e as classes vivem em
   `library.css` sobre variáveis de `tokens.css`.
   ===================================================================== */

/** Hash estável do appid. Mesmo título → sempre o mesmo padrão. */
function hash(appid) {
  let h = 2166136261;
  for (const ch of String(appid)) {
    h ^= ch.charCodeAt(0);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

const PATTERNS = ['stripes', 'mesh', 'dots', 'rings', 'bands'];
const GROUNDS = ['panel', 'surface-1', 'surface-2'];

/* Geometria de cada padrão, em unidades do viewBox. Os padrões que
   ladrilham vão em <pattern>; os anéis são concêntricos e não ladrilham,
   então são desenhados um a um. */
function patternDefs(kind, id, w, h) {
  switch (kind) {
    case 'stripes':
      return `<pattern id="${id}" width="20" height="20" patternUnits="userSpaceOnUse">
                <rect class="cover__ink" width="3" height="20" opacity=".11"/>
              </pattern>`;
    case 'mesh':
      return `<pattern id="${id}" width="34" height="34" patternUnits="userSpaceOnUse">
                <rect class="cover__ink" width="34" height="1" opacity=".07"/>
                <rect class="cover__ink" width="1" height="34" opacity=".07"/>
              </pattern>`;
    case 'dots':
      return `<pattern id="${id}" width="24" height="24" patternUnits="userSpaceOnUse">
                <circle class="cover__ink" cx="12" cy="12" r="2.5" opacity=".18"/>
              </pattern>`;
    case 'bands':
      return `<pattern id="${id}" width="96" height="96" patternUnits="userSpaceOnUse">
                <rect class="cover__ink" width="48" height="96" opacity=".06"/>
              </pattern>`;
    case 'rings': {
      const cx = w * 0.5;
      const cy = h * 0.4;
      const max = Math.hypot(Math.max(cx, w - cx), Math.max(cy, h - cy));
      let rings = '';
      for (let r = 26; r < max; r += 26) {
        rings += `<circle class="cover__ink-stroke" cx="${cx}" cy="${cy}" r="${r}" opacity=".10"/>`;
      }
      return `<g id="${id}">${rings}</g>`;
    }
    default:
      return '';
  }
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/**
 * @param {function} onFallback   chamado quando a capa gerada entra no ar,
 *                                 seja por falta de URL ou por falha de rede
 * @param {object} game            registro do catálogo
 * @param {'portrait'|'wide'|'tile'} shape retrato para prateleira e ficha,
 *                                  panorâmico para o fundo do hero,
 *                                  quadrado para a miniatura do índice
 * O panorâmico não leva inicial nem número: o hero já grava o nome em
 * display e o catálogo na linha de meta, e repetir vira ruído.
 */
const SHAPES = {
  portrait: [600, 900],   /* capa da prateleira e da ficha */
  wide:     [1600, 600],  /* fundo do bloco hero */
  tile:     [600, 600],   /* miniatura de 52px no índice */
};

export function generatedCover(game, shape = 'portrait') {
  const [w, h] = SHAPES[shape] ?? SHAPES.portrait;
  const seed = hash(game.appid);
  const kind = PATTERNS[seed % PATTERNS.length];
  const ground = GROUNDS[(seed >> 5) % GROUNDS.length];
  const id = `cover-${game.appid}-${shape}`;

  const fill = kind === 'rings'
    ? `<use href="#${id}"/>`
    : `<rect width="${w}" height="${h}" fill="url(#${id})"/>`;

  /* Inicial e número só na capa de verdade: a 52px viram borrão e no
     hero o nome já está em display logo ao lado. */
  const marks = shape !== 'portrait' ? '' : `
    <text class="cover__initial" x="40" y="${h - 40}">${escape(game.name[0])}</text>
    <text class="cover__catalog" x="46" y="96">${escape(game.catalog.replace(/^CAT-/, ''))}</text>`;

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', `cover cover--${ground}`);
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid slice');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = `<defs>${patternDefs(kind, id, w, h)}</defs>
                   <rect class="cover__ground" width="${w}" height="${h}"/>
                   ${fill}${marks}`;
  return svg;
}

/**
 * Devolve o elemento de arte de um título: a imagem do CDN quando existe,
 * a capa gerada quando não. Se a imagem falhar em carregar — CDN fora,
 * console offline —, a capa gerada entra no lugar sem piscar layout.
 */
export function coverElement(game, url, shape = 'portrait', onFallback = null) {
  if (!url) {
    onFallback?.();
    return generatedCover(game, shape);
  }

  const img = document.createElement('img');
  img.className = 'cover cover--art';
  img.src = url;
  img.alt = '';
  img.setAttribute('aria-hidden', 'true');
  img.addEventListener(
    'error',
    () => {
      img.replaceWith(generatedCover(game, shape));
      onFallback?.();
    },
    { once: true }
  );
  return img;
}
