/* =====================================================================
   KYBER — state
   Store observável mínimo. Sem framework, sem dependência.

   Chaves que atravessam telas:
     runningGame  { name } | null   header, tela 17, menu de energia
     profile      'quiet' | 'nominal' | 'hot'
     watts, cpuTemp, gpuTemp        header e régua
     downloads                      tela 18, toasts
     controllers                    header, 16a/16b

   Sem localStorage/sessionStorage: persistência é do backend.
   ===================================================================== */

const values = new Map();
const listeners = new Map();

function get(key) {
  return values.get(key);
}

function set(key, value) {
  if (values.get(key) === value) return value;   // valor igual não notifica
  values.set(key, value);

  const fns = listeners.get(key);
  if (fns) for (const fn of [...fns]) fn(value, key);

  return value;
}

/** Registra fn para a chave e a chama uma vez com o valor atual.
    Devolve a função de cancelamento. */
function subscribe(key, fn) {
  let fns = listeners.get(key);
  if (!fns) listeners.set(key, (fns = new Set()));
  fns.add(fn);

  if (values.has(key)) fn(values.get(key), key);

  return () => fns.delete(fn);
}

export const state = { get, set, subscribe };

/* Exposto no console para inspeção e para o critério de conclusão da
   Etapa 1: `kyber.state.set('profile', 'quiet')` anima o cursor da régua. */
globalThis.kyber = Object.assign(globalThis.kyber || {}, { state });
