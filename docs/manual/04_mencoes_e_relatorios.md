# 4. Menções e relatórios

Uma **menção** é uma publicação do DOU em que apareceu o CNPJ de uma empresa monitorada.

> **As menções nunca se perdem por causa do e-mail.** Toda menção é gravada no computador **antes** de qualquer envio. Se o e-mail estiver desligado ou falhar, ela continua na aba **Menções**.

## Aba Menções

Lista tudo o que já foi encontrado, da mais nova para a mais antiga. Um ponto verde indica menção encontrada hoje, e o número vermelho no menu lateral mostra quantas você ainda não viu.

- **Pesquisar:** por empresa, CNPJ ou trecho do texto.
- **Filtrar por data:** digite `DD/MM/AAAA`.
- A lista começa limitada; use **Carregar mais (+100)** ou **Exibir todas**.

### O que dá para fazer com cada menção

| Botão | O que faz |
|---|---|
| **Ver detalhes** | Mostra o trecho em que a empresa aparece, a seção e a data |
| **Abrir DOU** | Abre a matéria oficial no site da Imprensa Nacional (`in.gov.br`) |
| **Abrir PDF integral do dia** | Abre o PDF da edição guardado no seu computador (se o arquivamento estiver ligado) |
| **Enviar e-mail** | Envia a menção para alguém, com prévia antes do envio (precisa do e-mail ligado) |
| **Excluir menção** | Remove a menção do painel |

Para excluir várias de uma vez, marque as caixas de seleção e clique em **Excluir selecionadas**.

Na janela de detalhes há também **Parar de monitorar empresa**, para quando a menção mostra que o cliente não precisa mais ser acompanhado.

## Aba Relatórios

Serve para montar um recorte e exportar.

1. **Período:** use os atalhos (**Hoje**, **Últimos 7 dias**, **Este mês**, **Últimos 30 dias**, **Ano atual**) ou preencha **Data inicial** e **Data final**.
2. **Empresas:** escolha uma ou várias (deixe vazio para todas).
3. **Seção DOU:** uma seção ou **Todas as seções**.
4. Exporte pelo botão do topo:

| Botão | Resultado |
|---|---|
| **Excel** | Planilha `.xlsx` com empresa, seção, data, trecho e link de cada menção |
| **PDF** | Relatório formatado, pronto para mandar ao cliente ou arquivar |
| **Enviar por e-mail** | Manda o relatório por e-mail (precisa do e-mail ligado) |

A tela mostra até 100 resultados; a exportação leva todos os do filtro.

## Modelo do e-mail

Em **Configurações → Templates de e-mail** você muda o assunto e a aparência do e-mail de alerta. O editor tem modo visual, prévia com publicações de exemplo e código HTML.

Use as **variáveis** para o Registrale preencher sozinho cada e-mail:

| Variável | Vira |
|---|---|
| `{content}` | O bloco com todas as menções |
| `{empresa}` | Nome da empresa |
| `{cnpj}` | CNPJ da empresa |
| `{secao}` | Seção do DOU |
| `{data}` | Data da publicação |
| `{trecho}` | Trecho com o CNPJ destacado em amarelo |
| `{link}` | Link para a matéria no DOU |

Com o envio de e-mail desligado, essa tela fica travada.
