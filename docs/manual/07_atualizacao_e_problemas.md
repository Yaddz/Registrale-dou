# 7. Atualização, backup e problemas comuns

## Verificação de atualizações

1. Acesse **Configurações → Sistema e atualizações** (botão **Verificar atualizações**; o menu da bandeja também tem essa opção) no painel.
2. O app consulta a versão mais recente publicada nas Releases do GitHub, baixa o novo instalador e verifica o hash **SHA-256** antes de executar a atualização.
3. Você também pode baixar e executar o `Registrale-Setup-x.y.z.exe` manualmente por cima da instalação atual.

Todos os seus dados em `%LOCALAPPDATA%\Registrale` (banco de empresas, menções, configurações, logs e rotinas) e os PDFs em `Documentos\Registrale\DOU` são preservados.

## Desinstalação

Pelo menu *Configurações do Windows → Aplicativos* (ou `unins000.exe` na pasta do programa), a desinstalação remove apenas o aplicativo e os atalhos, perguntando antes se deseja manter ou remover os dados locais.

## Backup manual

Antes de migrar de máquina, copie a pasta `%LOCALAPPDATA%\Registrale` (com o aplicativo encerrado pela bandeja do sistema) e a sua pasta de PDFs.

## Problemas comuns e perguntas frequentes

### A rotina terminou como "Concluída com pendências"
Significa que pelo menos uma seção do DOU do dia ainda não estava disponível ou houve falha temporária na consulta/confirmação. O sistema agendará automaticamente novas tentativas a cada 60 minutos (até 4 vezes, até as 22h) e enviará e-mail apenas com as menções novas.

### A busca retornou 0 menções, mas tenho empresas cadastradas
1. Verifique em **Empresas** se há CNPJs **ativos** (não pausados).
2. Verifique em **Rotinas** se a rotina principal está **ativa** e com as seções desejadas marcadas (Seções 1, 2, 3 e Edição Extra).
3. Confira no log da execução se o status foi **Concluída com sucesso** ou **Concluída com pendências**.

### O ícone da bandeja não abre a janela
Clique com o botão direito no ícone do Registrale na bandeja do sistema e selecione **Abrir painel** (ou acesse `http://127.0.0.1:5000` no navegador).

### Erro de envio de e-mail ("Erro Envio E-mail")
As menções encontradas **já foram salvas** na aba **Menções**. Revise as credenciais SMTP em **Configurações → Integrações** ou desligue o interruptor do SMTP se não desejar envios por e-mail.
