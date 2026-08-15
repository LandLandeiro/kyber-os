/* =====================================================================
   KYBER — tela 11 · Login Steam

   Passo 2 de 4. Duas rotas lado a lado, e a escolha é o próprio foco:
   Ⓐ na rota primária aprova pelo celular, Ⓐ em ABRIR TECLADO desce para
   o teclado virtual em camada — o mesmo componente da busca e da senha
   de Wi-Fi, montado aqui em modo overlay.

   O QR é decorativo. Um código de verdade sai do desafio de autenticação
   da Steam, que este protótipo não tem; desenhar um padrão que ninguém
   consegue ler seria pior se a tela não dissesse isso, então ela diz.
   ===================================================================== */

import { state } from '../core/state.js';
import { glifoHTML } from '../core/glyphs.js';
import { DataAdapter } from '../data/adapter.js';
import { createKeyboard } from '../components/keyboard.js';
import { toast } from '../core/toast.js';
import { createLoader } from '../components/loader.js';

const HINTS = [
  { glyph: 'A', label: 'SELECIONAR ROTA' },
  { glyph: 'B', label: 'PASSO ANTERIOR' },
  { glyph: 'Y', label: 'GERAR NOVO CÓDIGO' },
];

const PASSOS = [
  ['01', 'IDIOMA E REDE', 'feito'],
  ['02', 'CONTA STEAM', 'atual'],
  ['03', 'CONTROLE', 'futuro'],
  ['04', 'PERFIL PADRÃO', 'futuro'],
];

export async function createSteamLogin({ firstRun, focus }) {
  const jogos = await DataAdapter.listGames();
  let campo = null;          /* 'usuario' | 'senha' | null */
  let usuario = '';
  let senha = '';

  const el = template(jogos.length);
  /* Espera longa por confirmação externa: varredura, conforme a folha. */
  el.querySelector('[data-login="loader"]').append(createLoader('varredura', 34));

  const camada = el.querySelector('[data-login="camada"]');
  const teclado = createKeyboard({
    focus,
    mode: 'overlay',
    region: 'keyboard',
    actions: ['shift', 'simbolos', 'espaco', 'apagar', 'confirmar'],
    onChange: pintarCampo,
    onConfirm: confirmarCampo,
  });
  camada.querySelector('[data-login="kb"]').append(teclado.el);

  return { el, chrome: 'boot', onEnter, onAction, onLeave };

  function onEnter() {
    state.set('screenName', 'PRIMEIRA EXECUÇÃO');
    state.set('bootStep', { n: 2, total: 4, label: 'CONTA' });
    state.set('hints', HINTS);
    state.set('context', 'BUILD 2026.08-1 · REDE OK · 1 GB/s');
  }

  function onLeave() { fecharTeclado(); }

  function onAction(action) {
    if (campo && teclado.handleAction(action)) return true;

    if (action === 'y') {
      toast({ kind: 'device', title: 'NOVO CÓDIGO GERADO',
              body: 'o código anterior expirou · aponte a câmera de novo' });
      return true;
    }

    if (action === 'b') {
      if (campo) { fecharTeclado(); return true; }
      firstRun.voltar();
      return true;
    }

    if (action !== 'a') return undefined;

    const alvo = document.activeElement?.closest?.('[data-login]');
    const papel = alvo?.dataset?.login;

    if (papel === 'qr') { aprovar(); return true; }
    if (papel === 'teclado') { abrirTeclado('usuario'); return true; }
    return undefined;
  }

  /* ---------- rota primária ---------- */

  function aprovar() {
    toast({ kind: 'info', title: 'CONTA CONECTADA',
            body: 'aprovado no Steam Mobile · biblioteca sincronizada' });
    firstRun.avancar();
  }

  /* ---------- rota alternativa ---------- */

  function abrirTeclado(qual) {
    campo = qual;
    teclado.value = qual === 'usuario' ? usuario : senha;
    el.dataset.teclado = 'true';
    camada.querySelector('[data-login="rotulo"]').textContent =
      qual === 'usuario' ? 'USUÁRIO DA STEAM' : 'SENHA DA STEAM';
    pintarCampo(teclado.value);
    focus.pushTrap(camada);
  }

  function fecharTeclado() {
    if (!campo) return;
    campo = null;
    el.dataset.teclado = 'false';
    focus.popTrap();
  }

  function pintarCampo(v) {
    if (campo === 'usuario') usuario = v; else if (campo === 'senha') senha = v;
    const espelho = camada.querySelector('[data-login="valor"]');
    espelho.textContent = campo === 'senha' ? '•'.repeat(v.length) : v;
    el.querySelector('[data-login="campo-usuario"]').textContent = usuario || 'vazio';
    el.querySelector('[data-login="campo-senha"]').textContent =
      senha ? '•'.repeat(senha.length) : 'vazio';
  }

  function confirmarCampo() {
    if (campo === 'usuario') {
      if (!usuario) { fecharTeclado(); return; }
      abrirTeclado('senha');
      return;
    }
    fecharTeclado();
    if (usuario && senha) {
      toast({ kind: 'info', title: 'CONTA CONECTADA',
              body: `${usuario} · Steam Guard será pedido no próximo boot` });
      firstRun.avancar();
      return;
    }
    toast({ kind: 'error', title: 'FALTA A SENHA',
            body: 'Steam exige usuário e senha nesta rota' });
  }
}

