/* =====================================================================
   KYBER — implementação de desenvolvimento do contrato de dados.

   Nada aqui persiste: sem localStorage, sem arquivo. O que muda em
   sessão fica em memória e some no reload — é assim que tem que ser
   até o `gameprofiled` existir do outro lado.

   Modelo de perfil: as quatro chaves (governor, gpuLevel, fpsLimit,
   priority) viram um escore 0..8; o escore vira nível, posição na régua
   e consumo estimado. A fórmula é a do protótipo da Etapa 1
   (telas/kyber-01-08-prototipo.dc.html), não invenção nova.
   ===================================================================== */

/* Ordem das opções = ordem crescente de intensidade. O índice É o peso. */
const GOVERNOR = ['powersave', 'schedutil', 'performance'];
const GPU_LEVEL = ['baixo', 'auto', 'alto'];
const FPS_LIMIT = ['30', '60', '120', 'sem limite'];
const PRIORITY = ['padrão', 'alta', 'tempo real'];

/* 'sem limite' não custa mais que 120: o peso do limite de quadros satura. */
const FPS_WEIGHT = [0, 1, 2, 2];

const SCORE_MAX = 8;          /* 2 + 2 + 2 + 2 */
const WATTS_IDLE = 22;        /* consumo de repouso do console */
const WATTS_PER_POINT = 7;

/* ---------------------------------------------------------------------
   Arte da loja.

   A proibição de arte de terceiros da identidade visual (seção 10) valia
   para a fase de mockup, e o próprio documento antecipa o fim dela:
   "KYBER - direcao de arte e tokens.md", Nota honesta, item 2 — "é
   defensável enquanto não há arte; quando as capas reais entrarem, o
   argumento fica sob pressão e a régua vai precisar competir com imagens
   saturadas". As capas reais entraram.

   A pressão prevista sobre a régua é real e ainda não foi tratada: capa
   saturada ao lado de uma régua que é a única cor do sistema. Fica em
   aberto para avaliação visual.

   `false` devolve capa gerada em 100% dos títulos, sem tocar em mais nada.
   --------------------------------------------------------------------- */
const USE_STORE_ART = true;

const CDN = 'https://cdn.cloudflare.steamstatic.com/steam/apps';
const ART_KIND = {
  cover: 'library_600x900.jpg',   /* retrato 2:3 — prateleira */
  hero:  'library_hero.jpg',      /* panorâmico — fundo do bloco hero */
};

const profile = (governor, gpuLevel, fpsLimit, priority) => ({
  governor: GOVERNOR[governor],
  gpuLevel: GPU_LEVEL[gpuLevel],
  fpsLimit: FPS_LIMIT[fpsLimit],
  priority: PRIORITY[priority],
});

/* ---------------------------------------------------------------------
   Catálogo.

   Doze títulos com AppID real e arte publicada — os três assets de cada
   um (600×900 e hero) foram conferidos respondendo 200 no CDN.

   Os três primeiros ocupavam AppIDs fictícios e apareciam com capa cinza
   na prateleira, o que lia como sistema quebrado em vez de decisão de
   design. Ficaram com jogos reais; a numeração de catálogo de cada um
   veio do protótipo da Etapa 1 e não mudou.

   O caminho da capa gerada continua coberto por USE_STORE_ART = false,
   que devolve capa gerada em 100% dos títulos — exercitar o fallback não
   exige manter entrada quebrada permanente na biblioteca.
   --------------------------------------------------------------------- */
