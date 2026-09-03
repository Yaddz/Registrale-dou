# Manual do Usuário — Ro-DOU Dashboard

> **Guia Oficial de Utilização, Configurações, Rotinas de Busca e Relatórios**  
> *Plataforma Registrale de Monitoramento do Diário Oficial da União (DOU)*

---

## 📑 Índice Rápido de Navegação

1. [Visão Geral e Primeiros Passos](#1-visão-geral-e-primeiros-passos)
   - [1.1. O que é o Ro-DOU Dashboard?](#11-o-que-é-o-ro-dou-dashboard)
   - [1.2. Acesso ao Sistema e Níveis de Permissão](#12-acesso-ao-sistema-e-níveis-de-permissão)
   - [1.3. Conhecendo a Tela Principal](#13-conhecendo-a-tela-principal)
   - [1.4. Alternando entre Modo Claro e Modo Escuro](#14-alternando-entre-modo-claro-e-modo-escuro)
   - [1.5. Configuração Inicial da Rotina Principal](#15-configuração-inicial-da-rotina-principal)
2. [Gestão de Empresas Monitoradas](#2-gestão-de-empresas-monitoradas)
   - [2.1. Como Localizar Empresas Cadastradas](#21-como-localizar-empresas-cadastradas)
   - [2.2. Como Cadastrar uma Nova Empresa Manualmente](#22-como-cadastrar-uma-nova-empresa-manualmente)
   - [2.3. Como Ativar ou Pausar o Monitoramento de uma Empresa](#23-como-ativar-ou-pausar-o-monitoramento-de-uma-empresa)
   - [2.4. Como Consultar o Histórico de Menções de um CNPJ](#24-como-consultar-o-histórico-de-menções-de-um-cnpj)
   - [2.5. Como Editar ou Excluir uma Empresa](#25-como-editar-ou-excluir-uma-empresa)
3. [Como Criar e Gerenciar Rotinas de Busca](#3-como-criar-e-gerenciar-rotinas-de-busca)
   - [3.1. Entendendo os Tipos de Rotinas](#31-entendendo-os-tipos-de-rotinas)
   - [3.2. Passo a Passo: Como Criar uma Nova Rotina de Busca](#32-passo-a-passo-como-criar-uma-nova-rotina-de-busca)
   - [3.3. Como Disparar uma Busca Imediata ("Rodar Agora")](#33-como-disparar-uma-busca-imediata-rodar-agora)
   - [3.4. Como Disparar Busca com Data Retroativa (Reprocessamento / Auditoria)](#34-como-disparar-busca-com-data-retroativa-reprocessamento--auditoria)
   - [3.5. Como Fazer uma Busca Mensal Completa](#35-como-fazer-uma-busca-mensal-completa)
   - [3.6. Como Pausar, Reativar ou Excluir uma Rotina](#36-como-pausar-reativar-ou-excluir-uma-rotina)
4. [Acompanhamento de Menções e Publicações](#4-acompanhamento-de-menções-e-publicações)
   - [4.1. Visualizando o Feed de Publicações em Tempo Real](#41-visualizando-o-feed-de-publicações-em-tempo-real)
   - [4.2. Entendendo os Destaques e Acessando o Ato Oficial](#42-entendendo-os-destaques-e-acessando-o-ato-oficial)
   - [4.3. Gerenciando Menções (Marcar Lidas / Excluir)](#43-gerenciando-menções-marcar-lidas--excluir)
5. [Geração de Relatórios e Exportações](#5-geração-de-relatórios-e-exportações)
   - [5.1. Filtrando Publicações por Período, Empresa e Seção](#51-filtrando-publicações-por-período-empresa-e-seção)
   - [5.2. Como Exportar para Planilha Excel (.xlsx)](#52-como-exportar-para-planilha-excel-xlsx)
   - [5.3. Como Gerar Relatório em PDF Diagramado](#53-como-gerar-relatório-em-pdf-diagramado)
   - [5.4. Como Enviar Relatórios por E-mail Diretamente pelo Painel](#54-como-enviar-relatórios-por-e-mail-diretamente-pelo-painel)
6. [Configurações do Sistema e Integrações (Acesso Master)](#6-configurações-do-sistema-e-integrações-acesso-master)
   - [6.1. Gestão de Usuários e Acessos](#61-gestão-de-usuários-e-acessos)
   - [6.2. Como Configurar a Integração com Google Sheets](#62-como-configurar-a-integração-com-google-sheets)
   - [6.3. Como Configurar o Servidor de E-mail (SMTP)](#63-como-configurar-o-servidor-de-e-mail-smtp)
   - [6.4. Como Criar e Personalizar Templates de E-mail](#64-como-criar-e-personalizar-templates-de-e-mail)
   - [6.5. Como Conectar ao ERP GestãoClick](#65-como-conectar-ao-erp-gestãoclick)
   - [6.6. Limpeza e Manutenção do Sistema](#66-limpeza-e-manutenção-do-sistema)
7. [Perguntas Frequentes (FAQ) & Dúvidas do Dia a Dia](#7-perguntas-frequentes-faq--dúvidas-do-dia-a-dia)

---

## 1. Visão Geral e Primeiros Passos

### 1.1. O que é o Ro-DOU Dashboard?
O **Ro-DOU Dashboard** é o sistema central da Registrale projetado para automatizar a leitura diária e histórica do **Diário Oficial da União (DOU)**. Ele identifica publicações, atos normativos, editais, licitações e atos de pessoal que mencionam as empresas clientes cadastradas ou termos estratégicos definidos pela sua equipe.

---

### 1.2. Acesso ao Sistema e Níveis de Permissão

Para acessar o sistema, informe seu usuário e senha na tela inicial de login:

* **Perfil Usuário Comum (`user`):**
  * Visualiza o Painel Geral e KPIs.
  * Acompanha o feed de menções em tempo real.
  * Consulta a lista de empresas e seus históricos individuais.
  * Dispara rotinas de busca diárias, retroativas e mensais.
  * Gera relatórios em Excel, PDF e envia e-mails.
* **Perfil Administrador (`master`):**
  * Possui todas as permissões de usuário comum.
  * Gerencia os usuários internos do sistema.
  * Configura credenciais do Google Sheets, SMTP, GestãoClick e INLABS.
  * Cria e edita templates dinâmicos de e-mail.
  * Executa rotinas de limpeza de dados e diagnóstico de armazenamento.

> [!NOTE]
> A sessão dura **30 minutos de inatividade**. Quando faltar 1 minuto para expirar, o painel exibirá um aviso permitindo estender o acesso com um clique.

> [!TIP]
> **Instalação como Aplicativo Desktop (PWA):** Você pode instalar o Ro-DOU Dashboard como um app nativo no Windows/macOS. No Google Chrome ou Microsoft Edge, clique no ícone **⊕ (Instalar Registrale)** na barra de endereços para fixar o ícone na sua barra de tarefas e abrir o sistema em uma janela dedicada sem poluição visual do navegador.

---

### 1.3. Conhecendo a Tela Principal

Ao entrar no sistema, você visualiza a aba **Visão Geral** com:

1. **Cards de Indicadores (KPIs):**
   * **Empresas Registradas:** Total de clientes na base.
   * **Monitorados (DAGs):** Empresas que estão ativas na busca diária.
   * **Menções Hoje:** Publicações encontradas na edição de hoje do DOU.
   * **Este Mês:** Total de matérias encontradas no mês corrente.
2. **Barra Superior de Status:**
   * **Última Sync:** Data e hora em que a lista de clientes foi atualizada com o ERP ou Google Sheets.
   * **Última Pesquisa:** Horário da última busca executada no DOU.
3. **Feed de Menções Recentes:**
   * Lista das últimas matérias encontradas, com o nome da empresa, seção do DOU, trecho em destaque e botão para ler o documento oficial.
4. **Histórico de Atividades:**
   * Linha do tempo com os últimos eventos executados (sincronizações, downloads e disparos).

---

### 1.4. Alternando entre Modo Claro e Modo Escuro

No topo superior direito, clique no botão de alternância de tema (**ícone de Sol / Lua**) para mudar instantaneamente entre o **Modo Claro** e o **Modo Escuro (Dark Mode)**. O sistema salva sua preferência no navegador.

---

### 1.5. Assistente de Configuração de Integrações (Setup Wizard)

O Ro-DOU Dashboard conta com um **Assistente Inteligente de Configuração (Setup Wizard)** que realiza um diagnóstico contínuo de todas as integrações essenciais do sistema.

Se houver qualquer integração pendente, um **banner informativo com badges interativos** é exibido no topo da aba Visão Geral:

* **Badges de Diagnóstico:**
  * 🟢 **Verde (Configurado):** A integração está completa e validada.
  * 🟡 **Amarelo (Pendente):** A integração requer preenchimento de parâmetros obrigatórios.
  * Clicar em qualquer badge direciona o operador imediatamente para o formulário correspondente (com rolagem suave e foco no card).

* **As 4 Integrações Monitoradas pelo Assistente:**
  1. **Rotina Principal (`Pesquisa_cnpj.yaml`):** Exige e-mails de destino e assunto para o disparo diário dos relatórios consolidados. Em instalações limpas, a rotina inicia sem dados fictícios (em branco) e o sistema abre diretamente o modal padrão de rotinas para preenchimento.
  2. **Servidor SMTP (E-mail):** Configuração de Host, Porta, Usuário, Senha e Remetente para envio de alertas automáticos. Possui preservação segura de senhas preexistentes, higienização automática de espaços em senhas de app do Gmail, diagnósticos aprimorados e suporte a teste imediato de conexão.
  3. **Planilha Google Sheets:** Conexão via Conta de Serviço (Service Account) com URL da planilha (`spreadsheet_url`), nome da aba e mapeamento de colunas para sincronização contínua de clientes.
  4. **Credenciais INLABS:** Usuário e senha de acesso ao portal da Imprensa Nacional para download automatizado das edições do DOU.

* **Fluxo Passo a Passo do Assistente (Wizard):**
  1. Clique no botão de ação destacado no banner (ex: **"Configurar: Rotina Principal"** ou **"Configurar: Servidor SMTP"**). Para a rotina principal, o sistema abre o modal padrão de edição de rotinas.
  2. Preencha os campos obrigatórios e utilize o botão de **Testar Conexão** quando disponível.
  3. Ao salvar, uma janela modal de confirmação (**"Etapa Salva com Sucesso!"**) exibirá a próxima integração pendente.
  4. Clique em **"Configurar Próximo"** para avançar ou em **"Concluir Depois"** se desejar finalizar em outro momento.
  5. Quando todas as 4 integrações estiverem concluídas, o banner de pendências desaparecerá automaticamente.

---

## 2. Gestão de Empresas Monitoradas

Na barra lateral, clique em **Empresas** para gerenciar a base de clientes monitorados.

### 2.1. Como Localizar Empresas Cadastradas
* Utilize a **Barra de Busca** no topo da tabela para pesquisar instantaneamente por **Razão Social**, **Nome Fantasia** ou **CNPJ** (com ou sem pontuação).
* Use os filtros de **Origem** para visualizar empresas vindas do *GestãoClick*, do *Google Sheets* ou cadastradas *Manualmente*.

---

### 2.2. Como Cadastrar uma Nova Empresa Manualmente
1. Na aba **Empresas**, clique no botão **+ Nova Empresa**.
2. Preencha o **Nome / Razão Social** da empresa.
3. Digite o **CNPJ** (a máscara de formatação é aplicada automaticamente).
4. Deixe marcada a opção **"Monitorar no DOU"** para que a empresa seja incluída nas varreduras diárias.
5. Clique em **Salvar Empresa**.

---

### 2.3. Como Ativar ou Pausar o Monitoramento de uma Empresa
* Na tabela de empresas, localize a coluna **Status**.
* Clique na **chave seletora (Toggle)** para ativar (azul) ou desativar (cinza) o monitoramento daquela empresa.
* Empresas desativadas permanecem salvas na base histórica, mas não consomem processamento nas buscas diárias do DOU.

---

### 2.4. Como Consultar o Histórico de Menções de um CNPJ
1. Na linha da empresa desejada, clique no botão **Histórico** (ícone de relógio/histórico).
2. Será aberta uma janela com a linha do tempo de todas as matérias do DOU já encontradas para aquele CNPJ.
3. Você pode clicar no link para ver a publicação original ou usar o botão **Enviar por Email** para disparar esse histórico para um destinatário.

---

### 2.5. Como Editar ou Excluir uma Empresa
* **Editar:** Clique no botão de lápis na linha da empresa, faça os ajustes de nome ou status e clique em **Salvar Alterações**.
* **Excluir:** Usuários administradores (`master`) podem clicar no botão de lixeira para remover a empresa da base de monitoramento.

---

## 3. Como Criar e Gerenciar Rotinas de Busca

Na barra lateral, clique em **Rotinas de Busca** para configurar como e quando o sistema varre o Diário Oficial da União.

---

### 3.1. Entendendo os Tipos de Rotinas

* **Rotina Principal do Sistema (`Pesquisa_cnpj_sync`):**
  * Varre automaticamente todas as empresas ativas cadastradas no sistema.
  * O sistema divide a lista em blocos escaláveis de até **1.500 CNPJs** por bloco de busca para garantir alto desempenho e resiliência no Airflow.
* **Rotinas Personalizadas:**
  * Rotinas criadas por você para buscar termos específicos, palavras-chave de licitações, nomes de sócios ou monitorar atos de órgãos públicos específicos.

---

### 3.2. Passo a Passo: Como Criar uma Nova Rotina de Busca

1. Na aba **Rotinas de Busca**, clique no botão **+ Nova Rotina**.
2. **Nome da Rotina:** Digite um nome claro (ex: `Monitoramento Licitações TI`, `Busca ANVISA Medicamentos`).
3. **Agendamento (Horário / Cron):**
   * Escolha o padrão de execução (ex: `0 8 * * *` para rodar todos os dias às 08:00).
4. **Seções do DOU:**
   * Marque as seções desejadas:
     * **Seção 1:** Atos Normativos, Resoluções, Decretos e Portarias.
     * **Seção 2:** Atos de Pessoal, Nomeações e Exonerações.
     * **Seção 3:** Contratos, Editais, Licitações, Avisos e Extratos.
5. **Termos de Busca:**
   * Digite os termos ou palavras-chave desejadas separados por vírgula (ex: `pregão eletrônico, registro de preços, tecnologia`).
6. **Tipo de Busca (Busca por termo exato / aproximada):**
   * **Desmarcado (Recomendado para CNPJs e termos com pontuação):** Realiza busca flexível, permitindo encontrar tanto formatos pontuados (`09.364.298/0001-93`) quanto unificados.
   * **Marcado:** Aplica correspondência estrita com aspas (`"..."`).
7. **Filtro por Órgãos (Opcional):**
   * Especifique ministérios, agências reguladoras ou autarquias que deseja filtrar (ex: `ANVISA, Ministério da Saúde`).
8. **E-mails de Notificação:**
   * Digite os e-mails que devem receber alertas automáticos quando forem encontradas publicações nesta rotina.
9. Clique em **Salvar Configurações**.

> [!NOTE]
> Todas as novas rotinas utilizam por padrão o **INLABS** como fonte de dados e replicam automaticamente os e-mails de destino cadastrados na rotina principal. Qualquer alteração realizada e salva no painel é sincronizada **imediatamente** com a DAG do Airflow.

---

### 3.3. Como Disparar uma Busca Imediata ("Rodar Agora")
* Ao lado da rotina desejada, clique no botão **Rodar Agora** (ícone de Play).
* O sistema iniciará a varredura da edição de hoje do Diário Oficial imediatamente em segundo plano.

---

### 3.4. Como Disparar Busca com Data Retroativa (Reprocessamento / Auditoria)
1. Ao lado da rotina desejada (ou na rotina principal `Pesquisa_cnpj_sync`), clique no botão **Data Lógica / Calendário** (ícone de calendário).
2. O modal inteligente de disparo será exibido:
   * **Entrada Flexível de Data:** Digite no formato brasileiro padrão `DD/MM/AAAA` (com máscara automática), no formato ISO `AAAA-MM-DD` ou clique no campo para abrir o **Calendário Flutuante**.
   * **Detecção Automática de Feriados e Finais de Semana:** Se a data selecionada for um sábado, domingo ou feriado nacional (ex: Tiradentes, Carnaval, Corpus Christi, Natal), o sistema avisa em destaque que não há circulação regular do DOU.
   * **Detecção de Histórico (> 120 dias):** Se a data for anterior a 120 dias da data atual, o sistema informa que a pesquisa será realizada diretamente via **API Oficial do DOU**, dispensando arquivos locais do INLABS.
   * **Execução Hoje:** Deixe o campo em branco para rodar a rotina para o dia corrente.
3. Clique em **Iniciar Busca**. O sistema normaliza a data e inicia a varredura em segundo plano.

---

### 3.5. Como Fazer uma Busca Mensal Completa

1. No topo da tela de rotinas, clique no botão **Busca Mensal**.
2. Selecione o **Mês** e o **Ano** desejados e clique em **Verificar e Iniciar**.
3. **Diagnóstico Inteligente de Disponibilidade:**
   * **Mês Completo no Banco:** A busca inicia imediatamente para todos os dias úteis do mês.
   * **Matérias Disponíveis para Download (dentro de 120 dias):** O modal exibe a quantidade de dias que serão baixados do INLABS antes do processamento. O download de múltiplos dias é executado com reaproveitamento de sessão segura, evitando bloqueios de taxa de requisições.
   * **Meses Históricos (fora da janela de 120 dias):** O sistema detecta automaticamente que os dados não estão mais no portal INLABS e realiza a busca diretamente via **API Oficial do DOU**.
   * **Cenário Misto (Mês Quebrado):** Quando um mês possui ALGUNS dias já no banco local INLABS mas OUTROS dias estão fora da janela de 120 dias, o modal de confirmação exibe um sumário visual com 3 categorias:
     * ✅ **No Banco**: Dias já baixados e armazenados localmente no INLABS.
     * 📥 **Baixar INLABS**: Dias ausentes dentro da janela de 120 dias, baixados em lote.
     * 🌐 **Via API DOU**: Dias históricos fora dos 120 dias, pesquisados via API Oficial do DOU.
   * O usuário pode optar por prosseguir com a execução mista completa ou pesquisar apenas os dias já disponíveis no INLABS.
4. Confirme a opção desejada para iniciar o processamento em segundo plano.

---

### 3.6. Como Pausar, Reativar ou Excluir uma Rotina
* **Pausar/Reativar:** Use a chave seletora (Toggle) ao lado do nome da rotina.
* **Editar:** Clique no botão de engrenagem para alterar termos, seções ou e-mails.
* **Excluir:** Clique no botão de lixeira (disponível apenas em rotinas personalizadas).

---

## 4. Acompanhamento de Menções e Publicações

Na barra lateral, clique em **Todas as Menções** para auditar todas as ocorrências encontradas.

### 4.1. Visualizando o Feed de Publicações em Tempo Real
* A lista exibe a data da publicação, o nome da empresa, o CNPJ e o badge indicando a Seção do DOU (`Seção 1`, `Seção 2` ou `Seção 3`).
* **Busca Inteligente Unificada:** O campo de pesquisa permite buscar por Razão Social, CNPJ (com ou sem pontuação), data específica (`28/08/2026`), mês por extenso (`agosto`, `08/2026`) ou palavras contidas no trecho da publicação.
* Quando uma nova publicação é detectada pelo sistema, o contador na barra lateral acende em vermelho e um alerta sonoro suave é emitido.

---

### 4.2. Entendendo os Destaques e Acessando o Ato Oficial
* Cada card exibe o **Trecho Localizado**, destacando a razão social ou o CNPJ encontrado no texto oficial.
* Clique no botão **Ver Publicação Completa** para abrir o documento oficial original diretamente no portal da Imprensa Nacional (`in.gov.br`).

---

### 4.3. Gerenciando Menções (Marcar Lidas / Excluir)
* Clique sobre qualquer menção para abrir os detalhes completos.
* Você pode selecionar uma ou várias menções usando as caixas de seleção (checkbox) para exportar ou remover registros antigos.

---

## 5. Geração de Relatórios e Exportações

Na barra lateral, clique em **Relatórios** para gerar documentos corporativos para auditoria ou envio a clientes.

---

### 5.1. Filtrando Publicações por Período, Empresa e Seção

1. **Atalhos de Período:** Clique em um dos botões rápidos:
   * `Hoje` | `Últimos 7 dias` | `Este Mês` | `Últimos 30 dias` | `Ano Atual`
   * Ou selecione uma **Data Inicial** e **Data Final** no calendário.
2. **Filtro de Busca Global:** Digite o nome da empresa, CNPJ, data (`28/08/2026`), mês por extenso (`agosto`) ou palavras-chave do trecho para gerar um relatório segmentado.
3. **Filtro por Seção:** Selecione apenas as seções de interesse (Seção 1, 2 ou 3).

---

### 5.2. Como Exportar para Planilha Excel (.xlsx)
* Com os filtros aplicados, clique no botão verde **EXCEL** no topo direito.
* O sistema gera e baixa uma planilha formatada com cabeçalho Registrale, dados da empresa, seção, resumo do texto e links clicáveis para o DOU.

---

### 5.3. Como Gerar Relatório em PDF Diagramado
* Com os filtros aplicados, clique no botão vermelho **PDF** no topo direito.
* O sistema gera um relatório executivo pronto para impressão ou envio ao cliente, diagramado com logotipo, resumo de menções e trechos em destaque.

---

### 5.4. Como Enviar Relatórios por E-mail Diretamente pelo Painel
1. Clique no botão **Enviar por Email**.
2. Selecione o modelo de mensagem desejado no campo **Template**.
3. Digite o e-mail dos destinatários (separados por vírgula).
4. Revise o assunto e visualize o preview do e-mail.
5. Clique em **Enviar Email**.

---

## 6. Configurações do Sistema e Integrações (Acesso Master)

> [!IMPORTANT]
> A aba **Configurações** fica visível na barra lateral apenas para usuários administradores (`master`).

---

### 6.1. Gestão de Usuários e Acessos
Na sub-aba **Usuários**:
* Para criar um novo acesso, informe o nome de usuário, a senha e selecione o papel (`master` para administradores ou `user` para operadores).
* Para revogar um acesso, clique no botão de excluir ao lado do usuário desejado.

---

### 6.2. Como Configurar a Integração com Google Sheets

Permite que sua equipe mantenha uma planilha no Google Drive com os clientes a serem monitorados, sem necessidade de cadastros manuais repetitivos:

1. **Configuração no Google Cloud:**
   * No Google Cloud Console, ative a **Google Sheets API v4**.
   * Crie uma **Conta de Serviço (Service Account)** e faça o download da chave JSON.
   * Copie o e-mail da Conta de Serviço (ex: `meu-sync@projeto.iam.gserviceaccount.com`).
   * Abra sua planilha no Google Drive, clique em **Compartilhar** e adicione o e-mail copiado com acesso de **Leitor**.
2. **Configuração no Dashboard:**
   * Cole a **URL completa da Planilha** (ex: `https://docs.google.com/spreadsheets/d/.../edit`).
   * Digite o **Nome da Página/Aba** (ex: `Página1` ou `Clientes`).
   * Cole o conteúdo do arquivo **Credenciais JSON**.
   * Escolha a **Orientação dos Dados**:
     * `Linhas`: Cada linha da planilha é uma empresa (cabeçalho na Linha 1).
     * `Colunas`: Cada coluna é uma empresa (cabeçalhos na Coluna A).
   * Informe o nome exato dos cabeçalhos nos campos **Coluna Razão Social** e **Coluna CNPJ**.
   * Ative o toggle **Sincronização Automática** e defina o intervalo (ex: a cada 1 hora ou diariamente).
   * **Apagar Registros Obsoletos (Toggle):** Ative esta opção caso deseje que empresas com origem Google Sheets que forem excluídas da planilha sejam automaticamente apagadas do banco de dados e removidas do monitoramento do DOU durante as sincronizações.
3. **Validação:**
   * Clique em **Testar Conexão e Prévia** para ver as primeiras linhas lidas da planilha.
   * Clique em **Salvar Configurações**.

---

### 6.3. Como Configurar o Servidor de E-mail (SMTP)
Na sub-aba **Integrações Gerais** (ou pelo modal de configuração do Assistente):
* **Servidor:** Endereço SMTP (ex: `smtp.gmail.com`, `smtp.office365.com` ou `email-smtp.us-east-1.amazonaws.com`).
* **Porta:** `587` (STARTTLS - padrão recomendado) ou `465` (SSL).
* **Usuário e Senha:** E-mail da conta e a senha (ou Senha de Aplicativo de 16 dígitos se usar autenticação em 2 etapas no Gmail/Google Workspace ou Microsoft 365).
  > [!TIP]
  > **Preservação Inteligente de Senhas:** Se você já salvou uma senha anteriormente, pode atualizar os outros campos (servidor, porta, remetente) deixando o campo de senha em branco. O sistema preservará a senha salva com segurança, sem apagá-la.
* **E-mail de Envio (From):** E-mail que aparecerá no remetente das notificações (ex: `notificacoes@registrale.com.br`).
* **Testar Envio:** Digite um e-mail de destino e clique em **Enviar Email de Teste** (ou use o botão de teste direto no modal da rotina principal). O teste valida a conexão TLS/SSL, autenticação e entrega da mensagem em tempo real.
* **Sincronização com o Airflow:** Ao salvar, o sistema sincroniza os dados no arquivo `.env` e atualiza a conexão `smtp_default` no Airflow de forma automática e transparente.

---

### 6.4. Como Criar e Personalizar Templates de E-mail
Na sub-aba **Templates de E-mail** (Menu Configurações > Templates):

O Ro-DOU Dashboard possui um poderoso **Editor Visual WYSIWYG Integrado** que permite criar, editar e pré-visualizar modelos de e-mail profissionais em tempo real sem precisar mexer em código:

1. **Campos do Modelo:**
   * **Nome do Template:** Identificação interna do modelo (ex: `Alerta DOU Padrão`, `Resumo Semanal Diretoria`).
   * **Assunto do E-mail:** Título da mensagem que será enviada. Suporta tags dinâmicas (ex: `Alerta DOU - Nova Publicação de {empresa}`).

2. **Modos de Trabalho:**
   * 🖊️ **Editor Visual (Preview):** Edição direta e interativa no próprio layout do e-mail, com formatação rica em tempo real.
   * 👁️ **Demonstração Real:** Simula a renderização final do e-mail com dados de exemplo reais e destaque amarelo aplicado.
   * 💻 **Código HTML:** Edição direta do código-fonte HTML para ajustes avançados.

3. **Barra de Ferramentas do Editor Visual:**
   * **Formatação de Texto:** Negrito (**B**), Itálico (*I*), Sublinhado (<u>U</u>) e Limpar Formatação.
   * 🟡 **Destaque Amarelo Estilo DOU:** Aplica ou remove instantaneamente a marcação amarela (`#FFA`) no texto ou variável selecionada, replicando a identidade visual das menções do Diário Oficial.
   * **Títulos e Parágrafos:** Seleção rápida entre Parágrafo, Título (H1), Subtítulo (H2) e Seção (H3).
   * **Alinhamento:** Alinhar à Esquerda, Centralizar ou Alinhar à Direita.
   * ↩️ / ↪️ **Desfazer e Refazer:** Atalhos rápidos para desfazer (`Ctrl+Z`) ou refazer (`Ctrl+Y`) ações de edição.

4. **Menu de Variáveis Dinâmicas (`+ Inserir Variável`):**
   * Clique no botão **+ Inserir Variável** na barra de ferramentas para abrir o menu suspenso e inserir automaticamente tags dinâmicas na posição do cursor:
     * `{content}`: Bloco completo com a estrutura de matérias formatadas do DOU.
     * `{empresa}`: Razão Social da empresa cliente.
     * `{cnpj}`: CNPJ formatado do cliente.
     * `{secao}`: Seção do DOU (`Seção 1`, `Seção 2` ou `Seção 3`).
     * `{data}`: Data de circulação da matéria no DOU.
     * `{trecho}`: Trecho oficial da publicação com o termo em destaque.
     * `{link}`: Link direto e oficial para o ato na Imprensa Nacional.

5. Clique em **Salvar Template** para gravar as alterações. Você pode criar múltiplos modelos e selecioná-los ao disparar relatórios por e-mail.

---

### 6.5. Como Conectar ao ERP GestãoClick
Na sub-aba **Integrações Gerais**:
* Insira o **Token de Acesso** e a **Chave Secreta** gerados no GestãoClick.
* Ative o toggle de sincronização automática. O sistema importará novos clientes cadastrados no ERP automaticamente.
* **Validação de Credenciais na Sincronização:** Se você tentar sincronizar sem ter preenchido o Access Token ou Secret Token, o sistema exibirá um alerta em vermelho bloqueando o processo e orientando a configurar as credenciais.

---

### 6.6. Limpeza e Manutenção do Sistema
Na sub-aba **Limpeza do Sistema**:
* **Limpar INLABS:** Remove edições antigas do banco com mais de 120 dias para liberar espaço em disco.
* **Limpar Histórico:** Limpa a linha do tempo de sincronizações passadas.
* **Limpar Menções:** Remove menções arquivadas.

---

## 7. Perguntas Frequentes (FAQ) & Dúvidas do Dia a Dia

### ❓ "O que é o banner amarelo pedindo para configurar a rotina principal?"
**Resposta:** Ao acessar o sistema pela primeira vez (ou após uma reinstalação limpa), a rotina principal de monitoramento inicia limpa (sem dados fictícios). Clique em **"Configurar agora"** no banner amarelo para abrir o modal de configuração padrão da rotina e informar os e-mails de destino e o assunto. Após salvar, o status da rotina passa para configurado e o assistente avança para as demais etapas.

---

### ❓ "Posso pesquisar meses antigos que estão fora da janela de 120 dias do INLABS?"
**Resposta:** Sim. O sistema detecta automaticamente que os dias estão fora da janela do INLABS e realiza a pesquisa diretamente via **API Oficial do DOU**. No modal de confirmação da busca mensal, esses dias aparecem na categoria **"Via API DOU"** com um ícone de globo (🌐).

---

### ❓ "Quanto tempo leva uma busca mensal histórica via API Oficial do DOU e como acompanhar?"
**Resposta:** Como a API Oficial do DOU consulta a Imprensa Nacional termo a termo para cada dia útil do mês pesquisado, o processamento pode levar de 5 a 15 minutos dependendo da quantidade de empresas monitoradas. O sistema processa tudo de forma assíncrona e protegida em segundo plano no Airflow. Você pode acompanhar o andamento diretamente no **Histórico de Eventos** da barra lateral, que registrará o evento **"Busca Mensal Concluída"** assim que todos os dias forem consolidados, atualizando automaticamente os KPIs e a aba **Todas as Menções**.

---

### ❓ "Cadastrei uma empresa hoje, quando ela começará a ser buscada?"
**Resposta:** Imediatamente nas próximas execuções automáticas. Se quiser conferir a edição do dia de hoje para essa nova empresa imediatamente, vá em **Rotinas de Busca** e clique em **Rodar Agora** na rotina `Pesquisa_cnpj_sync`.

---

### ❓ "Como monitorar uma palavra-chave ou termo em vez de uma empresa?"
**Resposta:** Vá em **Rotinas de Busca**, clique em **+ Nova Rotina**, dê um nome à rotina e digite suas palavras-chave (ex: `licitação software, pregão eletrônico`) no campo **Termos de Busca**. Selecione as seções do DOU desejadas e salve.

---

### ❓ "O que fazer quando a Busca Mensal avisar que faltam matérias no INLABS?"
**Resposta:** O modal de confirmação indicará claramente se os dias ausentes podem ser baixados do portal INLABS (janela dos últimos 120 dias) ou se serão consultados diretamente via **API Oficial do DOU** (para datas históricas). Basta clicar no botão principal de confirmação para que o sistema baixe os dias recentes e consulte a API DOU automaticamente.

---

### ❓ "Por que a planilha do Google Sheets deu erro de permissão (403)?"
**Resposta:** Abra a planilha no Google Drive, clique no botão azul **Compartilhar** no canto superior direito e adicione o e-mail da Conta de Serviço (o campo `client_email` presente no JSON de credenciais) como **Leitor**.

---

### ❓ "O e-mail de teste do SMTP não está sendo enviado. Como resolver?"
**Resposta:** Se você utiliza Gmail ou Microsoft 365 com autenticação em duas etapas, a senha comum não funcionará. Você precisa gerar uma **Senha de Aplicativo (App Password)** no painel de segurança da sua conta e colá-la no campo Senha do SMTP.

---

### ❓ "Como evitar que minha sessão expire enquanto estou trabalhando?"
**Resposta:** A sessão dura 30 minutos de inatividade. Quando faltar 1 minuto para expirar, o painel exibirá um aviso permitindo estender o acesso com um clique. Basta clicar em **Continuar Conectado** no aviso na tela para renovar o acesso por mais 30 minutos.
