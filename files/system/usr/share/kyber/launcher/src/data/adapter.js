/* =====================================================================
   KYBER — contrato de dados

   A UI conhece SÓ esta interface. `mock.js` a implementa hoje; `steam.js`
   a implementará na Etapa 7 lendo `appmanifest_*.acf`, o CDN e o
   `gameprofiled`. Trocar uma implementação pela outra não toca em tela
   nenhuma — é essa a razão de o contrato existir separado.

   Assincronia: tudo que é CONSULTA devolve Promise, porque a origem real
   é disco ou rede. A única exceção é `coverUrl`, que é derivação pura de
   string e precisa ser síncrona para montar marcação.

   ---------------------------------------------------------------------
   Game (listGames)
     appid      number   identificador Steam; títulos locais usam faixa 9xxxxxx
     name       string
     catalog    string   'CAT-0417' — numeração do catálogo local do console
     sizeGB     number
     lastPlayed string   ISO 'YYYY-MM-DD' | null quando nunca jogado
     hoursTotal number
     installed  boolean
     profile    Profile  perfil de performance gravado para o título
     genre      string   caixa alta, PT-BR

   Profile (getProfile / setProfile)
     governor   'powersave' | 'schedutil' | 'performance'
     gpuLevel   'baixo' | 'auto' | 'alto'
     fpsLimit   '30' | '60' | '120' | 'sem limite'
     priority   'padrão' | 'alta' | 'tempo real'

   LaunchStep (launchPlan) — a fila da tela 03
     name       string   'Governor de CPU'
     value      string   valor que será aplicado

   launch(appid, { onStep, signal })
     onStep(i)  chamado quando a etapa i COMEÇA a executar
     signal     AbortSignal; abortar cancela o lançamento e reverte
     resolve    quando a última etapa terminou; rejeita com AbortError
                se cancelado

   Estimate (estimateProfile)
     level      'quiet' | 'nominal' | 'hot'
     intensity  0..1 — posição do cursor na régua
     watts      number
     noise      string  ruído do ventilador
     frames     string  quadros estimados
     latency    string  latência de entrada

   ProfileGroup (profileOptions) — a fonte do editor da tela 04
     key        'governor' | 'gpuLevel' | 'fpsLimit' | 'priority'
     label      rótulo em mono caixa alta
     hint       o mecanismo real do sistema, sem eufemismo
     options    string[] em ordem crescente de intensidade

   SystemUpdate (systemUpdate)
     current    { version, base, kernel }
     incoming   { version, totalGB, doneGB, speedMB, state, etaSeconds }
     changelog  [{ version, text, minor }]
     generations[{ version, when, role }]

   Bluetooth (bluetooth)
     radio      { name, latency, pairing }
     others     [{ id, name, kind, state, signal }]

   RunningGame (getState().runningGame)
     appid      number
     name       string
     startedAt  number   epoch ms; a tela 17 conta a sessão a partir daqui

   Settings (settings) — além de build/kernel/compositor/resolution/refresh:
     sections   Section[]
   Section
     id, label, title, note
     groups     [{ key, label, hint, options[], value }]   seletores
     links      [{ id, label, hint, target }]              levam a outra tela
     facts      [{ label, value }]                         rodapé do painel

   StorageDetail (storageDetail)
     installGB, shadersGB, savesLocalMB, cloud, proton, status

   Download (listDownloads)
     id, appid, name, catalog, kind, totalGB, doneGB, speedMB, state, actions[]

   Session (sessions)
     label      string   'hoje · 22:03'
     value      string   '01:12:44' | '22 / 40'
     muted      boolean  linha de apoio, não de sessão
   ===================================================================== */

/** Métodos que uma implementação precisa oferecer para ser aceita. */
const CONTRACT = [
  'listGames',        // () → Promise<Game[]>
  'getGame',          // (appid) → Promise<GameDetail>
  'coverUrl',         // (appid, kind) → string | null   SÍNCRONO
  'launchPlan',       // (appid) → Promise<LaunchStep[]>
  'launch',           // (appid, {onStep, signal}) → Promise<void>
  'getState',         // () → Promise<{watts,cpuTemp,gpuTemp,profile,intensity,runningGame}>
  'getProfile',       // (appid) → Promise<Profile>
  'setProfile',       // (appid, profile) → Promise<void>
  'estimateProfile',  // (profile) → Estimate            SÍNCRONO
  'idleProfile',      // () → Promise<Profile>  perfil de repouso do console
  'defaultProfile',   // (appid) → Promise<Profile>  perfil de fábrica do título
  'profileOptions',   // () → ProfileGroup[]         grupos do editor (tela 04)
  'systemUpdate',     // () → Promise<SystemUpdate>  tela 14
  'updateAction',     // ('pause'|'resume'|'reboot'|'defer') → Promise<void>
  'bluetooth',        // () → Promise<Bluetooth>     tela 16b
  'forgetDevice',     // (id) → Promise<void>
  'sectionData',      // (sectionId) → Promise<object>  dados da seção viva
  'setSectionOption', // (sectionId, key, value) → Promise<void>
  'closeGame',        // () → Promise<void>     encerra a sessão em curso
  'sessions',         // (appid) → Promise<Session[]>
  'listDownloads',    // () → Promise<Download[]>
  'storage',          // () → Promise<{usedGB,totalGB}>
  'settings',         // () → Promise<Settings>  hub da tela 09
  'setOption',        // (sectionId, groupKey, value) → Promise<void>
  'storageDetail',    // (appid) → Promise<StorageDetail>  painel da tela 10
  'uninstall',        // (appid) → Promise<void>
  'networks',         // () → Promise<Network[]>
  'downloadAction',   // (id, 'pause'|'resume'|'cancel'|'prioritize') → Promise<void>
  'search',           // (consulta) → Promise<Game[]>
];

let impl = null;

/** Instala a implementação. Recusa uma implementação incompleta em vez de
    deixar o erro aparecer meia tela adiante. */
export function useAdapter(implementation) {
  const missing = CONTRACT.filter((m) => typeof implementation?.[m] !== 'function');
  if (missing.length) {
    throw new Error(`adapter incompleto — faltam: ${missing.join(', ')}`);
  }
  impl = implementation;
  return impl;
}

function call(method, args) {
  if (!impl) throw new Error('nenhum adapter instalado — chame useAdapter() antes');
  return impl[method](...args);
}

export const DataAdapter = Object.fromEntries(
  CONTRACT.map((name) => [name, (...args) => call(name, args)])
);
