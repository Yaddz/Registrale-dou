# 06. Design system do painel

Referência visual do painel Registrale (`templates/index.html` e `templates/login.html`). Ao criar ou alterar uma tela, siga este documento. Quando ele não cobrir um caso, prefira a solução mais simples e registre-a aqui.

**Arquivos que são a fonte da verdade:**

| Arquivo | O que define |
|---|---|
| `static/js/tailwind.config.js` | Paleta, fontes, pesos, raios e sombras do Tailwind |
| `static/css/registrale.css` | Tokens em variáveis CSS (claro e escuro), base e classes de componente |

Os dois são carregados no `<head>` de cada template, nesta ordem: Tailwind CDN → `tailwind.config.js` → fontes → `registrale.css`.

---

## 1. Princípios

1. **Ferramenta de trabalho, não vitrine.** O painel é usado todo dia por um analista. Densidade moderada, hierarquia clara, nada que pisque ou brilhe.
2. **Uma ação principal por área.** Cada cabeçalho, cartão ou modal tem no máximo um botão `btn-primary`. O resto é secundário ou discreto.
3. **Cor tem significado.** Neutros para a estrutura, azul tinta para destaque e informação, verde/âmbar/vermelho só para estado. Nunca use cor para "enfeitar" um botão.
4. **Texto legível antes de texto estilizado.** Nada abaixo de 11 px, caixa-alta só em cabeçalho de tabela, frases com a primeira letra maiúscula.
5. **Claro e escuro saem dos mesmos tokens.** Componentes novos usam as variáveis CSS e funcionam nos dois temas sem regra extra.

---

## 2. Tokens

### 2.1 Cor

A paleta foi reduzida de 12 famílias (slate, stone, blue, indigo, purple, teal, rose, amber, orange, yellow, emerald, red) para **5**:

| Família | Uso | Classe Tailwind canônica | Variáveis CSS |
|---|---|---|---|
| **neutral** (stone quente) | Fundo, superfícies, texto, bordas | `neutral-50…950` | `--bg`, `--surface`, `--surface-sunken`, `--surface-hover`, `--border`, `--border-strong`, `--text`, `--text-secondary`, `--text-muted` |
| **ink** (azul tinta) | Links, seleção, foco, informação | `ink-50…950` | `--accent`, `--accent-hover`, `--accent-soft`, `--accent-text` |
| **success** | Ativo, concluído, configurado | `success-50…950` | `--success`, `--success-soft`, `--success-border` |
| **warning** | Pendente, pausado, atenção | `warning-50…950` | `--warning`, `--warning-solid`, `--warning-soft`, `--warning-border` |
| **danger** | Erro, exclusão | `danger-50…950` | `--danger`, `--danger-soft`, `--danger-border` |

A ação principal usa `--primary` (quase preto no claro, quase branco no escuro).

**Apelidos legados.** Para não reescrever 6 mil linhas de uma vez, os nomes antigos continuam funcionando como apelidos em `tailwind.config.js`: `slate`/`stone`/`gray` → neutral, `blue`/`indigo`/`purple`/`sky` → ink, `emerald`/`teal`/`green` → success, `amber`/`orange`/`yellow` → warning, `red`/`rose` → danger. **Código novo usa os nomes canônicos** ou, melhor ainda, as classes de componente.

Valores principais (tema claro):

| Token | Valor | Token | Valor |
|---|---|---|---|
| `--bg` | `#f5f5f4` | `--text` | `#1c1917` |
| `--surface` | `#ffffff` | `--text-secondary` | `#57534e` |
| `--surface-sunken` | `#fafaf9` | `--text-muted` | `#78716c` (4,6:1 sobre branco) |
| `--border` | `#e7e5e4` | `--accent` | `#365d89` |
| `--border-strong` | `#d6d3d1` | `--primary` | `#1c1917` |

### 2.2 Tipografia

- **Família:** IBM Plex Sans (interface) e IBM Plex Mono (CNPJ, datas, horários, expressões cron, caminhos). A Inter foi removida.
- **Pesos:** 400 (texto), 500 (rótulos, botões, navegação), 600 (títulos, números de destaque). `font-bold` e `font-black` foram remapeados para 600 no config; não use pesos acima disso.
- **Escala:**

