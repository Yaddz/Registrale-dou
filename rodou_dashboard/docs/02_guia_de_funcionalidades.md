# 02. Guia de Funcionalidades do Painel

O painel de controle do **Ro-DOU Dashboard** foi projetado com uma interface reativa, limpa e moderna utilizando Alpine.js e Tailwind CSS. A interface é dividida em 5 áreas principais:

1. **Dashboard Principal (Visão Geral & Menções)**
2. **Empresas Monitoradas**
3. **Gerenciador de Rotinas**
4. **Relatórios de Menções**
5. **Configurações Globais** (Restrita a usuários com perfil `master`)

---

## 📊 1. Painel Principal (Dashboard)

Ao autenticar no sistema, o usuário é direcionado para a tela principal que exibe:

* **Cards de Indicadores (KPIs):**
  * **Empresas Monitoradas:** Total de empresas cadastradas no sistema.
  * **Empresas Ativas:** Quantidade de empresas que estão com monitoramento ativo.
  * **Menções Hoje:** Publicações oficiais detectadas na data de hoje.
  * **Menções no Mês:** Total de publicações oficiais detectadas no mês corrente.
  * **Última Sincronização:** Data e hora em que a base de clientes foi atualizada com o ERP ou Google Sheets.
  * **Próxima Execução:** Horário previsto para a próxima varredura automática do DOU.

* **Feed em Tempo Real de Menções:**
  * Lista de publicações encontradas em tempo real com badges coloridos por Seção do DOU (`Seção 1`, `Seção 2`, `Seção 3`).
  * Trecho contextualizado com destaque para o termo/CNPJ encontrado.
  * Botão de acesso direto ao documento oficial na Imprensa Nacional (`in.gov.br`).
  * Notificação sonora inteligente quando novas menções são detectadas pela primeira vez.

* **Histórico Recente de Atividades:**
  * Linha do tempo lateral contendo os últimos 5 eventos executados pelo sistema (disparos de rotina, downloads do INLABS, sincronizações de base e envios de e-mails).

---

## 🏢 2. Gestão de Empresas Monitoradas

Aba acessível no menu superior para gestão completa da base de clientes:

* **Busca e Filtro em Tempo Real:** Campo de busca com resposta instantânea por Razão Social, Nome Fantasia ou CNPJ formatado/não-formatado.
* **Badges de Origem:** Identificação visual da origem de cada empresa:
  * `GestãoClick`: Importada via API do ERP.
  * `Google Sheets`: Importada via integração com planilha Google.
  * `Manual`: Cadastrada manualmente pelo operador no painel.
* **Ações Rápidas por Empresa:**
  * **Alternar Monitoramento:** Chave de ativação/desativação individual de busca diária.
  * **Editar Empresa:** Modal para ajuste de Razão Social e status.
  * **Histórico Individual:** Abre uma linha do tempo dedicada com todas as publicações já encontradas especificamente para aquele CNPJ.
  * **Excluir Empresa:** Remove o registro da base de monitoramento (apenas para perfil `master`).
* **Adição Manual:** Modal para cadastro rápido de novas empresas com validação e máscara automática de CNPJ.

---

## ⚙️ 3. Gerenciador de Rotinas de Busca

Permite configurar, disparar sob demanda e automatizar as pesquisas nos Diários Oficiais:

* **Tipos de Rotinas:**
  * **Rotina de Sistema (`Pesquisa_cnpj_sync`):** Rotina principal que lê todas as empresas ativas do banco SQLite e divide automaticamente os CNPJs em blocos para execução paralela de alta performance no Airflow.
  * **Rotinas Personalizadas:** Rotinas customizadas para monitoramento de termos específicos (ex: palavras-chave de licitações, nomes de sócios, órgãos públicos específicos).
* **Ações por Rotina:**
  * **Rodar Agora:** Dispara imediatamente a rotina para a data corrente.
  * **Disparar com Data Lógica:** Modal inteligente com suporte a datas no formato `DD/MM/AAAA` (com máscara automática) e `AAAA-MM-DD`, calendário flutuante interativo (Flatpickr), detecção de feriados nacionais e finais de semana (informando ausência de circulação do DOU) e aviso automático com comutação para a API Oficial do DOU quando a data for anterior a 120 dias.
  * **Busca Mensal Automatizada:** Dispara a varredura para todos os dias úteis de um mês e ano selecionados. Inclui download automatizado em lote de múltiplos dias faltantes no portal INLABS com sessão persistente (sem bloqueios de rate limit) e suporte completo ao **Cenário Misto** na busca (sumário visual com 3 categorias: ✅ *No Banco INLABS*, 📥 *Baixar INLABS*, 🌐 *Via API DOU*).
  * **Modos de Execução da Busca Mensal:** A execução suporta perfis variados de busca: `full` (executa dias no banco e busca faltantes via API DOU), `download_and_search` (baixa no INLABS os dias na janela de 120 dias e pesquisa históricos via API DOU), `inlabs_only` (busca somente dias salvos no PostgreSQL) e `api_dou_only` (pesquisa todo o período diretamente pela API Oficial do DOU).
  * **Proteção e Estabilidade de DAGs Temporárias:** As DAGs temporárias geradas para consultas ad-hoc e buscas mensais (via API DOU) são monitoradas de forma protegida, com tolerância ampliada de 1 hora e verificação ativa no Airflow para evitar cancelamento prematuro por limpezas em segundo plano ou reciclagem de processos.
  * **Padronização INLABS:** Todas as novas rotinas criadas automaticamente usam `INLABS` como fonte de dados padrão e replicam os e-mails de destinatário da rotina principal.
  * **Ativar/Pausar Rotina:** Chave para habilitar ou desabilitar o agendamento da rotina.
  * **Configurações Avançadas:** Edição do Cron de execução, seções do DOU (`SEÇÃO 1`, `SEÇÃO 2`, `SEÇÃO 3`), lista de órgãos específicos, busca por termo exato e e-mails de alerta.

