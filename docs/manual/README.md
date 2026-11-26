# Manual do Usuário — Registrale-DOU

O Registrale-DOU lê o **Diário Oficial da União (DOU)** todos os dias e avisa quando alguma empresa cliente do escritório aparece numa publicação. Você cadastra as empresas uma vez; o aplicativo faz a leitura sozinho, guarda cada aparição encontrada (a **menção**) e, se você quiser, manda um e-mail com o resumo.

Este manual também está na aba **Manual** do painel e pode ser baixado em Markdown pelo botão **Baixar manual (.md)**.

## Como o dia a dia funciona

1. **Às 8h dos dias úteis** (horário padrão), o Registrale pesquisa a edição do dia nas Seções 1, 2 e 3 e nas Edições Extras.
2. Cada publicação que cita o CNPJ de uma empresa ativa vira uma **menção**, gravada no computador.
3. Se o envio de e-mail estiver ligado, os destinatários recebem as menções novas.
4. Se o arquivamento estiver ligado, o PDF completo de cada seção do dia é salvo na sua pasta.
5. Se alguma seção ainda não tiver sido publicada, o Registrale tenta de novo mais tarde, sozinho.

Você só precisa entrar no painel para conferir as menções, gerar relatórios ou mudar alguma configuração.

## Por onde começar

| Se você quer… | Leia |
|---|---|
| Instalar e configurar pela primeira vez | [1. Primeiros passos](01_primeiros_passos.md) |
| Cadastrar ou importar empresas | [2. Empresas](02_empresas.md) |
| Mudar o horário, pesquisar um dia ou um mês | [3. Rotinas e buscas](03_rotinas_e_buscas.md) |
| Ver o que foi encontrado e gerar relatórios | [4. Menções e relatórios](04_mencoes_e_relatorios.md) |
| Guardar os PDFs do DOU | [5. PDFs do DOU](05_pdfs_do_dou.md) |
| Ajustar e-mail, usuários e integrações | [6. Configurações](06_configuracoes.md) |
| Atualizar, fazer backup ou resolver um problema | [7. Atualização e problemas](07_atualizacao_e_problemas.md) |
| Entender um termo (raiz do CNPJ, INLABS, SMTP…) | [8. Glossário](08_glossario.md) |

## Perfis de acesso

| Perfil | Pode fazer |
|---|---|
| **Administrador** (`master`) | Tudo: configurações, usuários, rotinas, limpeza de dados |
| **Consulta** (`user`) | Ver menções e empresas, disparar buscas e gerar relatórios. Não vê a aba **Configurações** nem cria ou exclui rotinas |

Quando o painel abre direto, sem senha (o padrão neste computador), você entra como administrador.

> **Convenções deste manual:** nomes em **negrito** são botões, abas ou campos exatamente como aparecem na tela. O caminho **Configurações → Integrações** significa: abra a aba **Configurações** no menu lateral e depois a seção **Integrações**.