const GAMES = [
  {
    appid: 553850, name: 'HELLDIVERS 2', catalog: 'CAT-0417', hasArt: true,
    genre: 'AÇÃO / TÁTICO', year: 2024, sizeGB: 18.4, hoursTotal: 48,
    lastPlayed: '2026-08-14', installed: true, profile: profile(2, 2, 2, 1),
    summary: 'Tiro cooperativo em planetas hostis. Campanha compartilhada entre sessões.',
  },
  {
    appid: 1145360, name: 'Hades', catalog: 'CAT-1145', hasArt: true,
    genre: 'ROGUELIKE', year: 2020, sizeGB: 12.6, hoursTotal: 96,
    lastPlayed: '2026-08-12', installed: true, profile: profile(1, 2, 2, 1),
    summary: 'Ação isométrica por tentativas. Progressão entre execuções.',
  },
  {
    appid: 620, name: 'Portal 2', catalog: 'CAT-0620', hasArt: true,
    genre: 'QUEBRA-CABEÇA', year: 2011, sizeGB: 12.9, hoursTotal: 22,
    lastPlayed: '2026-08-11', installed: true, profile: profile(0, 1, 1, 0),
    summary: 'Quebra-cabeça em primeira pessoa com portais. Campanha e cooperativo.',
  },
  {
    appid: 292030, name: 'The Witcher 3', catalog: 'CAT-2920', hasArt: true,
    genre: 'RPG', year: 2015, sizeGB: 51.2, hoursTotal: 187,
    lastPlayed: '2026-08-09', installed: true, profile: profile(2, 2, 1, 1),
    summary: 'RPG de mundo aberto. Contratos, escolhas e três finais principais.',
  },
  {
    appid: 413150, name: 'Stardew Valley', catalog: 'CAT-4131', hasArt: true,
    genre: 'SIMULAÇÃO', year: 2016, sizeGB: 1.4, hoursTotal: 143,
    lastPlayed: '2026-08-07', installed: true, profile: profile(0, 0, 1, 0),
    summary: 'Fazenda, mineração e relações de vizinhança em ciclo de estações.',
  },
  {
    appid: 367520, name: 'Hollow Knight', catalog: 'CAT-3675', hasArt: true,
    genre: 'METROIDVANIA', year: 2017, sizeGB: 9.1, hoursTotal: 61,
    lastPlayed: '2026-08-05', installed: true, profile: profile(1, 1, 2, 0),
    summary: 'Exploração 2D em reino subterrâneo. Mapa por descoberta, sem marcador.',
  },
  {
    appid: 526870, name: 'Satisfactory', catalog: 'CAT-0912', hasArt: true,
    genre: 'SIMULAÇÃO', year: 2024, sizeGB: 6.8, hoursTotal: 112,
    lastPlayed: '2026-08-02', installed: true, profile: profile(0, 1, 0, 0),
    summary: 'Construção de fábrica em planeta alienígena. Logística em primeira pessoa.',
  },
  {
    appid: 105600, name: 'Terraria', catalog: 'CAT-1056', hasArt: true,
    genre: 'AVENTURA', year: 2011, sizeGB: 1.1, hoursTotal: 208,
    lastPlayed: '2026-07-30', installed: true, profile: profile(1, 0, 1, 0),
    summary: 'Construção e combate em mundo 2D gerado. Progressão por chefes.',
  },
  {
    appid: 275850, name: "No Man's Sky", catalog: 'CAT-2758', hasArt: true,
    genre: 'EXPLORAÇÃO', year: 2016, sizeGB: 18.9, hoursTotal: 74,
    lastPlayed: '2026-07-26', installed: true, profile: profile(2, 2, 2, 2),
    summary: 'Levantamento planetário em galáxia procedural. Voo e superfície contínuos.',
  },
  {
    appid: 588650, name: 'Dead Cells', catalog: 'CAT-5886', hasArt: true,
    genre: 'ROGUELIKE', year: 2018, sizeGB: 1.9, hoursTotal: 39,
    lastPlayed: '2026-07-21', installed: true, profile: profile(1, 1, 2, 1),
    summary: 'Ação lateral por tentativas. Rotas alternativas por permissão de acesso.',
  },
  {
    appid: 1091500, name: 'Cyberpunk 2077', catalog: 'CAT-1091', hasArt: true,
    genre: 'RPG', year: 2020, sizeGB: 68.7, hoursTotal: 12,
    lastPlayed: '2026-07-14', installed: true, profile: profile(2, 2, 3, 1),
    summary: 'RPG de ação em cidade densa. Ramificação por atributo e reputação.',
  },
  {
    appid: 753640, name: 'Outer Wilds', catalog: 'CAT-1130', hasArt: true,
    genre: 'EXPLORAÇÃO', year: 2019, sizeGB: 4.1, hoursTotal: 0,
    lastPlayed: null, installed: false, profile: profile(1, 1, 1, 0),
    summary: 'Levantamento de um sistema solar em laço temporal. Sem combate.',
  },
];

const byId = new Map(GAMES.map((g) => [g.appid, g]));

/* Repouso do console: nada forçado em lugar nenhum. Escore 0 → 22 W. */
const IDLE_PROFILE = profile(0, 0, 0, 0);

