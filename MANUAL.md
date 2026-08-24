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
> A sessão do usuário dura **30 minutos** de inatividade. Qualquer clique ou navegação renova a sessão automaticamente. Quando faltar 1 minuto para expirar, o sistema exibirá um aviso permitindo estender o acesso com um clique.

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
  * O sistema divide a lista em blocos de até **150 CNPJs** para garantir buscas rápidas e em paralelo.
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
6. **Filtro por Órgãos (Opcional):**
   * Especifique ministérios, agências reguladoras ou autarquias que deseja filtrar (ex: `ANVISA, Ministério da Saúde`).
7. **E-mails de Notificação:**
   * Digite os e-mails que devem receber alertas automáticos quando forem encontradas publicações nesta rotina.
8. Clique em **Salvar Configurações**.

---

### 3.3. Como Disparar uma Busca Imediata ("Rodar Agora")
* Ao lado da rotina desejada, clique no botão **Rodar Agora** (ícone de Play).
* O sistema iniciará a varredura da edição de hoje do Diário Oficial imediatamente em segundo plano.

---

### 3.4. Como Disparar Busca com Data Retroativa (Reprocessamento / Auditoria)
1. Ao lado da rotina, clique no botão **Data Lógica / Calendário**.
2. Selecione no calendário a data passada exata que deseja auditar ou reprocessar.
3. Clique em **Disparar**.
4. O sistema buscará as publicações publicadas naquela data específica.

---

### 3.5. Como Fazer uma Busca Mensal Completa

1. No topo da tela de rotinas, clique no botão **Busca Mensal**.
2. Selecione o **Mês** e o **Ano** desejados e marque as rotinas que devem rodar.
3. **Verificação de Matérias no INLABS:**
   * O sistema confere automaticamente se todas as edições daquele mês estão disponíveis.
   * Se o sistema avisar que existem matérias faltantes, clique no botão **Baixar Matérias Faltantes** para realizar o download automático das edições ausentes.
4. Clique em **Iniciar Busca Mensal**. O sistema processará todos os dias úteis do mês selecionado.

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
2. **Filtro de Empresas:** Digite o nome de uma ou mais empresas no campo de busca para gerar um relatório segmentado.
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
3. **Validação:**
   * Clique em **Testar Conexão e Prévia** para ver as primeiras linhas lidas da planilha.
   * Clique em **Salvar Configurações**.

---

### 6.3. Como Configurar o Servidor de E-mail (SMTP)
Na sub-aba **Integrações Gerais**:
* **Servidor:** Endereço SMTP (ex: `smtp.gmail.com` ou `smtp.office365.com`).
* **Porta:** `587` (STARTTLS) ou `465` (SSL).
* **Usuário e Senha:** E-mail da conta e a senha (ou Senha de Aplicativo de 16 dígitos se usar autenticação em 2 etapas no Gmail/Outlook).
* **E-mail de Envio:** E-mail que aparecerá como remetente (ex: `notificacoes@registrale.com.br`).
* **Testar Envio:** Digite seu e-mail e clique em **Testar Envio** para receber uma mensagem de confirmação.

---

### 6.4. Como Criar e Personalizar Templates de E-mail
Na sub-aba **Templates de E-mail**:
* Crie modelos visuais de mensagens usando o editor HTML com visualização dinâmica.
* Insira as tags dinâmicas que o sistema substitui na hora do envio:
  * `{empresa}`: Razão Social do cliente.
  * `{cnpj}`: CNPJ do cliente.
  * `{secao}`: Seção do Diário Oficial.
  * `{data}`: Data da publicação.
  * `{trecho}`: Trecho oficial onde o nome foi citado.
  * `{link}`: Link direto para o ato na Imprensa Nacional.

---

### 6.5. Como Conectar ao ERP GestãoClick
Na sub-aba **Integrações Gerais**:
* Insira o **Token de Acesso** e a **Chave Secreta** gerados no GestãoClick.
* Ative o toggle de sincronização automática. O sistema importará novos clientes cadastrados no ERP automaticamente.

---

### 6.6. Limpeza e Manutenção do Sistema
Na sub-aba **Limpeza do Sistema**:
* **Limpar INLABS:** Remove edições antigas do banco com mais de 120 dias para liberar espaço em disco.
* **Limpar Histórico:** Limpa a linha do tempo de sincronizações passadas.
* **Limpar Menções:** Remove menções arquivadas.

---

## 7. Perguntas Frequentes (FAQ) & Dúvidas do Dia a Dia

### ❓ "Cadastrei uma empresa hoje, quando ela começará a ser buscada?"
**Resposta:** Imediatamente nas próximas execuções automáticas. Se quiser conferir a edição do dia de hoje para essa nova empresa imediatamente, vá em **Rotinas de Busca** e clique em **Rodar Agora** na rotina `Pesquisa_cnpj_sync`.

---

### ❓ "Como monitorar uma palavra-chave ou termo em vez de uma empresa?"
**Resposta:** Vá em **Rotinas de Busca**, clique em **+ Nova Rotina**, dê um nome à rotina e digite suas palavras-chave (ex: `licitação software, pregão eletrônico`) no campo **Termos de Busca**. Selecione as seções do DOU desejadas e salve.

---

### ❓ "O que fazer quando a Busca Mensal avisar que faltam matérias no INLABS?"
**Resposta:** No próprio modal de Busca Mensal, clique no botão azul **Baixar Matérias Faltantes**. O sistema fará o download automático dos dias ausentes direto da Imprensa Nacional antes de iniciar a busca.

---

### ❓ "Por que a planilha do Google Sheets deu erro de permissão (403)?"
**Resposta:** Abra a planilha no Google Drive, clique no botão azul **Compartilhar** no canto superior direito e adicione o e-mail da Conta de Serviço (o campo `client_email` presente no JSON de credenciais) como **Leitor**.

---

### ❓ "O e-mail de teste do SMTP não está sendo enviado. Como resolver?"
**Resposta:** Se você utiliza Gmail ou Microsoft 365 com autenticação em duas etapas, a senha comum não funcionará. Você precisa gerar uma **Senha de Aplicativo (App Password)** no painel de segurança da sua conta e colá-la no campo Senha do SMTP.

---

### ❓ "Como evitar que minha sessão expire enquanto estou trabalhando?"
**Resposta:** Qualquer clique de navegação entre abas ou botões estende a sessão automaticamente por mais 30 minutos. Quando faltar 1 minuto para expirar, clique em **Continuar** no aviso na tela para renovar o acesso.
