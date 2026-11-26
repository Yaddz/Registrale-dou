# 7. Atualização, backup e problemas comuns

## Atualizar o Registrale

1. Abra **Configurações → Sistema e atualizações** e clique em **Verificar atualizações** (ou use a mesma opção no menu do ícone da bandeja).
2. Se houver versão nova, clique em **Baixar e atualizar**. O Registrale confere se o arquivo baixado é o original (verificação SHA-256) antes de instalar.

Também dá para baixar o `Registrale-Setup-x.y.z.exe` novo e instalar por cima.

**Seus dados ficam:** empresas, menções, configurações, rotinas e PDFs são preservados na atualização.

## Onde ficam os arquivos

| O quê | Pasta | Na atualização |
|---|---|---|
| Programa | `%LOCALAPPDATA%\Programs\Registrale` | É substituído |
| Dados (banco `database.db`, rotinas, logs) | `%LOCALAPPDATA%\Registrale` | É preservado |
| PDFs do DOU | `Documentos\Registrale\DOU` (ou a pasta que você escolheu) | É preservado |

> Para abrir uma dessas pastas, cole o caminho (por exemplo `%LOCALAPPDATA%\Registrale`) na barra de endereço do Explorador de Arquivos.

## Backup

1. Encerre o programa: botão direito no ícone da bandeja → **Sair**.
2. Copie a pasta `%LOCALAPPDATA%\Registrale` inteira para um lugar seguro.
3. Copie também a sua pasta de PDFs.

Para restaurar em outro computador, instale o Registrale e use o **Assistente de Importação** (passo 1 do assistente ou **Configurações → Sistema e atualizações**) com o `database.db` copiado.

## Desinstalar

Pelo Windows: **Configurações → Aplicativos → Registrale-DOU → Desinstalar**. O desinstalador pergunta se você quer apagar também os dados locais. A resposta recomendada é **Não**, para poder reinstalar depois sem perder nada.

## Problemas comuns

### A busca terminou "com pendências"

Alguma seção do DOU do dia ainda não tinha saído ou não respondeu a tempo. As menções já encontradas estão gravadas. O Registrale tenta de novo sozinho a cada hora (até 4 vezes, até as 22h) e o e-mail das novas tentativas traz só o que for novo. Não precisa fazer nada.

O evento no **Histórico** traz o **Motivo**. Os mais comuns:

- **"Portal do DOU indisponível"**: o site `in.gov.br` ficou fora do ar durante a busca. O Registrale desiste da consulta pelo site em poucos minutos (em vez de ficar horas tentando) e procura as empresas no **PDF integral** do dia; só fica pendente o que nem o PDF conseguiu cobrir.
- **"N CNPJ(s) sem resposta do portal"**: o site falhou só para algumas empresas; elas foram procuradas no PDF integral e, se ainda faltar alguma, aparecem listadas aqui.

Se o e-mail sair com o aviso **"resultado INCOMPLETO"**, as publicações listadas são reais; o que faltou será procurado nas novas tentativas. Um dia com o portal fora **nunca** aparece como "0 menções encontradas".

### Apareceu "Busca Falhou"

A busca parou por um erro inesperado (a mensagem vem no evento). O resultado daquele dia não está completo: rode **Pesquisar no DOU** na rotina principal mais tarde. Se repetir, envie o arquivo de log (ícone da bandeja → **Ver logs**) para o suporte.

### A busca não encontrou nenhuma menção

Na maioria dos dias isso é normal: nenhum cliente apareceu no DOU. Para ter certeza:

1. No **Histórico de eventos**, veja se a busca terminou como **Busca Concluída** (dia lido por inteiro).
2. Na aba **Empresas**, confira se há empresas com status **Monitorado (Ativo)**.
3. Na aba **Rotinas**, confira se a rotina principal está **Ativa**, com as quatro seções marcadas e **Órgãos específicos** vazio.

### Cadastrei uma empresa hoje. Quando ela entra na busca?

Na próxima busca automática. Para ver o dia de hoje na hora, use **Pesquisar no DOU** na rotina principal.

### Apareceu "Erro Envio E-mail"

A busca funcionou e as menções estão na aba **Menções**. Só o envio falhou. Revise o servidor em **Configurações → Integrações** (veja a dica da senha de app em [6. Configurações](06_configuracoes.md#e-mail-smtp)) ou desligue **Enviar e-mails** se não precisar deles.

### A planilha do Google dá erro de permissão (403)

A planilha não foi compartilhada com a conta de serviço. No Google Sheets, clique em **Compartilhar** e adicione, como **Leitor**, o e-mail que aparece em **Configurações → Google Sheets** (botão **Copiar e-mail**).

### O painel não abre

Clique com o botão direito no ícone da bandeja e escolha **Abrir painel**. Se não houver ícone, abra o Registrale-DOU pelo atalho da Área de Trabalho. Se a janela não aparecer, acesse `http://127.0.0.1:5000` no navegador. Persistindo, use **Reiniciar** no menu da bandeja.

Se o programa já estiver rodando, abrir o atalho de novo traz a janela do painel para a frente (nada de abrir uma segunda cópia). O aviso **"O Registrale-DOU já está aberto"** só aparece se a cópia em execução for de uma versão antiga: nesse caso use o ícone da bandeja → **Abrir painel**. Não é preciso finalizar processos no Gerenciador de Tarefas; se o programa tiver sido encerrado à força, ele mesmo fecha o servidor antigo na próxima abertura.

### O computador estava desligado no horário da busca

Não tem problema: ao abrir, o Registrale faz a busca que ficou pendente.

### Preciso pesquisar um mês antigo

Use a **Busca mensal** da rotina ([3. Rotinas e buscas](03_rotinas_e_buscas.md#busca-mensal)). Meses antigos são consultados direto na API do DOU.