/* Perfis alterados em sessão vivem aqui e some no reload — de propósito. */
const overrides = new Map();

const profileOf = (appid) => overrides.get(appid) ?? byId.get(appid)?.profile;

/* Escore → nível. Limiares do protótipo: até 2 silencioso, até 5 equilibrado. */
function scoreOf(p) {
  return (
    GOVERNOR.indexOf(p.governor) +
    GPU_LEVEL.indexOf(p.gpuLevel) +
    FPS_WEIGHT[FPS_LIMIT.indexOf(p.fpsLimit)] +
    PRIORITY.indexOf(p.priority)
  );
}

function estimateProfile(p) {
  const score = scoreOf(p);
  return {
    level: score <= 2 ? 'quiet' : score <= 5 ? 'nominal' : 'hot',
    intensity: score / SCORE_MAX,
    watts: WATTS_IDLE + score * WATTS_PER_POINT,
  };
}

/* ---------------------------------------------------------------------
   Fila de lançamento — o que o gameprofiled faz antes de sair de cena.
   Os quatro primeiros passos são o perfil do título; os dois últimos são
   sempre os mesmos porque não dependem do jogo.

   O ritmo de 620ms por passo vive aqui, não na interface: quem demora é
   o daemon, e a tela só reage ao que ele avisa. Na Etapa 7 o atraso some
   e o tempo passa a ser o de cada escrita em /sys de verdade.
   --------------------------------------------------------------------- */
const LAUNCH_STEPS = [
  { name: 'Governor de CPU',         value: (p) => p.governor },
  { name: 'Nível de energia da GPU', value: (p) => p.gpuLevel },
  { name: 'Limite de quadros',       value: (p) => p.fpsLimit },
  { name: 'Prioridade de processo',  value: (p) => p.priority },
  { name: 'Prefixo Proton',          value: () => 'experimental' },
  { name: 'Encerrando o launcher',   value: () => 'gamescope' },
];

const STEP_MS = 620;

const sleep = (ms, signal) =>
  new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(t);
      reject(new DOMException('lançamento cancelado', 'AbortError'));
    }, { once: true });
  });

const framesOf = (p) =>
  p.fpsLimit === 'sem limite' ? 143 : Number(p.fpsLimit) - 2;

/* Sessão em curso — o header e a precedência da régua leem daqui.

   Começa vazia: é o estado da tela 01 na referência
   (telas/prints/01-biblioteca.png não tem indicador de jogo vivo) e é o
   que deixa a régua em modo de previsão, seguindo o foco da prateleira.
   `launch()` preenche; abrir com 553850 reproduz o cenário da tela 09,
   com Hollow Tide em execução e a régua travada na medição. */
let running = null;
let startedAt = 0;

