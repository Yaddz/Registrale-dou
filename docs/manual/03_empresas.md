# 3. Empresas, raiz de CNPJ e sincronização

## Regra de identificação por raiz de CNPJ

O Registrale-DOU identifica cada empresa pelos **8 primeiros caracteres do CNPJ** (a raiz):

- **Conta como menção:** CNPJ completo de qualquer estabelecimento da raiz (matriz ou filiais), raiz pontuada isolada (`XX.XXX.XXX`, padrão comum em Resoluções-RE da ANVISA) e raiz destacada pela própria busca do DOU.
- **Não conta:** raiz sem pontuação solta no texto, número maior que contenha os 8 dígitos ou valores monetários (ex.: `R$ 24.684.423,00`).
- **CNPJ alfanumérico:** o padrão de 12 caracteres alfanuméricos + 2 dígitos verificadores é suportado integralmente.

A consulta na API do DOU é sempre enviada no formato `"XX.XXX.XXX"`, cobrindo matriz e filiais em uma única consulta.

## Fontes de cadastro

1. **Cadastro manual:** adicione, edite ou exclua empresas na aba **Empresas** (botão **Adicionar empresa**).
2. **Google Sheets:** conecte uma planilha privada via conta de serviço (JSON), configure a coluna de CNPJ/Razão Social e defina o intervalo de sincronização automática.
   - A opção de **Apagar obsoletos** (aba **Google Sheets**) remove do monitoramento empresas de origem `Google Sheets` que foram retiradas da planilha (preservando empresas cadastradas manualmente ou via GestãoClick).
3. **API GestãoClick:** importe clientes informando a URL base e os tokens de acesso.

## Pausar e ativar empresas ou origens

- Você pode pausar ou ativar empresas individualmente ou por origem (`Manual`, `Google Sheets`, `GestãoClick`).
- Todos os interruptores de ativar/pausar seguem o mesmo padrão visual e gravam o estado diretamente no banco antes de reconstruir `Pesquisa_cnpj.yaml`.
- O assistente de onboarding e as configurações reconhecem automaticamente origens ou rotinas que foram pausadas.