| Papel | Classe | Tamanho |
|---|---|---|
| Título de página | `text-xl font-semibold tracking-tight` | 20 px |
| Título de cartão/modal | `.card-title` ou `text-base font-semibold` | 15–16 px |
| Texto | `text-sm` | 14 px |
| Botão, tabela | (no componente) | 13 px |
| Rótulo, legenda, ajuda | `text-xs` / `.field-label` | 12 px |
| Mínimo absoluto | `text-[11px]` | 11 px (cabeçalho de tabela, badge) |

- **Caixa:** frases com inicial maiúscula ("Menções recentes", não "Menções Recentes"; "Exportar Excel", não "EXCEL"). `uppercase` só em `<thead>`, com `tracking-wider` (0,04 em).
- **Números:** use `.tabular` (ou dentro de `<table>`) para alinhar algarismos.

### 2.3 Espaçamento e layout

Escala do Tailwind, em múltiplos de 4 px. Valores de uso:

| Contexto | Valor |
|---|---|
| Entre cartões de uma grade | `gap-4` (16 px) |
| Entre seções de uma aba | `space-y-6` (24 px) |
| Padding de cartão | `p-5` (20 px) ou `.card-body` |
| Padding de cartão compacto (barra de filtros) | `p-4` |
| Entre botões de um grupo | `gap-2` |
| Rótulo → campo | 6 px (embutido em `.field-label`) |

### 2.4 Raios

| Token | Valor | Uso |
|---|---|---|
| `rounded-sm` / `--radius-sm` | 4 px | Badge |
| `rounded` / `rounded-md` / `--radius-md` | 6 px | Botão, campo |
| `rounded-lg` / `rounded-xl` / `--radius-lg` | 8 px | Item de navegação, toast, menu |
| `rounded-2xl` / `rounded-3xl` / `--radius-xl` | 12 px | Cartão, modal |
| `rounded-full` | — | Avatar, ponto de status, switch |

`rounded-[2rem]` e outros valores arbitrários estão proibidos.

### 2.5 Elevação

Três níveis, todos via variável (`--shadow-1/2/3`), mapeados no config:

| Nível | Classes | Uso |
|---|---|---|
| 1 | `shadow-xs`, `shadow-sm`, `shadow` | Cartão, botão secundário |
| 2 | `shadow-md`, `shadow-lg` | Menu, popover, tooltip |
| 3 | `shadow-xl`, `shadow-2xl` | Modal, toast |

Sem sombras coloridas, sem `shadow-[0_0_…]` (brilho).

### 2.6 Movimento

- Transições de 150 ms em cor e borda (`transition-colors`).
- Sem `active:scale-*`, `hover:scale-*`, `hover:-translate-*`.
- `animate-spin` só em ícone de carregamento. `animate-pulse` não é usado em indicadores de status.

---

## 3. Componentes

Classes definidas em `static/css/registrale.css`. Elas já tratam tema escuro, foco e estado desabilitado.

### Botão

```html
<button class="btn btn-primary"><i data-lucide="plus"></i> Adicionar empresa</button>
<button class="btn btn-secondary"><i data-lucide="download"></i> Exportar Excel</button>
<button class="btn btn-ghost btn-sm">Ver todas <i data-lucide="arrow-right"></i></button>
<button class="btn btn-danger">Excluir</button>
<button class="btn btn-secondary btn-icon" title="Alternar modo escuro"><i data-lucide="moon"></i></button>
```

| Variante | Quando usar |
|---|---|
| `btn-primary` | A ação principal da área (salvar, executar, enviar) |
| `btn-secondary` | Demais ações (exportar, sincronizar, cancelar) |
| `btn-ghost` | Ações terciárias, links de navegação, ícones em linha de tabela |
| `btn-danger` | Ação destrutiva confirmada (dentro do modal de confirmação) |

Tamanhos: padrão 36 px de altura; `btn-sm` 30 px. `btn-icon` deixa o botão quadrado. Ícones dentro de `.btn` ficam em 16 px automaticamente; não passe `w-*`/`h-*`.

Rótulos: verbo no infinitivo, inicial maiúscula, sem caixa-alta ("Enviar por e-mail", "Executar agora").

### Campo

```html
<label for="cnpj" class="field-label">CNPJ</label>
<input id="cnpj" class="input font-mono" placeholder="00.000.000/0000-00">
<p class="field-hint">Use a raiz de 8 dígitos para cobrir matriz e filiais.</p>
```