export const MockAdapter = {
  async listGames() {
    return GAMES.map((g) => ({ ...g, profile: profileOf(g.appid) }));
  },

  async getGame(appid) {
    const g = byId.get(appid);
    if (!g) throw new Error(`appid desconhecido: ${appid}`);
    return { ...g, profile: profileOf(appid) };
  },

  coverUrl(appid, kind = 'cover') {
    if (!USE_STORE_ART) return null;
    const g = byId.get(appid);
    if (!g?.hasArt) return null;              /* → capa gerada */
    return `${CDN}/${appid}/${ART_KIND[kind] ?? ART_KIND.cover}`;
  },

  async launchPlan(appid) {
    const p = profileOf(appid);
    return LAUNCH_STEPS.map(({ name, value }) => ({ name, value: value(p) }));
  },

  /* Cancelar no meio não deixa o console num estado intermediário: o
     jogo simplesmente não passa a rodar. Reverter perfil de verdade é
     trabalho do daemon, na Etapa 7. */
  async launch(appid, { onStep, signal } = {}) {
    if (!byId.has(appid)) throw new Error(`appid desconhecido: ${appid}`);

    for (let i = 0; i < LAUNCH_STEPS.length; i++) {
      if (signal?.aborted) throw new DOMException('lançamento cancelado', 'AbortError');
      onStep?.(i);
      await sleep(STEP_MS, signal);
    }
    running = appid;
    startedAt = Date.now();
  },

  /* Encerrar devolve a máquina ao repouso. Quem faz isso de verdade é o
     gameprofiled revertendo cada escrita em /sys; aqui é só o estado. */
  async closeGame() {
    running = null;
    startedAt = 0;
  },

  async idleProfile() {
    return { ...IDLE_PROFILE };
  },

  /* Histórico da tela 17. Fixo: sessão é coisa que o console grava, e o
     mock não grava nada. */
  async sessions(appid) {
    const g = byId.get(appid);
    return [
      { label: 'ontem · 19:41', value: '02:38:10' },
      { label: 'anteontem · 21:02', value: '01:04:52' },
      { label: 'conquistas', value: `22 / ${g?.hoursTotal > 100 ? 60 : 40}`, muted: true },
    ];
  },

  async getState() {
    const jogo = running === null ? null : byId.get(running);
    /* Sem sessão, o console reporta o perfil de repouso — é o que o
       gameprofiled devolve com nada rodando, não um valor de enfeite. */
    const est = estimateProfile(jogo ? profileOf(running) : IDLE_PROFILE);
    return {
      watts: est.watts,
      cpuTemp: 61,
      gpuTemp: 68,
      profile: est.level,
      intensity: est.intensity,
      controllers: 1,
      /* Quadros por segundo só existem com jogo na tela. O limite é o
         teto; o valor real fica logo abaixo dele. */
      fps: jogo ? framesOf(profileOf(running)) : null,
      runningGame: jogo
        ? { appid: jogo.appid, name: jogo.name, startedAt }
        : null,
    };
  },

  async getProfile(appid) {
    return { ...profileOf(appid) };
  },

  async setProfile(appid, next) {
    overrides.set(appid, { ...next });
  },

  estimateProfile,

  async listDownloads() { return []; },

  async storage() {
    /* A repartição sai daqui inteira para a tela 10 não ter que inventar
       o que é "outros" — barra cujos segmentos não somam o total usado é
       gráfico mentindo. */
    const gamesGB = Math.round(
      GAMES.filter((g) => g.installed).reduce((sum, g) => sum + g.sizeGB, 0) * 10
    ) / 10;
    const systemGB = 110;
    const otherGB = 60;
    return {
      totalGB: 930,
      usedGB: Math.round((gamesGB + systemGB + otherGB) * 10) / 10,
      gamesGB, systemGB, otherGB,
    };
  },

  async settings() {
    return {
      build: 'KYBER · BUILD 2026.08-1',
      kernel: '6.12-zen',
      compositor: 'gamescope',
      image: 'bazzite-stable',
      resolution: '1920×1080',
      refresh: '120 HZ',
    };
  },
};

/* =====================================================================
   Camada de configurações, armazenamento, downloads e busca.

   Fica no fim do arquivo porque é dado de tela, não modelo de máquina:
   o que está acima descreve o console, o que está aqui descreve o que
   as telas 09, 10, 13 e 18 mostram sobre ele.
   ===================================================================== */

