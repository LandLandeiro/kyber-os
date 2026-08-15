/* =====================================================================
   KYBER — senha de Wi-Fi

   Não é uma das 19 telas: é o teclado virtual em modo camada, com o
   campo espelhado próprio. Mesmo componente da busca, outra montagem —
   é para isso que ele é componente.
   ===================================================================== */

import { state } from '../core/state.js';
import { createKeyboard } from '../components/keyboard.js';
import { toast } from '../core/toast.js';

export async function createWifi({ router, focus }, ssid) {
  const el = document.createElement('div');
  el.className = 'wifi glass-scrim';
  el.innerHTML = `
    <div class="wifi__top">
      <div class="wifi__kicker">SENHA DA REDE · ${escape(String(ssid).toUpperCase())}</div>
      <div class="wifi__field">
        <div class="mirror">
          <span class="mirror__value" data-wifi="value"></span>
          <span class="mirror__caret"></span>
        </div>
        <div class="wifi__aside">
          <span class="wifi__count" data-wifi="count">0 / 63</span>
          <span class="rule-v rule-v--30"></span>
          <span class="wifi__show focusable" tabindex="0" role="button"
                data-wifi="show">MOSTRAR</span>
        </div>
      </div>
      <div class="wifi__legend">
        <span>CAMPO ESPELHADO · O QUE VOCÊ DIGITA APARECE AQUI</span>
        <span>CONFIRMAR PARA CONECTAR</span>
      </div>
    </div>
    <div class="wifi__kb"></div>`;

  const valorEl = el.querySelector('[data-wifi="value"]');
  const contaEl = el.querySelector('[data-wifi="count"]');
  let visivel = false;

  const teclado = createKeyboard({
    focus,
    mode: 'overlay',
    region: 'keyboard',
    regionUp: 'wifi-field',
    actions: ['shift', 'simbolos', 'espaco', 'apagar', 'confirmar'],
    onChange: pintar,
    onConfirm: conectar,
  });
  el.querySelector('.wifi__kb').append(teclado.el);

  /* O campo é região própria para o D-pad ↑ sair do teclado e alcançar
     MOSTRAR sem fechar a camada. */
  const campo = el.querySelector('.wifi__aside');
  campo.dataset.region = 'wifi-field';
  campo.dataset.regionFlow = 'horizontal';
  campo.dataset.regionDim = 'off';
  campo.dataset.regionDown = 'keyboard';

  pintar('');

  return { el, overlay: true, onAction, onEnter };

  function onEnter() {
    state.set('screenName', 'REDE');
  }

  function onAction(action) {
    if (teclado.handleAction(action)) return true;
    if (action === 'a' && document.activeElement?.dataset?.wifi === 'show') {
      visivel = !visivel;
      document.activeElement.textContent = visivel ? 'OCULTAR' : 'MOSTRAR';
      pintar(teclado.value);
      return true;
    }
    return undefined;
  }

  function pintar(v) {
    valorEl.textContent = visivel ? v : '•'.repeat(v.length);
    contaEl.textContent = `${v.length} / 63`;
  }

  function conectar(v) {
    router.pop();
    toast({
      kind: v.length >= 8 ? 'info' : 'error',
      title: v.length >= 8 ? 'CONECTANDO' : 'SENHA CURTA DEMAIS',
      body: v.length >= 8
        ? `${ssid} · ${v.length} caracteres · conexão não implementada`
        : `${ssid} · WPA exige pelo menos 8 caracteres`,
    });
  }
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