### 3.1. Assistente de Integrações Passo a Passo (Setup Wizard)

O sistema verifica continuamente a integridade de todas as integrações ao carregar o painel:
* Se houver qualquer pendência, um **banner de alerta interativo** é exibido no topo do dashboard com badges indicativos para cada integração (`Rotina Principal`, `Servidor SMTP`, `Google Sheets` e `Acesso INLABS`).
* **Modal da Rotina Principal (`mainDagSetupModal`):**
  1. **Destinatários e Notificação:** E-mails de destino (obrigatório com validação de regex), assunto do e-mail e horário de execução (cron).
  2. **Servidor de Envio (SMTP):** Servidor, porta, usuário, senha (com preservação de senhas preexistentes) e e-mail de envio, com botão de teste imediato de conexão SMTP dentro do modal.
* **Fluxo Wizard Sequencial:** Ao salvar com sucesso uma etapa, o assistente abre o modal de confirmação sugerindo o avanço imediato para a próxima integração pendente.
* Após salvar, o sistema sincroniza atomicamente o SQLite, o YAML `Pesquisa_cnpj.yaml`, as variáveis do `.env` e as conexões do Airflow (`smtp_default`).

---

## 📑 4. Central de Relatórios e Exportações

Ferramenta avançada de auditoria, filtros e geração de relatórios corporativos:

* **Atalhos de Período Rápido:** Seleção instantânea de datas: `Hoje`, `Últimos 7 dias`, `Este Mês`, `Últimos 30 dias`, `Ano Atual` ou período personalizado.
* **Seleção Múltipla de Empresas:** Filtro com autocomplete para selecionar uma ou mais empresas específicas simultaneamente.
* **Filtro por Seção do DOU:** Opção de filtrar por Seção 1 (Atos Normativos), Seção 2 (Pessoal) ou Seção 3 (Contratos e Editais).
* **Opções de Exportação:**
  * **Excel Corporativo (.xlsx):** Gera planilha formatada via `openpyxl` com cabeçalhos estilizados, larguras automáticas de coluna e links clicáveis para o DOU.
  * **Relatório PDF Diagramado:** Gera documento executivo em PDF com cabeçalho oficial da Registrale, dados da empresa, resumo da publicação, trecho localizado e link para a edição original.
  * **Disparo de Relatório por E-mail:** Permite disparar o relatório formatado para um ou múltiplos destinatários via SMTP utilizando os modelos cadastrados.

---

## 🛠️ 5. Configurações Globais (Acesso Master)

Painel restrito a administradores com as seguintes abas:

### A. Usuários
* Criação de novos acessos com definição de papéis (`master` ou `user`).
* Listagem de usuários internos e remoção de credenciais.

### B. Google Sheets (Integração Dedicada)
* Manual passo a passo interativo de configuração no Google Cloud.
* Campo para credenciais JSON da Conta de Serviço (*Service Account*).
* Teste de conexão em tempo real com pré-visualização das linhas e colunas lidas da planilha.
* Configuração da orientação dos dados (Linhas ou Colunas), intervalo de sincronização automática e mapeamento de cabeçalhos (`Razão Social` e `CNPJ`).
* Botão de sincronização forçada imediata.

### C. Integrações Gerais
* **Configuração SMTP:** Servidor, porta, usuário, senha, e-mail de envio e botão de teste de disparo com feedback visual imediato (integrado ao fluxo do `mainDagSetupModal` para configuração guiada do sistema).
* **API GestãoClick:** Token de acesso, Secret token, URL base da API e flag de sincronização automática.
* **Credenciais INLABS:** Usuário e senha de acesso à base da Imprensa Nacional.

### D. Templates de E-mail
* **Editor Visual WYSIWYG Integrado:** Edição direta e intuitiva no preview do e-mail com três modos de trabalho: *Editor Visual (Preview)*, *Demonstração Real* e *Código HTML*.
* **Ferramenta Destaque Amarelo DOU:** Aplicação em 1 clique da cor `#FFA` com formatação oficial do Diário Oficial no texto ou tag selecionada.
* **Menu de Variáveis Dinâmicas (`+ Inserir Variável`):** Inserção contextual das tags `{content}`, `{empresa}`, `{cnpj}`, `{secao}`, `{data}`, `{trecho}` e `{link}` na posição do cursor.
* **Controle de Edição:** Desfazer / Refazer (Ctrl+Z / Ctrl+Y), títulos (H1, H2, H3), alinhamentos e limpeza de formatação.
* Criação, edição e exclusão de múltiplos modelos de e-mail personalizados.

### E. Limpeza de Sistema
* **Limpar Dados:** Reseta os dados gerais do banco local.
* **Limpar INLABS:** Remove publicações históricas do INLABS com mais de **120 dias** para liberar espaço em disco.
* **Limpar Histórico:** Limpa eventos antigos da linha do tempo.
* **Limpar Menções:** Remove menções antigas arquivadas no painel.

### F. Armazenamento INLABS
* Painel de diagnóstico que exibe o tamanho total ocupado no banco PostgreSQL do INLABS e a quantidade de dias armazenados.
* Tabela detalhada listando cada dia carregado no banco com total de artigos e matérias processadas.