const SECTIONS = [
  {
    id: 'video', label: 'VÍDEO', title: 'Vídeo', note: 'APLICA IMEDIATAMENTE',
    groups: [
      { key: 'resolucao', label: 'RESOLUÇÃO', hint: 'saída ativa via HDMI 2.1',
        options: ['1280×720', '1920×1080', '2560×1440', '3840×2160'], value: '1920×1080' },
      { key: 'taxa', label: 'TAXA DE ATUALIZAÇÃO', hint: 'o painel aceita até 120 Hz',
        options: ['60 HZ', '120 HZ'], value: '120 HZ' },
      { key: 'vrr', label: 'TAXA VARIÁVEL · VRR', hint: 'reduz rasgo abaixo do limite de quadros',
        options: ['DESLIGADO', 'ATIVO'], value: 'ATIVO' },
      { key: 'escala', label: 'ESCALA DA INTERFACE', hint: 'distância de leitura de 1 a 3 metros',
        options: ['100 %', '110 %', '125 %'], value: '110 %' },
    ],
    facts: [
      { label: 'SAÍDA', value: 'HDMI 2.1' },
      { label: 'PAINEL', value: '120 HZ · VRR' },
      { label: 'HDR', value: 'indisponível' },
      { label: 'COMPOSITOR', value: 'gamescope' },
    ],
  },
  {
    /* Seção viva: o volume é a barra de degraus.
       Ver src/screens/settings-audio.js. */
    id: 'audio', label: 'ÁUDIO', title: 'Áudio', note: 'APLICA IMEDIATAMENTE',
  },
  {
    /* Seção viva: dois estados de link e o teclado de senha por cima.
       Ver src/screens/settings-network.js. */
    id: 'rede', label: 'REDE', title: 'Rede', note: 'CONECTADO POR WI-FI',
  },
  {
    /* A seção BLUETOOTH é a tela 16b e se desenha sozinha, a partir do
       que a Gamepad API reporta — ver src/screens/bluetooth.js. */
    id: 'bluetooth', label: 'BLUETOOTH', title: 'Bluetooth', note: 'RÁDIO ATIVO',
  },
  {
    id: 'sistema', label: 'SISTEMA', title: 'Sistema', note: 'BAZZITE-STABLE',
    links: [
      { id: 'storage', label: 'ARMAZENAMENTO',
        hint: 'o que ocupa o disco e o que dá para apagar', target: 'storage' },
      { id: 'downloads', label: 'DOWNLOADS',
        hint: 'fila de instalação e atualização', target: 'downloads' },
      { id: 'update', label: 'ATUALIZAÇÃO DO SISTEMA',
        hint: 'gerações da imagem no disco e rollback', target: 'update' },
    ],
    facts: [
      { label: 'KERNEL', value: '6.12-zen' },
      { label: 'IMAGEM', value: 'bazzite-stable' },
      { label: 'MESA', value: '25.2' },
      { label: 'DISCO', value: '612 / 930 GB' },
    ],
  },
  {
    /* Seção viva: tem a fresta de luz e a prévia dela.
       Ver src/screens/settings-appearance.js. */
    id: 'aparencia', label: 'APARÊNCIA', title: 'Aparência', note: 'QUATRO CONTROLES',
  },
];

const NETWORKS = [
  { ssid: 'Fibra 2G4 — 5 GHz', security: 'WPA2', signal: 92, connected: true },
  { ssid: 'KYBER-LAB', security: 'WPA3', signal: 78, connected: false },
  { ssid: 'Vizinho 5G', security: 'WPA2', signal: 41, connected: false },
];

/* Fila de download. Viva: pausar, retomar e cancelar mudam de verdade. */
let DOWNLOADS = [
  { id: 'd1', appid: 1091500, name: 'Cyberpunk 2077', catalog: 'CAT-1091',
    kind: 'ATUALIZAÇÃO 2.4', totalGB: 60, doneGB: 41, speedMB: 86, state: 'BAIXANDO' },
  { id: 'd2', appid: 588650, name: 'Dead Cells', catalog: 'CAT-5886',
    kind: 'INSTALAÇÃO', totalGB: 8, doneGB: 0, speedMB: 0, state: 'AGUARDANDO' },
  { id: 'd3', appid: 275850, name: "No Man's Sky", catalog: 'CAT-2758',
    kind: 'ATUALIZAÇÃO 5.1', totalGB: 19, doneGB: 0, speedMB: 0, state: 'AGUARDANDO' },
];

const uninstalled = new Set();

