# Ajustes de UI — aviso de integrações, SMTP, contador de menções e responsividade

> Prompt de execução para um agente (Sonnet). Leia `AGENTS.md` antes de começar.
> Não crie commits, branches nem push. Não altere `src/`.

## Diagnóstico já feito (não precisa refazer)

Tudo foi verificado numa cópia do app (porta 5055, dados copiados) e no código atual.

### A. Aviso "Integrações pendentes" aparece o tempo todo
`templates/index.html` ≈ linhas 235–290 mostram um callout sempre que
`integrationsStatus.all_configured` é falso. O usuário dispensa, mas o aviso volta a cada
mudança, porque a assinatura (`integrationsNoticeSignature()`) muda. Ele tem botão próprio
("Configurar …" → `startIntegrationWizard()`), que é o **assistente antigo**. Hoje já existe o
assistente de primeiro uso em 9 passos (`reopenOnboardingWizard()`, `onboarding_service.py`).

### B. SMTP "desligado" volta a valer como ligado
- Backend: `services/email_service.py::is_smtp_enabled` retorna **True** quando a chave
  `enabled` não existe em `global_settings.smtp`.
- Frontend: `index.html` ≈ linha 4500 faz `if (raw.smtp.enabled === undefined) raw.smtp.enabled = true;`.
- Depois de "Limpar dados" (ou numa instalação nova) a chave some. A tela passa a mostrar o SMTP
  ligado, e qualquer "Salvar" em Configurações grava `enabled: true`. É o estado atual da máquina
  do usuário: `smtp.enabled = true` com o servidor **vazio**. Por isso cada busca gera
  "Erro Envio E-mail — [WinError 10061] conexão recusada", e a rotina exige e-mail para salvar.
- Com o SMTP explicitamente desligado, salvar a rotina sem e-mail **funciona** (testado). O bug é
  o padrão "ligado".

### C. Contador de menções da tela Empresas fica em 0
1. O painel não recarrega dados quando uma execução termina. `pollActivity()` (≈ linha 4731) só
   reagenda o polling. Empresas, menções e KPIs só mudam ao clicar em "Atualizar"
   (`refreshCurrentTab`). Ao recarregar a página, o contador aparece certo (SURGITEC = 1).
2. `routes/companies.py::get_companies_data` conta menções por **CNPJ completo igual**. A regra 1
   do `AGENTS.md` identifica a empresa pela **raiz** (8 primeiros caracteres): menção de uma filial
   ou só pela raiz (`root_only`) não entra na contagem da empresa.

### D. Responsividade e estética
Observado em 900 px e 390 px de largura:
- A sidebar não recolhe sozinha em telas estreitas. Em 390 px ela continua visível e ocupa a tela.
  Deveria virar gaveta (botão de menu), e em larguras médias (< 1024 px) começar recolhida (w-20).
- **Empresas:** os botões do cabeçalho quebram de forma desalinhada. A tabela tem 913 px dentro de
  um contêiner de 568 px, então Menções/Status/Ações ficam escondidos atrás de rolagem horizontal.
  Em telas estreitas, troque por cartões (nome, CNPJ, badge de menções, status, ações) ou fixe a
  coluna Ações.
- **Configurações:** em 900 px o submenu vira uma lista empilhada e o conteúdo da aba some abaixo,
  sem item ativo destacado. Use um seletor (select ou pills roláveis) acima do conteúdo em telas
  estreitas.
- **Limpeza do sistema:** os 4 cartões (Limpar dados / INLABS / histórico / menções) têm títulos
  que transbordam o cartão mesmo no desktop (print do usuário). Use grid responsiva
  (`grid-cols-2 lg:grid-cols-4`), quebra de linha e altura mínima.
- **Cabeçalho do topo** (status, última sync, botões): quebra em várias linhas em 900 px. Agrupe
  e deixe os botões só com ícone abaixo de `md`.
- **Inputs de arquivo nativos:** `index.html` linhas ≈1910, 1914 (Configurações → importar) e
  ≈3879, 3883 (assistente, passo 1) usam `<input type="file" class="input">`, com o botão
  "Escolher arquivo" do navegador. Troque por um componente do design system: input escondido +
  `<label class="btn btn-secondary">` com ícone `upload`, e o nome do(s) arquivo(s) escolhido(s) ao
  lado, ou uma dropzone. Mantenha os mesmos `id`s ou ajuste o JS que os lê.
- O cartão da rotina mostra a seção crua "SECAO 1". Exiba o rótulo amigável ("Seção 1").

## Tarefas

### T1. Remover o assistente antigo e o aviso permanente
1. Remova o callout "Integrações pendentes" da Visão geral e o fluxo `startIntegrationWizard()`
   / `openIntegrationTarget` usado só por ele (confira se mais algo usa antes de apagar). O
   assistente de 9 passos continua sendo o único assistente.