`.input` vale para `input`, `select` e `textarea` (nesta, acrescente `h-auto py-2`). Ícone à esquerda: envolva em `relative` e use `pl-9` no campo.

### Cartão

```html
<section class="card">
  <header class="card-header">
    <h2 class="card-title">Menções recentes</h2>
    <button class="btn btn-ghost btn-sm">Ver todas</button>
  </header>
  <div class="card-body">…</div>
</section>
```

Para KPIs: `card p-5` + rótulo `text-xs text-neutral-500` + número `text-3xl font-semibold tabular`.

### Badge

```html
<span class="badge">Personalizada</span>
<span class="badge badge-success">Ativa</span>
<span class="badge badge-warning">Pausada</span>
<span class="badge badge-danger">Erro</span>
<span class="badge badge-accent">Seção 1</span>
```

### Aviso (callout)

Superfície neutra (igual a um cartão) com uma faixa de 3 px à esquerda na cor do estado. O texto fica neutro; só a faixa e o ícone carregam cor. Substitui as antigas caixas de fundo colorido translúcido (`bg-amber-50`, `bg-blue-50/50`, `bg-emerald-950/40`…), que tinham contraste ruim, sobretudo no tema escuro.

```html
<div class="callout callout-warning p-4 flex items-start gap-3">
  <i data-lucide="alert-triangle" class="callout-icon w-4 h-4 mt-0.5"></i>
  <div>
    <h4 class="text-sm font-semibold">Portal INLABS em manutenção</h4>
    <p class="text-xs text-neutral-500">As buscas usam o PDF integral do dia.</p>
  </div>
</div>
```

| Tom | Classe | Uso |
|---|---|---|
| Informação | `callout-info` | Dicas, explicações |
| Sucesso | `callout-success` | Teste concluído, atualização disponível |
| Atenção | `callout-warning` | Pendências, contingência |
| Erro | `callout-danger` | Falhas |
| Neutro | só `callout` | Nota sem estado |

**Recolhível.** Para avisos persistentes (como "Integrações pendentes" na Visão geral), use um cabeçalho `.callout-toggle` com a seta `.callout-chevron` (gira com `.is-open`) e o corpo em `x-show`. O cabeçalho recolhido resume o conteúdo numa linha e mantém a ação principal visível. O estado recolhido fica em `localStorage` com a lista de pendências como chave, então o aviso reabre sozinho quando surge uma pendência nova.

Não use fundo colorido em caixas. Fundo tingido fica restrito a `.badge`.

### Opção selecionável

Cartões de escolha (origens da sincronização, layout de pastas): fundo `bg-white`, borda `border-neutral-200`; selecionado troca só a borda para `border-neutral-900` (`dark:border-neutral-200`). Sem fundo colorido.

### Tabela

`.table` em `<table>` aplica cabeçalho em caixa-alta discreta, linhas com borda e hover. CNPJ e datas em `font-mono`.

### Indicador de status

```html
<span class="status-dot status-dot-success"></span> Configurado
```

Variantes: `-success`, `-accent`, `-warning`, `-danger`. Sem brilho e sem pulsar.

### Chave liga/desliga

Mantido o markup existente (`.dash-switch` > `input.dash-switch-input.sr-only` + `.dash-switch-track` > `.dash-switch-thumb`), agora com foco visível e sem brilho no tema escuro.

### Toast

Superfície neutra com barra lateral colorida e ícone no tom do estado (`.toast.toast-success|info|warning|error`). Títulos: "Concluído", "Em andamento", "Atenção", "Erro".

### Marca

`<span class="brand-mark">R</span>` + "Registrale". Substitui o ícone de robô (`bot-message-square`), que reforçava a cara de "app de IA".

---

## 4. Padrões de tela

**Cabeçalho de aba.** Toda aba começa igual:

```html
<div class="flex flex-col md:flex-row md:items-end justify-between gap-4">
  <div>
    <h2 class="text-xl font-semibold tracking-tight">Empresas</h2>
    <p class="text-sm text-neutral-500 mt-1">Clientes monitorados pela raiz do CNPJ.</p>
  </div>
  <div class="flex flex-wrap gap-2">
    <!-- secundárias primeiro, primária por último -->
  </div>
</div>
```