Object.assign(MockAdapter, {
  async settings() {
    const disk = await MockAdapter.storage();
    return {
      build: 'KYBER · BUILD 2026.08-1',
      kernel: '6.12-zen',
      compositor: 'gamescope',
      image: 'bazzite-stable',
      resolution: '1920×1080',
      refresh: '120 HZ',
      disk,
      sections: SECTIONS.map((s) => ({ ...s })),
    };
  },

  async setOption(sectionId, groupKey, value) {
    const group = SECTIONS.find((s) => s.id === sectionId)?.groups
      ?.find((g) => g.key === groupKey);
    if (group) group.value = value;
  },

  async storageDetail(appid) {
    const g = byId.get(appid);
    if (!g) throw new Error(`appid desconhecido: ${appid}`);
    return {
      installGB: g.sizeGB,
      shadersGB: Math.round(g.sizeGB * 0.08 * 10) / 10,
      savesLocalMB: 40 + (g.appid % 120),
      cloud: 'sincronizados',
      proton: 'experimental',
      status: running === appid ? 'EM EXECUÇÃO AGORA' : 'OCIOSO',
    };
  },

  async uninstall(appid) {
    if (running === appid) throw new Error('não dá para desinstalar o jogo em execução');
    uninstalled.add(appid);
    const g = byId.get(appid);
    if (g) g.installed = false;
  },

  async networks() {
    return NETWORKS.map((n) => ({ ...n }));
  },

  async listDownloads() {
    return DOWNLOADS.map((d) => ({ ...d }));
  },

  async downloadAction(id, action) {
    const i = DOWNLOADS.findIndex((d) => d.id === id);
    if (i < 0) return;
    if (action === 'cancel') { DOWNLOADS.splice(i, 1); return; }
    if (action === 'pause')  { DOWNLOADS[i].state = 'PAUSADO'; DOWNLOADS[i].speedMB = 0; return; }
    if (action === 'resume') { DOWNLOADS[i].state = 'BAIXANDO'; DOWNLOADS[i].speedMB = 86; return; }
    if (action === 'prioritize') {
      const [d] = DOWNLOADS.splice(i, 1);
      DOWNLOADS.unshift(d);
    }
  },

  /* Busca por prefixo em qualquer palavra do título: quem digita "HOL"
     espera achar "Vale Holanda", não só o que começa com HOL. */
  async search(consulta) {
    const q = String(consulta ?? '').trim().toLowerCase();
    /* Consulta vazia devolve tudo: abrir a busca mostra a biblioteca, e
       não uma lista vazia esperando alguém adivinhar o que digitar. */
    if (!q) return GAMES.map((g) => ({ ...g, profile: profileOf(g.appid) }));
    return GAMES.filter((g) =>
      g.name.toLowerCase().split(/[\s:&-]+/).some((w) => w.startsWith(q)) ||
      g.name.toLowerCase().startsWith(q)
    ).map((g) => ({ ...g, profile: profileOf(g.appid) }));
  },
});

/* =====================================================================
   Editor de perfil (04), atualização do sistema (14) e Bluetooth (16b).
   ===================================================================== */

/* As três estimativas derivadas do escore. São palpite do gameprofiled,
   e a interface diz isso com todas as letras — não são medição. */
const NOISE   = ['baixo', 'moderado', 'alto'];
const FRAMES  = ['~48 fps', '~86 fps', '~118 fps'];
const LATENCY = ['18 ms', '12 ms', '8 ms'];

const PROFILE_GROUPS = [
  { key: 'governor', label: 'GOVERNOR DE CPU',
    hint: 'escalonamento de frequência', options: GOVERNOR },
  { key: 'gpuLevel', label: 'NÍVEL DE ENERGIA DA GPU',
    hint: 'amdgpu power_dpm_force_performance_level', options: GPU_LEVEL },
  { key: 'fpsLimit', label: 'LIMITE DE FPS',
    hint: 'aplicado pelo gamescope', options: FPS_LIMIT },
  { key: 'priority', label: 'PRIORIDADE DE PROCESSO',
    hint: 'nice / sched policy', options: PRIORITY },
];

/* ---------------------------------------------------------------------
   Atualização do sistema.

   O progresso não é animação: sai do relógio. `systemUpdate()` calcula
   quanto já baixou a partir de quando o download foi retomado, que é o
   que uma leitura de daemon faz. Pausar congela o acumulado.
   --------------------------------------------------------------------- */
const UPDATE = {
  current: { version: '2026.08.1', base: 'bazzite-stable', kernel: '6.12-zen' },
  incoming: { version: '2026.09.0', totalGB: 2.6, speedMB: 71 },
  baseDoneGB: 1.4,
  resumedAt: Date.now(),
  state: 'BAIXANDO',
};

const CHANGELOG = [
  ['gamescope 3.17 · HDR em jogos Proton', false],
  ['gameprofiled: perfis por sessão, não só por jogo', false],
  ['mesa 25.3 · correção de stutter em shaders novos', false],
  ['suporte a controle DualSense por Bluetooth LE', false],
  ['kernel 6.13-zen · latência de entrada 2 ms menor', false],
  ['launcher: vista de índice alternável pelo Ⓨ', false],
  ['steam runtime sniper atualizado', true],
  ['correção: ventoinha em rampa após suspender', true],
  ['correção: áudio HDMI mudo ao retomar de suspensão', true],
  ['pipewire 1.4 · perfil de baixa latência por padrão', true],
  ['correção: teclado virtual perdia foco ao trocar de mapa', true],
  ['bluez 5.79 · reconexão de controle mais rápida', true],
  ['correção: rollback não listava a geração mais antiga', true],
  ['flatpak 1.16 · atualizações em segundo plano', true],
];