2. Substitua por um aviso que **só** aparece em caso de problema real:
   - configuração que existia e foi apagada: por exemplo, a rotina principal sem e-mails com o
     SMTP ligado, ou o Google Sheets/GestãoClick com sincronização automática ligada mas sem
     credenciais;
   - erro recente de integração no histórico (`sync_history`, últimas 24 h): "Erro Envio E-mail",
     "Erro (Busca Mensal)", falha de sincronização.
   Integração **desligada** nunca gera aviso. O aviso diz o problema em uma linha e leva direto à
   aba certa de Configurações. Pode ser dispensado e só volta se surgir um problema novo.
3. Ajuste `/api/integrations_status` (ou crie `/api/health_alerts`) para devolver só esses
   problemas.

### T2. SMTP desligado por padrão e coerente
1. `is_smtp_enabled`: sem a chave `enabled` → **False**. Com `enabled: true` e sem `server` →
   trate como não pronto: não tente enviar e registre um único evento claro por execução
   ("SMTP ligado sem servidor configurado"), não um erro de conexão por rotina.
2. Remova o padrão `true` do frontend (≈ linha 4500). A tela e o backend usam a mesma regra.
3. Garanta que "Limpar dados" e a instalação nova gravem `smtp.enabled = false`.
4. Rotina (principal e personalizadas): com o SMTP desligado, e-mail e assunto são opcionais no
   frontend e no backend (já é assim; mantenha e cubra com teste).
5. **Corrija a instalação do usuário:** faça backup do `database.db` e grave
   `global_settings.smtp.enabled = false` (o servidor está vazio). Não toque nos outros campos nem
   exiba senhas.

### T3. Contador de menções
1. `get_companies_data`: agregue por **raiz do CNPJ** (8 primeiros caracteres normalizados,
   aceitando CNPJ alfanumérico), somando matriz, filiais e menções só pela raiz. Reutilize
   `src/utils/cnpj.py` (sem alterá-lo) ou um helper do painel.
2. No frontend, quando `fetchActivity` mostrar a transição "ocupado → ocioso", recarregue
   KPIs, menções, empresas e histórico uma vez, sem esperar o clique em "Atualizar".

### T4. Responsividade e estética
Implemente os itens da seção D. Valide em 1280, 1024, 900, 768 e 390 px de largura, nas abas
Visão geral, Menções, Rotinas, Empresas, Relatórios, Configurações (todas as subabas) e no
assistente (todos os passos), em modo claro e escuro. Nenhum texto pode transbordar o cartão,
nenhum botão pode ficar cortado, e não pode haver rolagem horizontal da página. Siga o design
system (`docs/tecnico/06_design_system.md`, `static/css/registrale.css`).

### T5. Varredura extra
Navegue no app (cópia na porta 5055 com dados copiados para uma pasta temporária, via
`REGISTRALE_DATA_DIR`/`REGISTRALE_DB_PATH`; nunca a instalação real) procurando mais problemas do
mesmo tipo: textos técnicos crus na tela, botões que não fazem nada, estados vazios sem mensagem,
toasts com tipo `undefined`, item ativo da sidebar errado, modais que não cabem na tela. Corrija o
que for pequeno e liste no relatório o que ficou de fora.

### T6. Testes, instalação e documentação
- Testes offline para: `is_smtp_enabled` (sem chave → False; ligado sem servidor → não pronto),
  aviso só com problema real (integração desligada não gera aviso), contagem por raiz (matriz +
  filial + só raiz) e rotina salva sem e-mail com o SMTP desligado.
- `pytest -m "not live"` com `.venv\Scripts\python.exe -m pytest`. Sem regressões.
- Copie os arquivos alterados para `%LOCALAPPDATA%\Programs\Registrale\app\` (mesmos caminhos),
  apague os `__pycache__` correspondentes, reinicie o app (como no hotfix anterior) e confirme que
  `http://127.0.0.1:5000` responde.
- Registre no `docs/projeto/PLANO.md` e no `CHANGELOG.md` (1.3.2).

## Critério de aceite
- A Visão geral não mostra aviso nenhum quando não há problema; integração desligada não conta.
- Com o SMTP desligado, a rotina salva sem e-mail e as buscas não registram erro de e-mail.
- O contador da SURGITEC (e de qualquer empresa com menção de filial) aparece sem recarregar a
  página depois de uma busca.
- Nada transborda nem fica cortado em 900 px e 390 px. Os inputs de arquivo seguem o design system.
- Relatório final: arquivos alterados, larguras/telas verificadas (com prints salvos na pasta
  temporária), testes, e o que não foi feito.
