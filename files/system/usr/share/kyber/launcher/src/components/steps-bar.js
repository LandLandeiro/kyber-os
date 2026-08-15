/* =====================================================================
   KYBER — barra de degraus

   Padrão novo desta entrega. Um valor contínuo por natureza — volume —
   virando degraus discretos, porque num console não existe arrastar: o
   D-pad anda de um em um e cada passo precisa ter um destino nomeável.
   Vinte degraus dão 5% por toque, que é grosso o bastante para não
   irritar e fino o bastante para não faltar.

   É UM alvo de foco só, não vinte. Focar cada degrau faria vinte paradas
   para atravessar o controle; com um alvo, ← → mexem o valor e ↑ ↓ saem
   para o resto da tela. Por isso a barra CONSOME o movimento horizontal
   enquanto está focada, e devolve nas pontas — quem chegou ao fim da
   escala quer sair dela, não ficar preso.

   Altura dos degraus: rampa desenhada, não linear. Ela sobe rápido no
   começo e quase encosta no teto no fim, para o olho ler "quanto falta"
   antes de ler o número.
   ===================================================================== */

const ALTURAS = [
  34, 38, 42, 46, 50, 54, 58, 62, 66, 70,
  74, 78, 82, 86, 90, 94, 96, 98, 99, 100,
];

export function createStepsBar({
  steps = 20,
  value = 0,
  unit = '%',
  format = null,
  /* Vizinhos declarados: a barra é larga e a heurística de geometria não
     casa o centro dela com o de um seletor estreito. */
  focusUp = null,
  focusDown = null,
  onChange = () => {},
} = {}) {
  let atual = Math.max(0, Math.min(steps, value));

  const el = document.createElement('div');
  el.className = 'steps-bar focusable';
  el.tabIndex = 0;
  el.setAttribute('role', 'slider');
  el.dataset.stepsBar = 'true';
  if (focusUp) el.dataset.focusUp = focusUp;
  if (focusDown) el.dataset.focusDown = focusDown;

  const trilha = document.createElement('div');
  trilha.className = 'steps-bar__track';
  for (let i = 0; i < steps; i++) {
    const degrau = document.createElement('span');
    degrau.className = 'steps-bar__step';
    degrau.style.height = `${ALTURAS[Math.round((i / (steps - 1)) * (ALTURAS.length - 1))]}%`;
    trilha.append(degrau);
  }

  const leitura = document.createElement('div');
  leitura.className = 'steps-bar__value';

  el.append(trilha, leitura);
  pintar();

  return {
    el,
    get value() { return atual; },
    set value(v) { atual = Math.max(0, Math.min(steps, v)); pintar(); },
    /** A tela chama isto antes do focusManager. `true` = consumiu. */
    handleMove,
  };

  function handleMove(dir) {
    if (document.activeElement !== el) return false;
    if (dir !== 'left' && dir !== 'right') return false;

    const proximo = atual + (dir === 'right' ? 1 : -1);
    /* Nas pontas o movimento volta a ser do focusManager: a barra não
       prende quem já chegou ao fim da escala. */
    if (proximo < 0 || proximo > steps) return false;

    atual = proximo;
    pintar();
    onChange(atual);
    return true;
  }

  function pintar() {
    const pct = Math.round((atual / steps) * 100);
    trilha.querySelectorAll('.steps-bar__step').forEach((d, i) => {
      d.dataset.on = i < atual ? 'true' : 'false';
    });
    leitura.innerHTML = format
      ? format(atual)
      : `${pct}<span class="steps-bar__unit"> ${unit}</span>`;
    el.setAttribute('aria-valuenow', String(atual));
    el.setAttribute('aria-valuemax', String(steps));
    el.setAttribute('aria-label', `${pct} ${unit}`);
  }
}
