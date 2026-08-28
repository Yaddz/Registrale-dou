# 03. Integrações do Sistema

O **Ro-DOU Dashboard** atua como uma ponte de dados entre o ERP corporativo, planilhas colaborativas, a base de dados oficial da Imprensa Nacional e servidores de e-mail. A seguir, detalha-se o funcionamento de cada uma das 4 principais integrações:

---

## 🔗 1. Integração GestãoClick (ERP)

A integração com o GestãoClick é responsável por manter a base de clientes do monitoramento sempre sincronizada com o ERP comercial da Registrale.

### Como Funciona o Fluxo de Sincronização:
1. O backend consome o endpoint paginado `/clientes` da API do GestãoClick (`https://api.gestaoclick.com/franquias/clientes`).
2. Autentica via cabeçalhos HTTP:
   * `access-token`: Chave de acesso configurada.
   * `secret-access-token`: Chave secreta de autenticação.
3. Percorre todas as páginas de clientes e filtra apenas registros que possuem CNPJ válido preenchido.
4. Normaliza e formata os números de CNPJ (padrão `XX.XXX.XXX/XXXX-XX`).
5. Persiste as empresas na tabela `Company` do SQLite com `origem = 'gestaoclick'` e `status = True`.
6. Divide automaticamente os CNPJs ativos em **blocos de até 150 empresas** e regrava os arquivos YAML particionados (`Pesquisa_cnpj_part_1.yaml`, `Pesquisa_cnpj_part_2.yaml`, etc.) e o arquivo consolidado `Pesquisa_cnpj_sync.yaml`.

---

## 📊 2. Integração Google Sheets (API v4)

A integração com o Google Sheets permite que equipes operacionais mantenham uma planilha online no Google Drive e sincronizem automaticamente os CNPJs para monitoramento sem necessidade de exportar arquivos manuais.

### Arquitetura de Conexão Segura:
* Utiliza a biblioteca oficial `google-api-python-client` e autenticação via **Conta de Serviço (Service Account)** do Google Cloud.
* Funciona perfeitamente com **planilhas privadas** (não requer que a planilha seja pública na web; basta compartilhar a planilha privada com o e-mail da Conta de Serviço).

### Recursos Disponíveis:
* **Orientação Flexível:**
  * **Modo Linhas (`rows`):** Cabeçalho na linha 1 com dados nas linhas subsequentes.
  * **Modo Colunas (`columns`):** Cabeçalhos dispostos verticalmente na coluna A com dados distribuídos nas colunas B, C, D...
* **Mapeamento de Colunas Personalizado:** O operador pode configurar os nomes exatos das colunas (ex: coluna da Razão Social = `Nome do Cliente` ou `Empresa`, coluna do CNPJ = `CNPJ / CPF` ou `Documento`).
* **Sincronização Automática (Scheduler Daemon):** O Dashboard executa um worker em background que sincroniza a planilha periodicamente (a cada 15 min, 30 min, 1h, 2h, 6h, 12h ou diariamente).
* **Apagar Registros Obsoletos (`delete_obsolete`):** Switch configurável que, quando ativado, exclui automaticamente do banco e das DAGs empresas com origem `Google Sheets` que foram deletadas da planilha na última sincronização (mantendo protegidas empresas manuais e do ERP).
* **Teste de Conexão com Amostra:** Antes de salvar, o usuário pode clicar em *Testar Conexão e Prévia* para visualizar o título da planilha, abas disponíveis e uma tabela com as primeiras linhas lidas.

---

## 🏛️ 3. Conexão INLABS (Imprensa Nacional / PostgreSQL)

O INLABS é o sistema de distribuição digital de matérias da Imprensa Nacional. O Dashboard conecta-se ao banco de dados PostgreSQL do INLABS (`dou_inlabs`) para consultar a disponibilidade de matérias históricas.

### Detalhes Técnicos:
* **Driver:** `pg8000` (driver PostgreSQL nativo em Python puro, de alta estabilidade e sem dependências binárias complexas).
* **Estrutura Consultada:** Tabela `dou_inlabs.article_raw` particionada por data de publicação.
* **Diagnóstico de Armazenamento:**
  * Endpoint `/api/inlabs_stats` calcula o tamanho real ocupado em disco pelo banco de dados (`pg_database_size`).
  * Mapeia todos os dias já baixados e a quantidade exata de artigos armazenados por data.
* **Prevenção de Lacunas na Busca Mensal:** Ao disparar uma busca mensal, o sistema verifica quais dias do mês selecionado não possuem dados baixados no INLABS e oferece um botão para realizar o download automático dos dias ausentes antes de iniciar o processamento das buscas.

---

## 📧 4. Servidor SMTP & Disparo de Notificações

Responsável pelo envio de alertas imediatos quando uma empresa monitorada é mencionada no Diário Oficial e pelo envio de relatórios sob demanda.

### Recursos:
* Suporte a servidores SMTP padrão, TLS e SSL (porta 587 ou 465).
* Suporte a autenticação com usuário e senha ou chaves de aplicativo (ex: Gmail/Google Workspace, Microsoft 365, Amazon SES, SendGrid).
* **Higienização Automática de Credenciais:** Remove automaticamente espaços inseridos por conveniência visual em Senhas de Aplicativo do Google (`abcd efgh ijkl mnop`).
* **Preservação Inteligente de Senhas:** Atualizações de configurações que deixem o campo de senha vazio mantêm a senha salva previamente no banco de dados, evitando perda acidental de credenciais.
* **Sincronização com o Airflow:** O salvamento de SMTP grava automaticamente as configurações no `.env` e atualiza a conexão `smtp_default` via REST API do Airflow.
* **Renderização Dinâmica de Templates:** Substitui variáveis no corpo HTML do e-mail:
  * `{empresa}`: Razão Social da empresa
  * `{cnpj}`: CNPJ da empresa
  * `{secao}`: Seção do DOU onde a publicação ocorreu
  * `{data}`: Data oficial da publicação
  * `{trecho}`: Trecho de texto onde o termo foi identificado
  * `{link}`: Link direto para o ato oficial no site da Imprensa Nacional
* **Teste de Conexão Imediato:** Disponível tanto na aba de Configurações quanto no modal do assistente (`/api/test_smtp`), enviando um e-mail de teste para o destinatário informado com diagnóstico detalhado de erros e suporte a fallback de credenciais salvas no banco.