**Barra de filtros.** Um `card p-4` com busca (`flex-1`), selects `input w-auto` e a contagem alinhada à direita (`ml-auto text-xs`).

**Modal.** Overlay `bg-neutral-950/60`, painel `rounded-2xl shadow-2xl`, rodapé com `btn-secondary` (Cancelar) à esquerda da `btn-primary`.

**Estado vazio.** Uma frase em `text-sm text-neutral-500`, centralizada, sem ilustração. Diga o que fazer quando houver ação ("Nenhuma empresa. Sincronize a planilha ou adicione manualmente.").

---

## 5. Conteúdo

- Português do Brasil, frase com inicial maiúscula.
- Sem emojis na interface (💡, 🟢, ✓ etc.). Use ícone Lucide quando precisar de apoio visual.
- Sem jargão de implementação no texto visível: "CNPJs monitorados", não "Monitorados (DAGs)"; "Rotina principal", não "Sistema (Sync)".
- "e-mail" com hífen.
- Reticências como caractere único (…).

---

## 6. Auditoria de novembro/2026

Levantamento feito sobre `index.html` (6.575 linhas) e `login.html` antes da padronização.

### 6.1 Corrigido nesta rodada

| Problema | Antes | Agora |
|---|---|---|
| Duas famílias de cinza misturadas | 1.464 usos de `slate` (frio) + 1.220 de `stone` (quente) | Uma família neutral; `slate` vira apelido |
| Cores de destaque sem regra | 12 famílias, incl. purple, indigo, rose, teal | 5 famílias com papel definido |
| Botões principais de cores diferentes na mesma tela | Azul (Sincronizar), preto (Inserir), verde-pastel (EXCEL), vermelho-pastel (PDF), marrom (E-mail), laranja (Configurar) | `btn-primary` / `btn-secondary` / `btn-ghost` |
| Raios | 7 valores, incl. `rounded-[2rem]` em 9 modais | 4 valores |
| Peso de fonte | 430 `font-bold` + 55 `font-black` | Máximo 600 |
| Rótulos microscópicos em caixa-alta espaçada | 172 textos de 8–10 px, 129 `uppercase tracking-widest` | Mínimo 11 px; caixa-alta só em `<thead>` |
| Brilho neon e pulsação | 13 pontos de status com `shadow-[0_0_12px…]` + `animate-pulse`; regras de "glow" no tema escuro | Ponto sólido de 8 px |
| Micro-animações de "app de IA" | 53 `active:scale-95`, `hover:scale-105` | Removidas |
| Classes mortas | 21 `animate-in`/`fade-in`/`zoom-in-95` (plugin `tailwindcss-animate` nunca foi carregado) | Removidas |
| Campos com padding/raio/fundo variados | ~10 variações (`p-2.5`/`p-3`/`p-4`, `rounded-xl`/`2xl`) | `.input` (58 campos) |
| Rótulos de campo | Overline cinza claro, 10 px | `.field-label` (65 rótulos) |
| Toast | Fundo saturado, borda neon, título em caixa-alta | Superfície neutra + barra de estado |
| Logo de robô | `bot-message-square` | Marca tipográfica "R" |
| Login com outro visual | Fundo `slate-50`, cartão `rounded-3xl`, Inter 900 | Mesmos tokens e componentes do painel |
| Bloco `<style>` de 330 linhas com 124 `!important` | Inline no `index.html` | `registrale.css`, 4 seções comentadas, 46 `!important` restritos à camada legada |
| Emojis na interface | 6 ocorrências | Removidos |
| Cabeçalhos de aba | Só Rotinas e Relatórios tinham título | Empresas ganhou cabeçalho; Visão geral, Rotinas e Relatórios padronizados |
| Caixas de aviso com fundo colorido translúcido | 24 caixas `bg-*-50` / `bg-*-950/40` com texto colorido; contraste ruim no escuro | `.callout` neutro com faixa lateral; aviso de integrações recolhível |
| Menções, Configurações (9 subabas), modais e manual com classes soltas | Cartões `rounded-3xl p-8`, botões `px-5 py-3 rounded-xl` de cores variadas, pílulas coloridas, tabelas com cabeçalho caixa-alta espaçado, ícones em quadro colorido, vários `btn-primary` por área | `.card`, `.btn` (primary/secondary/ghost/danger, `btn-sm`, `btn-icon`), `.badge`, `.status-dot`, `.table`; painéis internos neutros; quadros de ícone neutros com ícone colorido |
| Modais (sincronização, rotina, busca mensal, assistente, onboarding de PDF, sessão, histórico, e-mail, empresa) | Painel `rounded-2xl/3xl`, cabeçalho e rodapé com fundo `slate-50`, `rounded-b-[2rem]` | `.card` + `shadow-2xl`, cabeçalho/rodapé `px-5 py-4` com borda neutra, fundo `bg-neutral-950/60`, um `btn-primary` por modal |
| Manual embutido | Número da seção em quadro colorido (blue, emerald, purple, rose…), títulos em Title Case | Quadros neutros, títulos com inicial maiúscula só na primeira palavra; conteúdo intacto |
| Texto `text-slate-400` sobre branco | 2,5:1 (reprova WCAG AA) | `--text-muted` 4,6:1 |

