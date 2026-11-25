# 1. Primeiro uso, instalação e onboarding

## Instalação no Windows

1. Baixe o instalador `Registrale-Setup-x.y.z.exe` na página de releases (e confira o arquivo `.sha256` quando disponível).
2. Execute o instalador. Não é necessário Docker, WSL, terminal ou instalação prévia de Python.
3. O instalador grava o programa em `%LOCALAPPDATA%\Programs\Registrale`, cria o atalho na Área de Trabalho e configura a inicialização automática com o Windows.
4. Ao abrir, o ícone do **Registrale-DOU** aparece na **bandeja do sistema** (ao lado do relógio) e o painel abre em uma **janela própria** (WebView2), com fallback automático para o navegador padrão em `http://127.0.0.1:5000`.

> **Fechar a janela:** ao fechar a janela principal, o painel é minimizado para a bandeja do sistema e o agendador continua rodando em segundo plano. Use o menu do ícone na bandeja (botão direito) para reabrir a janela, ver logs, reiniciar ou encerrar o aplicativo.

## Onde ficam os arquivos

| Conteúdo | Caminho padrão no Windows | Observação |
|---|---|---|
| Programa instalado | `%LOCALAPPDATA%\Programs\Registrale` | Substituído nas atualizações |
| Banco SQLite (`database.db`), rotinas e logs | `%LOCALAPPDATA%\Registrale` | Preservado ao atualizar ou desinstalar |
| PDFs integrais do DOU | `Documentos\Registrale\DOU` | Configurável no onboarding e em **Configurações** |

## Acesso e login opcional

No uso local (`127.0.0.1` / `localhost`), o painel pode abrir **direto**, como administrador e sem senha, ou **exigir usuário e senha**. A abertura direta só vale neste computador; acessos por outro endereço continuam pedindo login. Altere a qualquer momento em **Configurações → Usuários → Acesso ao painel** (interruptor **Exigir login**). Com o login ligado, a sessão expira após 30 minutos sem renovação.

## Assistente de primeiro uso (9 passos)

Ao abrir o Registrale-DOU pela primeira vez, o **assistente de configuração inicial** guia o analista por **9 passos** para deixar a busca das 8h pronta (ou conscientemente desativada). O progresso fica salvo: se fechar o painel no meio (botão **X** do assistente), ele retoma do passo onde parou no próximo acesso.

1. **Boas-vindas e importação:** importe um `database.db` e/ou rotinas `.yaml` de uma instalação anterior (um backup do banco atual é feito antes) ou comece do zero. Se houver dados anteriores no computador, o assistente os detecta e oferece **Importar dados detectados**.
2. **Pasta e organização dos PDFs:** escolha onde salvar os PDFs integrais do DOU e o layout de pastas (`Por ano e mês`, `Só por ano` ou `Tudo na mesma pasta`).
3. **Como abrir o painel:** defina se o painel pede usuário e senha ou abre direto neste computador.
4. **Rotina inicial:** revise horário (padrão **8h em dias úteis**), seções (**1, 2, 3 e Edição Extra**), órgãos (**todos**) e busca exata (**desligada**, para cobrir matriz e filiais pela raiz do CNPJ). O botão **Manter padrão** avança e mantém a rotina padrão ativa.
5. **Empresas monitoradas:** escolha a origem dos clientes — **Google Sheets**, **API do GestãoClick** ou **cadastro manual** —, teste a conexão e sincronize na hora para ver quantos CNPJs entraram.
6. **API do GestãoClick:** informe Base URL, Access Token e Secret Token, teste a conexão e defina se a sincronização automática fica ativa.
7. **E-mail (SMTP):** ligue ou desligue o envio; quando ligado, informe servidor, porta, usuário, senha, remetente e destinatários e faça um envio de teste. Desligado, as menções continuam sendo gravadas no painel.
8. **INLABS e contingência:** no aplicativo instalado o INLABS local não existe (o instalador não embute o PostgreSQL portátil); o assistente explica que a busca usa automaticamente a contingência **PDF integral + API do DOU** e permite ajustar essa opção.
9. **Resumo:** mostra o que ficou ativo, desativado ou pendente, o próximo horário de busca e o botão **Buscar agora**, que dispara a busca de hoje para testar a configuração.

### Pular, manter e retomar

- **Pular por enquanto** avança e deixa a integração daquele passo **desativada** (estado neutro, **não** pendente): por exemplo, pular o passo 2 desliga o arquivamento de PDFs, o 6 desliga a sincronização automática do GestãoClick e o 7 desliga o SMTP. Os passos 1 e 3 só avançam (o 3 mantém a forma de abertura atual). Reative depois em **Configurações**.
- No passo 4 o botão é **Manter padrão**: a rotina semeada (8h, dias úteis, Seções 1/2/3 e Extra, todos os órgãos) continua ativa.
- **Refazer configuração inicial:** em **Configurações → Sistema e atualizações** reabre o assistente sem apagar nenhum dado. Na reabertura, o botão de pular vira **Manter como está** e **não desliga** uma integração que já estava ligada.
