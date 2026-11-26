# 2. Empresas

## Como o Registrale reconhece uma empresa

Toda empresa é identificada pela **raiz do CNPJ**: os 8 primeiros dígitos, que são iguais na matriz e em todas as filiais.

> **Exemplo:** no CNPJ `24.684.423/0001-50`, a raiz é `24.684.423`. A filial `24.684.423/0002-30` tem a mesma raiz, então é a mesma empresa.

Por isso, basta cadastrar **um** CNPJ por empresa: a busca já cobre a matriz e todas as filiais.

| Conta como menção | Não conta como menção |
|---|---|
| O CNPJ completo da matriz ou de qualquer filial | Os 8 dígitos sem pontos soltos no texto (`24684423`) |
| A raiz sozinha, com pontos (`24.684.423`), comum nas Resoluções-RE da ANVISA | Um número maior que contém os 8 dígitos |
| A raiz destacada pela própria busca do DOU | Um valor em reais (`R$ 24.684.423,00`) |

O novo CNPJ com letras (12 caracteres alfanuméricos + 2 dígitos) também é aceito.

## De onde vêm as empresas

Você pode usar uma, duas ou as três fontes ao mesmo tempo. Cada empresa guarda a sua **origem**.

| Origem | Quando usar | Onde configurar |
|---|---|---|
| **Manual** | Poucas empresas, ou uma empresa que não está na planilha nem no ERP | Aba **Empresas → Adicionar empresa** |
| **Google Sheets** | A lista de clientes fica numa planilha do Google | **Configurações → Google Sheets** |
| **GestãoClick** | Os clientes estão cadastrados no ERP GestãoClick | **Configurações → Integrações**, cartão **API GestãoClick** |

Para trazer as novidades da planilha ou do ERP na hora, use **Sincronizar bases** (no topo da tela) ou **Sincronizar** (na aba Empresas) e escolha a origem. Com a sincronização automática ligada, isso acontece sozinho.

**Se o mesmo CNPJ estiver em mais de uma origem:**
- **Manual** sempre vence: nem a planilha nem o GestãoClick alteram uma empresa cadastrada à mão.
- **Google Sheets** vence sobre o **GestãoClick**: se a planilha tiver um CNPJ que veio do GestãoClick, a planilha atualiza o nome e o status e a origem passa para **Google Sheets**; o GestãoClick não altera empresas que já estão na planilha.

### Cadastrar uma empresa à mão

1. Abra a aba **Empresas** e clique em **Adicionar empresa**.
2. Preencha **Razão social / nome** e **CNPJ** (a pontuação é colocada sozinha).
3. Deixe **Monitorar no DOU** ligado.
4. Clique em **Salvar Empresa**.

A empresa entra na próxima busca automática. Para conferir o dia de hoje na hora, veja [Pesquisar agora](03_rotinas_e_buscas.md#pesquisar-agora-ou-um-dia-específico).

### Ligar uma planilha do Google Sheets

A tela **Configurações → Google Sheets** tem um passo a passo ilustrado (**Manual de configuração**). Em resumo:

1. No Google Cloud, ative a **Google Sheets API** e crie uma **conta de serviço**.
2. Baixe a chave dessa conta em formato **JSON**.
3. Compartilhe a planilha com o e-mail da conta de serviço, como **Leitor**. O painel mostra esse e-mail com o botão **Copiar e-mail**.
4. No painel, cole a **URL da planilha** e o conteúdo do **arquivo JSON**.
5. Informe o nome exato das colunas **Razão social / nome** e **CNPJ**.
6. Escolha a **Sincronização automática** (de 15 minutos a 24 horas).
7. Clique em **Testar conexão e Prévia** para ver as primeiras linhas lidas e depois em **Salvar configurações**.

**Apagar obsoletos:** quando ligado, uma empresa que sair da planilha também sai do monitoramento. Só vale para empresas de origem Google Sheets: as manuais e as do GestãoClick nunca são apagadas por isso.

### Ligar o GestãoClick

Em **Configurações → Integrações**, cartão **API GestãoClick**, informe **Base URL API**, **Access token** e **Secret access token** (gerados no próprio GestãoClick) e ligue **Sincronização automática** se quiser a atualização diária.

## Procurar, ordenar e filtrar

Na aba **Empresas** você pode pesquisar por nome ou CNPJ, filtrar por origem e por status (**Monitorado (Ativo)** ou **Inativo**) e ordenar por quantidade de menções, nome, CNPJ, status ou origem.

A coluna **Menções** soma tudo o que foi encontrado da empresa: matriz, filiais e menções só pela raiz. Ela se atualiza sozinha quando uma busca termina.

## Pausar, editar e ver o histórico

| Quero… | Como |
|---|---|
| Parar de monitorar uma empresa sem apagá-la | Clique no lápis (**Editar empresa**) e desligue **Monitorar no DOU** |
| Pausar todas as empresas de uma origem | Na rotina principal (aba **Rotinas**, engrenagem), em **Monitoramento por Origem**, desmarque a origem |
| Ver todas as menções de uma empresa | Ícone **Histórico no DOU** na linha da empresa |
| Exportar a lista de empresas | **Exportar Excel**, no topo da aba Empresas |

Empresas pausadas continuam no cadastro e com o histórico, só não entram nas buscas. Toda mudança atualiza a rotina principal na hora.