function doneGB() {
  if (UPDATE.state !== 'BAIXANDO') return UPDATE.baseGBAtPause ?? UPDATE.baseDoneGB;
  const s = (Date.now() - UPDATE.resumedAt) / 1000;
  const baixado = UPDATE.baseDoneGB + (s * UPDATE.incoming.speedMB) / 1024;
  return Math.min(UPDATE.incoming.totalGB, baixado);
}

const OTHERS = [
  { id: 'jbl', name: 'Fone JBL 520', kind: 'ÁUDIO', state: 'CONECTADO', signal: '−55 dBm' },
  { id: 'kbd', name: 'Teclado Keychron K3', kind: 'TECLADO', state: 'DESLIGADO', signal: '—' },
];

let outros = [...OTHERS];

Object.assign(MockAdapter, {
  async defaultProfile(appid) {
    const g = byId.get(appid);
    if (!g) throw new Error(`appid desconhecido: ${appid}`);
    return { ...g.profile };
  },

  profileOptions() {
    return PROFILE_GROUPS.map((g) => ({ ...g, options: [...g.options] }));
  },

  async systemUpdate() {
    const done = doneGB();
    const total = UPDATE.incoming.totalGB;
    if (done >= total && UPDATE.state === 'BAIXANDO') UPDATE.state = 'PRONTA';

    const faltam = total - done;
    return {
      current: { ...UPDATE.current },
      incoming: {
        ...UPDATE.incoming,
        doneGB: Math.round(done * 100) / 100,
        state: UPDATE.state,
        speedMB: UPDATE.state === 'BAIXANDO' ? UPDATE.incoming.speedMB : 0,
        etaSeconds: UPDATE.state === 'BAIXANDO'
          ? Math.ceil((faltam * 1024) / UPDATE.incoming.speedMB)
          : null,
      },
      changelog: CHANGELOG.map(([text, minor]) => ({
        version: UPDATE.incoming.version, text, minor,
      })),
      generations: [
        { version: UPDATE.incoming.version, when: 'baixada hoje', role: 'PRÓXIMO BOOT' },
        { version: UPDATE.current.version, when: 'há 12 dias', role: 'EM USO' },
        { version: '2026.07.3', when: 'há 41 dias', role: 'ROLLBACK' },
      ],
    };
  },

  async updateAction(acao) {
    if (acao === 'pause' && UPDATE.state === 'BAIXANDO') {
      UPDATE.baseGBAtPause = doneGB();
      UPDATE.state = 'PAUSADO';
      return;
    }
    if (acao === 'resume' && UPDATE.state === 'PAUSADO') {
      UPDATE.baseDoneGB = UPDATE.baseGBAtPause ?? UPDATE.baseDoneGB;
      UPDATE.baseGBAtPause = undefined;
      UPDATE.resumedAt = Date.now();
      UPDATE.state = 'BAIXANDO';
    }
  },

  async bluetooth() {
    return {
      radio: { name: 'BLUETOOTH 5.3', latency: '8 ms', pairing: 'ATIVAR' },
      others: outros.map((d) => ({ ...d })),
    };
  },

  async forgetDevice(id) {
    outros = outros.filter((d) => d.id !== id);
  },
});

/* estimateProfile ganha as três derivadas sem mudar as chaves antigas. */
const estimateBase = MockAdapter.estimateProfile;
MockAdapter.estimateProfile = (p) => {
  const est = estimateBase(p);
  const lv = ['quiet', 'nominal', 'hot'].indexOf(est.level);
  return { ...est, noise: NOISE[lv], frames: FRAMES[lv], latency: LATENCY[lv] };
};

/* =====================================================================
   Seções vivas do hub: ÁUDIO (09b), REDE (09c) e APARÊNCIA (09d).

   Cada uma tem forma própria demais para caber no modelo genérico de
   seletores — volume em degraus, dois estados de link, prévia de
   hardware. Por isso desenham a si mesmas e leem daqui.
   ===================================================================== */