/* QR decorativo, determinístico: três marcadores de canto e um miolo
   estável, para o quadro ler como código sem fingir que é um. */
function qrCells(n = 13) {
  const cel = [];
  const marcador = (lx, ly, x, y) => {
    const dx = x - lx, dy = y - ly;
    if (dx < 0 || dy < 0 || dx > 6 || dy > 6) return null;
    const borda = dx === 0 || dy === 0 || dx === 6 || dy === 6;
    const miolo = dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4;
    return borda || miolo;
  };
  let semente = 7;
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const m = marcador(0, 0, x, y) ?? marcador(n - 7, 0, x, y) ?? marcador(0, n - 7, x, y);
      if (m !== null && m !== undefined) { cel.push(m); continue; }
      semente = (semente * 1103515245 + 12345) & 0x7fffffff;
      cel.push(((semente >> 16) & 1) === 1);
    }
  }
  return cel;
}

function template(totalJogos) {
  const section = document.createElement('section');
  section.className = 'login screen__page';
  section.dataset.teclado = 'false';

  const passo = ([n, rotulo, estado]) => `
    <div class="login__passo login__passo--${estado}">
      <span class="login__passo-mark"></span>
      <span class="login__passo-text">${n}&nbsp;&nbsp;${rotulo}</span>
    </div>`;

  const linha = (k, v) => `
    <div class="login__apos-row"><span>${k}</span><span>${v}</span></div>`;

  section.innerHTML = `
    <div class="login__rota focusable" tabindex="0" role="button"
         data-region="login-qr" data-region-flow="vertical" data-region-dim="off"
         data-region-right="login-alt"
         data-login="qr" data-focus-initial aria-label="Aprovar no celular">
      <div class="login__kicker"><span>ROTA PRIMÁRIA</span><span class="login__rule"></span></div>
      <h1 class="login__title">Aprove no app do celular</h1>
      <p class="login__desc">Abra o Steam Mobile, toque em Confirmações e aponte a câmera para o código.</p>

      <div class="login__instalacao">
        <div class="login__label">INSTALAÇÃO</div>
        ${PASSOS.map(passo).join('')}
      </div>

      <div class="login__qr-wrap">
        <div class="login__qr">
          <div class="login__qr-grid">
            ${qrCells().map((on) => `<i${on ? ' data-on="true"' : ''}></i>`).join('')}
          </div>
        </div>
        <div class="login__qr-side">
          <div class="login__aguardando">
            <span data-login="loader"></span>
            <span>AGUARDANDO O CELULAR…</span>
          </div>
          <div class="login__fatos">SEM SENHA NESTE DISPOSITIVO<br>SESSÃO PERSISTE APÓS DESLIGAR<br>STEAM GUARD OBRIGATÓRIO</div>
          <div class="login__qr-nota">Código ilustrativo: o desafio real vem da Steam e este protótipo não fala com ela.</div>
        </div>
      </div>
    </div>

    <div class="login__rota login__rota--alt">
      <div class="login__kicker"><span>ROTA ALTERNATIVA</span><span class="login__rule"></span></div>
      <h2 class="login__title login__title--alt">Entrar com teclado</h2>
      <p class="login__desc">Digite usuário e senha pelo teclado virtual. Steam Guard será pedido em seguida.</p>

      <div class="login__campos">
        <div class="login__campo">
          <div class="login__label">USUÁRIO</div>
          <div class="login__caixa" data-login="campo-usuario">vazio</div>
        </div>
        <div class="login__campo">
          <div class="login__label">SENHA</div>
          <div class="login__caixa" data-login="campo-senha">vazio</div>
        </div>
      </div>

      <div class="login__apos">
        <div class="login__label">APÓS ENTRAR</div>
        ${linha('Biblioteca sincroniza', `${totalJogos} títulos`)}
        ${linha('Saves na nuvem', 'ativados')}
        ${linha('Perfis de performance', 'equilibrado')}
      </div>

      <div class="login__acao" data-region="login-alt" data-region-flow="horizontal"
           data-region-dim="off" data-region-left="login-qr">
        <div class="btn focusable" tabindex="0" role="button"
             data-login="teclado">ABRIR TECLADO</div>
      </div>
    </div>

    <div class="login__camada glass-scrim" data-login="camada">
      <div class="login__camada-topo">
        <div class="login__label" data-login="rotulo">USUÁRIO DA STEAM</div>
        <div class="login__espelho">
          <span class="mirror__value" data-login="valor"></span>
          <span class="mirror__caret"></span>
        </div>
        <div class="login__camada-legenda">
          <span>CAMPO ESPELHADO · O QUE VOCÊ DIGITA APARECE AQUI</span>
          <span>CONFIRMAR SEGUE PARA O PRÓXIMO CAMPO · ${glifoHTML('B')} FECHA</span>
        </div>
      </div>
      <div data-login="kb"></div>
    </div>`;
  return section;
}
