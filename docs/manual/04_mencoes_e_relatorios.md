# 4. Menções, relatórios e atividade

## Registro garantido antes do e-mail

Toda menção encontrada é gravada no banco SQLite local (`mentions`) **antes** de qualquer tentativa de envio de e-mail. Se o servidor SMTP estiver desligado ou falhar, as menções continuam salvas no painel e a execução registra o status apropriado (como `Erro Envio E-mail` quando apenas o envio falhou).

## Filtros e visualização

Na aba **Menções**, há uma busca por empresa, CNPJ, data ou trecho e um filtro de data (`DD/MM/AAAA`). A listagem inicial é limitada; use **Carregar mais** ou **Exibir todas**.

Na aba **Relatórios**, é possível filtrar por empresas (uma ou várias), seção do DOU (Seção 1, 2, 3 ou Edições Extras) e período (data inicial e final).

Cada menção tem os atalhos **Abrir DOU** (matéria oficial em `in.gov.br`, quando disponível/confirmado) e **Abrir PDF integral do dia** (arquivado localmente), além de ver detalhes, enviar por e-mail (com o SMTP ligado) e excluir.

## Exportação de relatórios

Na aba **Relatórios** (botões **Excel**, **PDF** e **Enviar por e-mail**):

- **Excel (`.xlsx`):** exporta a listagem filtrada.
- **PDF:** gera relatório formatado para envio ao cliente ou arquivo interno.
- **Enviar por e-mail:** disponível com o SMTP ligado.

A aba **Empresas** tem seu próprio **Exportar Excel**.

## Template de e-mail

Em **Configurações → Templates de e-mail**, você pode personalizar o assunto e o corpo HTML dos alertas usando as variáveis disponíveis (exibidas em painel lateral organizado sem quebra de layout).

## Painel de atividade e botão Atualizar

- Tarefas em segundo plano (buscas diárias, busca mensal, sincronização de empresas e arquivamento de PDFs) exibem progresso visível na barra de atividade.
- O botão **Atualizar** na barra de ações permite recarregar imediatamente o estado das execuções, menções e sincronizações.