### 6.2 Pendente (dívida conhecida)

| Item | Por que importa | Sugestão |
|---|---|---|
| **Tailwind via Play CDN** (`cdn.tailwindcss.com`) | O próprio Tailwind avisa que não é para produção: compila no navegador a cada carga e depende de internet. O app é instalado no Windows e deveria abrir offline. | Gerar `static/css/app.css` com o **Tailwind standalone CLI** (binário único, sem Node) no `build.ps1`. O `tailwind.config.js` já está pronto para isso. |
| **Dependências sem versão fixa** (`lucide@latest`, `alpinejs@3.x.x`, `flatpickr` sem versão) | Uma atualização externa pode quebrar ícones ou o Alpine sem nenhuma mudança no código. | Fixar versões e, junto com o item acima, servir os arquivos de `static/vendor/`. |
| **Camada de compatibilidade legada** (seção 4 de `registrale.css`) | Remapeia `bg-white`, `text-slate-*`, `bg-emerald-50` etc. com `!important` para o tema escuro. Funciona, mas esconde regras. | Ao mexer numa tela, troque as classes antigas por componentes e apague a regra correspondente. |
| **`index.html` monolítico** (6.233 linhas, ~3.000 de JS Alpine) | Dificulta revisar e padronizar. | Separar cada aba em `{% include 'tabs/…html' %}` e o JS em `static/js/dashboard.js`, sem mudar comportamento. |
| **Botões e cartões fora do padrão nas telas já migradas** | Restam usos soltos em Visão geral, Empresas e Relatórios (cerca de 45 `font-bold`/`font-black`, 3 `rounded-3xl`, 3 cabeçalhos de tabela antigos, ex.: Relatórios) e nas abas do manual que usam `<table>` do conteúdo. | Passar a mesma varredura (botões, cartões, `<thead>`) nessas abas. |
| **Títulos em "Title Case"** | Menções, Configurações, modais e manual foram corrigidos. Ficam nomes próprios (Google Sheets, Edições Extras, Padrão Registrale) e conteúdo do manual. | Revisar o texto corrido do manual e os rótulos de Visão geral/Empresas/Relatórios. |
| **PWA** (`manifest.json`, `sw.js`, metas `apple-mobile-web-app-*`) | O painel abre em janela própria (pywebview); o service worker não faz cache e não tem função. | Avaliar remoção. |
| **Tema do Flatpickr** (`airbnb.css`) | Não segue os tokens (cores e raio próprios). | Sobrescrever as variáveis do calendário em `registrale.css` ou trocar por `input type="date"`. |
| **Template de e-mail no editor visual** | Usa `Segoe UI`, azul `#06acff` e emoji 📋. É o e-mail enviado ao cliente, fora do escopo do painel. | Tratar separadamente, se desejado. |

---

## 7. Checklist para mudanças de interface

- [ ] Usei `.btn`, `.input`, `.field-label`, `.card`, `.badge` em vez de classes soltas?
- [ ] Há no máximo um `btn-primary` por área?
- [ ] Usei só neutral/ink/success/warning/danger (ou apelidos já existentes)?
- [ ] Nenhum texto abaixo de 11 px, nenhum `uppercase` fora de `<thead>`, nenhum peso acima de 600?
- [ ] Nenhum raio arbitrário, sombra colorida, `scale`, emoji?
- [ ] Testei no tema claro **e** no escuro?
