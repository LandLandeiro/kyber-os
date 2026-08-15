/* =====================================================================
   KYBER — tela 19 · Splash de boot

   NOTA TÉCNICA — ISTO NÃO É O ARTEFATO FINAL.

   No console de verdade o splash é um tema do plymouth: roda no
   initramfs, antes de o gamescope subir e muito antes de o launcher
   existir. Nenhuma linha deste arquivo estará lá — o que vai para o
   console é um tema plymouth (script + PNG) com o mesmo desenho.

   Aqui ele é a tela de carregamento inicial do launcher, e serve para
   duas coisas: demonstrar visualmente o quadro de boot e dar ao
   protótipo um começo de fluxo. Quando o tema plymouth for feito, este
   arquivo continua útil como referência de proporção e ritmo, mas não
   como implementação.

   Sem chrome nenhum: 1920×1080 de void absoluto, a palavra e a linha de
   progresso. É a única tela do sistema sem header, sem régua e sem
   rodapé — e a única onde `void-abs` é permitido, porque não há camada
   alguma para perceber.
   ===================================================================== */

import { state } from '../core/state.js';

/* A linha de progresso do splash é o terceiro uso de cor saturada que a
   identidade autoriza, e o único movimento desta tela. */
const SPLASH_SVG = 'src/assets/logo/kyber-splash.svg';
const DURACAO_MS = 2600;
const INICIO = 4;      /* o mockup abre em 4% — o boot já começou */

/* Injeta o arquivo da marca no lugar do wordmark de DOM, descartando a
   linha de progresso que vem congelada em 80% — quem desenha o progresso
   vivo é a barra da tela. Falhar aqui não quebra nada: o wordmark de DOM
   já está no lugar e é o mesmo desenho. */
async function marcaDoPacote(host) {
  try {
    const svg = await (await fetch(SPLASH_SVG)).text();
    const doc = new DOMParser().parseFromString(svg, 'image/svg+xml');
    const raiz = doc.querySelector('svg');
    if (!raiz || doc.querySelector('parsererror')) return;
    for (const r of raiz.querySelectorAll('rect')) {
      if (Number(r.getAttribute('y')) >= 1000) r.remove();   /* barra congelada */
    }
    raiz.removeAttribute('width');
    raiz.removeAttribute('height');
    host.replaceChildren(raiz);
    host.dataset.pacote = 'true';
  } catch {
    /* sem o arquivo, fica o wordmark de DOM */
  }
}

export async function createSplash({ firstRun }) {
  const el = document.createElement('section');
  el.className = 'splash screen__page';
  /* A marca vem do pacote, na versão só tipográfica — que é a do mockup.

     Ela entra INLINE, não como <img>: um SVG carregado por <img> é um
     documento isolado e não alcança a @font-face da página, então o
     wordmark saía em Helvetica. A folha da marca proíbe o wordmark em
     qualquer fonte que não Familjen Grotesk 700, e inline ele herda a
     fonte da página.

     Até o arquivo chegar, o mesmo wordmark em DOM segura o quadro — sem
     ele haveria um frame vazio no começo do boot. */
  el.innerHTML = `
    <div class="splash__mark" data-splash="marca">KYBER</div>
    <div class="splash__track"></div>
    <div class="splash__bar" data-splash="bar" style="width:${INICIO}%"></div>`;

  marcaDoPacote(el.querySelector('[data-splash="marca"]'));

  const barra = el.querySelector('[data-splash="bar"]');
  let raf = 0;
  let inicio = 0;

  return { el, chrome: 'bare', onEnter, onLeave, onAction, unmount };

  function onEnter() {
    state.set('screenName', 'BOOT');
    state.set('hints', []);
    inicio = performance.now();
    correr();
  }

  function onLeave() { cancelAnimationFrame(raf); }
  function unmount() { cancelAnimationFrame(raf); }

  /* Ⓐ ou Ⓑ pulam a espera. Splash não é lugar de prender ninguém. */
  function onAction(action) {
    if (action === 'a' || action === 'b') { firstRun.avancar(); return true; }
    return undefined;
  }

  function correr() {
    const passo = () => {
      const t = Math.min(1, (performance.now() - inicio) / DURACAO_MS);
      barra.style.width = `${INICIO + (100 - INICIO) * t}%`;
      if (t >= 1) { firstRun.avancar(); return; }
      raf = requestAnimationFrame(passo);
    };
    passo();
  }
}
