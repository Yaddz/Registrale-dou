# 6. Integrações e configurações (SMTP, INLABS e acesso)

## SMTP (Envio de e-mails)

- **Interruptor global de SMTP:** fica em **Configurações → Integrações**.
- Quando o SMTP está **desligado**:
  - Os campos dependentes (servidor, porta, usuário, senha, remetente e destinatários) ficam desabilitados na interface.
  - É possível salvar rotinas e configurações **sem informar destinatários**.
  - Nenhum disparo de e-mail ocorre em buscas automáticas, manuais, mensais ou novas tentativas — todas as menções continuam sendo gravadas normalmente no painel.
- Quando **ligado**, configure servidor, porta, usuário, senha, e-mail de envio (From) e destinatários; há também um campo de destinatário para **teste de envio** do SMTP. Os destinatários dos relatórios diários ficam na rotina principal.

## API do GestãoClick

Também em **Configurações → Integrações** (cartão **API GestãoClick**): Base URL, Access token, Secret access token e o interruptor **Sincronização automática**. Quando desligada, aparece como **Desativada**, sem gerar pendência.

## INLABS e busca padrão (PDF + API do DOU)

O instalador Windows padrão não embute os binários do PostgreSQL portátil (`-SkipPostgresDownload`), portanto o **INLABS local não vem instalado por padrão** no aplicativo desktop.

Para garantir buscas confiáveis mesmo sem o banco INLABS local (ou quando o portal `inlabs.in.gov.br` estiver em manutenção):

- O sistema utiliza a contingência escolhida em **Configurações → Integrações** (campo **Fonte quando o INLABS estiver fora**, `inlabs_fallback`):
  - **`pdf` (padrão):** baixa e lê o texto do PDF integral do DOU (`pesquisa.in.gov.br`) e confirma as empresas encontradas na API do DOU (`in.gov.br`) para obter os links oficiais das matérias.
  - **`api`:** consulta diretamente a API oficial do DOU para todos os termos da rotina.
  - **`off` (Desligado):** desativa a contingência automática e pesquisa apenas o banco INLABS local.
- Caso o PostgreSQL portátil esteja presente e o INLABS configurado, ele é usado normalmente; se não estiver disponível, o app não gera erros repetidos no log e segue pela contingência configurada.

## Acesso local e segurança

- Em **Configurações → Usuários → Acesso ao painel**, o interruptor **Exigir login** alterna entre abertura direta (como administrador, só em `127.0.0.1`) e exigência de usuário e senha. Na mesma aba ficam os usuários do painel.
- Ao religar a exigência de login, sessões anteriores abertas sem senha são encerradas automaticamente.