const AUDIO = {
  saida: 'HDMI',
  volume: 14,          /* em degraus de 0 a 20 */
  modo: 'estéreo',
  som: 'ATIVO',
  dispositivos: [
    { id: 'HDMI', nome: 'LG OLED C3' },
    { id: 'FONE USB', nome: 'HyperX Cloud III' },
    { id: 'BLUETOOTH', nome: 'Fone JBL 520' },
  ],
  facts: [
    { label: 'AMOSTRAGEM', value: '48 kHz' },
    { label: 'FORMATO', value: '16 bit PCM' },
    { label: 'LATÊNCIA', value: '21 ms' },
    { label: 'SERVIDOR', value: 'pipewire' },
  ],
};

/* Qual link está ativo é decisão do hardware, não do usuário: cabo
   espetado desliga o rádio. Trocar aqui (ou por `kyber.data.setSectionOption
   ('rede','link','cabo')` no console) mostra o outro estado da tela. */
const REDE = {
  link: 'wifi',
  radio: 'DESLIGADO',
  enderecamento: 'dhcp',
  wifi: {
    ssid: 'Fibra 2G4 — 5 GHz',
    ip: '192.168.0.34', seguranca: 'wpa2', canal: 44,
    sinal: '−42', linkGB: '1,2',
    facts: [
      { label: 'INTERFACE', value: 'wlan0' },
      { label: 'MAC', value: 'A4:2B:8C:11:70:D9' },
      { label: 'GATEWAY', value: '192.168.0.1' },
      { label: 'DNS', value: '1.1.1.1' },
    ],
  },
  cabo: {
    ip: '192.168.0.12', concessao: 'dhcp · concessão de 24 h',
    linkGB: '1', latencia: '4',
    facts: [
      { label: 'INTERFACE', value: 'eth0' },
      { label: 'MAC', value: 'A4:2B:8C:11:70:D8' },
      { label: 'GATEWAY', value: '192.168.0.1' },
      { label: 'DNS', value: '1.1.1.1' },
    ],
  },
  redes: [
    { ssid: 'Fibra 2G4 — 5 GHz', seguranca: 'wpa2 · seguro', sinal: '−42', conectada: true },
    { ssid: 'KYBER-LAB', seguranca: 'wpa3 · seguro', sinal: '−58', conectada: false },
    { ssid: 'Vizinho 5G', seguranca: 'wpa2 · seguro', sinal: '−71', conectada: false },
    { ssid: 'Convidados', seguranca: 'aberta', sinal: '−66', conectada: false },
  ],
};

/* A fresta é o único controle da interface que sai da tela. A prévia usa
   o âmbar de verdade porque é a mesma cor no objeto e no pixel — essa
   correspondência é intencional na identidade e quebrá-la faria a prévia
   mentir sobre o que o botão faz. Por ora só persiste. */
const FRESTA = {
  DESLIGADO: { opacidade: 0, rotulo: 'apagada' },
  DISCRETO:  { opacidade: .62, rotulo: '62 % · âmbar fixo' },
  PLENO:     { opacidade: 1, rotulo: '100 % · âmbar fixo' },
};

const APARENCIA = {
  vista: 'VITRINE',
  ordem: 'RECENTES',
  capa: 'ARTE DA LOJA QUANDO HOUVER',
  fresta: 'DISCRETO',
};

Object.assign(MockAdapter, {
  async sectionData(id) {
    if (id === 'audio') return JSON.parse(JSON.stringify(AUDIO));
    if (id === 'rede') return JSON.parse(JSON.stringify(REDE));
    if (id === 'aparencia') {
      return { ...APARENCIA, fresta: { ...FRESTA[APARENCIA.fresta], nivel: APARENCIA.fresta } };
    }
    return null;
  },

  async setSectionOption(id, key, value) {
    if (id === 'audio')  { AUDIO[key] = value; return; }
    if (id === 'rede')   { REDE[key] = value; return; }
    if (id === 'aparencia') { APARENCIA[key] = value; return; }
  },
});

/* COMPORTAMENTO DA CAPA age de verdade: com "sempre capa gerada", nenhum
   título busca arte na loja. Seria estranho um controle inteiro que não
   faz nada quando fazer é uma linha. */
const coverUrlBase = MockAdapter.coverUrl;
MockAdapter.coverUrl = (appid, kind) =>
  APARENCIA.capa === 'SEMPRE CAPA GERADA' ? null : coverUrlBase(appid, kind);
