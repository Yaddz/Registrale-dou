# 1. Primeiros passos

## Instalar

1. Baixe o instalador `Registrale-Setup-x.y.z.exe` na página de versões (releases) do projeto.
2. Dê dois cliques e siga as telas. Não é preciso instalar Python, Docker nem nada antes.
3. Ao terminar, o Registrale-DOU:
   - cria um atalho na Área de Trabalho;
   - passa a iniciar sozinho quando o Windows liga;
   - abre o painel numa janela própria.

## A janela e o ícone perto do relógio

O Registrale funciona em segundo plano, como um antivírus: o ícone dele fica na **bandeja do sistema**, ao lado do relógio do Windows.

- **Fechar a janela não desliga o programa.** Ele continua rodando e faz as buscas no horário.
- Clique com o **botão direito** no ícone para ver o menu:

| Opção | Para que serve |
|---|---|
| **Abrir painel** | Reabre a janela (um clique no ícone faz o mesmo) |
| **Status** | Mostra a versão e se o serviço está no ar |
| **Verificar atualizações** | Procura uma versão nova |
| **Ver logs** | Abre a pasta de registros técnicos (útil para suporte) |
| **Reiniciar** | Reinicia o serviço, se algo parecer travado |
| **Sair** | Encerra o programa (as buscas automáticas param até ele abrir de novo) |

> Se a janela própria não abrir, o painel abre no navegador, no endereço `http://127.0.0.1:5000`. Funciona do mesmo jeito.

## Assistente de primeiro uso

Na primeira vez, um assistente de **9 passos** deixa tudo pronto para a busca das 8h. Você pode fechar no meio (botão **X**): na próxima abertura ele continua de onde parou.

| Passo | O que o assistente pergunta | Se você clicar em **Pular por enquanto** |
|---|---|---|
| 1. Boas-vindas | Se você quer trazer dados de uma instalação anterior (banco `database.db` e rotinas `.yaml`). Se ele achar dados antigos no computador, oferece **Importar dados detectados** | Começa do zero |
| 2. PDFs | Onde guardar os PDFs do DOU e como organizar as pastas | O arquivamento de PDFs fica desligado |
| 3. Abertura do painel | Se o painel pede usuário e senha ou abre direto neste computador | Mantém como está |
| 4. Rotina inicial | Horário da busca (padrão: **8h, segunda a sexta**), seções do DOU e órgãos | O botão vira **Manter padrão** e a rotina padrão continua ligada |
| 5. Empresas | De onde vêm os clientes: **Google Sheets**, **API do GestãoClick** ou **cadastro manual**. Dá para testar e sincronizar na hora | Nenhuma empresa é importada agora |
| 6. GestãoClick | Endereço e chaves da API, e se a sincronização automática fica ligada | A sincronização automática fica desligada |
| 7. E-mail | Se o Registrale envia e-mails; se sim, os dados do servidor e os destinatários, com envio de teste | O envio de e-mail fica desligado (as menções continuam sendo gravadas) |
| 8. Fonte da busca | Explica de onde o Registrale lê o DOU e permite trocar a fonte | Mantém a fonte recomendada |
| 9. Resumo | Mostra o que ficou ligado, desligado ou pendente e o próximo horário de busca | — |

No passo 9, o botão **Buscar agora** faz a busca de hoje para você conferir se tudo funciona.

**Pular não gera erro nem aviso:** a função só fica desligada até você ligá-la em **Configurações**.

**Refazer depois:** em **Configurações → Sistema e atualizações → Refazer configuração inicial**. Nada é apagado. Ao refazer, o botão de pular vira **Manter como está** e não desliga o que já estava ligado.

## Entrar com senha ou direto

Por padrão, neste computador, o painel abre direto, sem pedir senha. Quem acessar por outro endereço continua precisando de login.

Para exigir senha sempre: **Configurações → Usuários → Acesso ao painel**, interruptor **Exigir login**. Com o login ligado:

- a sessão termina após **30 minutos** sem uso;
- um relógio no topo mostra o tempo restante e, no último minuto, aparece o aviso para **Continuar**.

## A tela principal (Visão geral)

| Parte da tela | O que mostra |
|---|---|
| Barra superior | **Última sync** (última atualização da lista de empresas), **Última pesquisa** e **Próxima pesquisa** no DOU |
| Botão **Atualizar** | Recarrega os dados da aba aberta |
| Botão **Sincronizar bases** | Atualiza agora a lista de empresas a partir do GestãoClick e/ou do Google Sheets |
| Indicadores | **Empresas registradas**, **CNPJs monitorados**, **Menções hoje** e **Menções no mês** |
| **Menções recentes** | As últimas aparições encontradas, com atalho **Ver todas** |
| **Histórico de eventos** | Tudo o que o sistema fez: buscas, sincronizações, e-mails, erros |
| Avisos | Só aparecem quando há um problema real (por exemplo, e-mail ligado sem servidor). O botão **Resolver** leva direto à tela certa |

O tema claro/escuro é trocado pelo botão de sol/lua no topo.
