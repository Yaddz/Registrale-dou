# 6. Configurações

A aba **Configurações** só aparece para administradores. Ela é dividida em seções:

| Seção | Para que serve |
|---|---|
| **Usuários** | Exigir ou não senha para abrir o painel; criar e remover usuários |
| **Google Sheets** | Ligar a planilha de clientes ([2. Empresas](02_empresas.md#ligar-uma-planilha-do-google-sheets)) |
| **Integrações** | E-mail (SMTP), API do GestãoClick e fonte de leitura do DOU |
| **Arquivo PDF DOU** | Guardar os PDFs completos do DOU ([5. PDFs do DOU](05_pdfs_do_dou.md)) |
| **Templates de e-mail** | Aparência do e-mail de alerta ([4. Menções e relatórios](04_mencoes_e_relatorios.md#modelo-do-e-mail)) |
| **Limpeza do sistema** | Apagar dados em massa (cuidado: não tem volta) |
| **Armazenamento** | Espaço ocupado pelos PDFs e pelo cache |
| **Logs do sistema** | Registros técnicos, úteis para suporte |
| **Sistema e atualizações** | Versão, atualização, importação de dados antigos e assistente de primeiro uso |

## Usuários

- **Acesso ao painel:** o interruptor **Exigir login** decide se o painel pede senha. Desligado, ele abre direto como administrador, e só neste computador.
- **Novo usuário:** informe **Username**, **Senha** e **Nível** (**Master** = administrador, **Consulta** = só leitura e buscas) e clique em **Criar acesso**.

Ao religar o **Exigir login**, quem estava usando o painel sem senha é desconectado.

## E-mail (SMTP)

O SMTP é o servidor que envia os e-mails (o mesmo que o seu programa de e-mail usa). Fica em **Configurações → Integrações**, cartão **SMTP & Notificações**.

1. Ligue **Enviar e-mails**.
2. Preencha **Servidor SMTP**, **Porta**, **Usuário**, **Senha** e **E-mail de envio (From)**.
3. Coloque um endereço em **Destinatário para teste SMTP** e envie o teste.
4. Clique em **Salvar configurações**.

> **Gmail ou Microsoft 365 com verificação em duas etapas:** a senha normal não funciona. Gere uma **senha de app** na conta de e-mail e use-a no campo **Senha**. No Gmail, o comum é servidor `smtp.gmail.com`, porta `587`.

Os destinatários dos alertas diários ficam na própria rotina ([3. Rotinas e buscas](03_rotinas_e_buscas.md#mudar-uma-rotina)).

**Com o envio desligado** (o padrão numa instalação nova): nenhum e-mail sai, os campos ficam travados, rotinas podem ser salvas sem destinatário e **as menções continuam sendo gravadas normalmente**. O cartão mostra **Desativado**, sem aviso de pendência.

## API do GestãoClick

No cartão **API GestãoClick & Caminhos**: **Base URL API**, **Access token**, **Secret access token** e o interruptor **Sincronização automática**. Desligado, o cartão mostra **Desativada** e não gera aviso.

## De onde o Registrale lê o DOU

No cartão **Credenciais INLABS**, o campo **Fonte quando o INLABS estiver fora** define como a busca é feita. Na instalação padrão o INLABS (serviço de download em lote da Imprensa Nacional) **não vem instalado**, então essa é a fonte usada todos os dias:

| Opção | Como funciona | Quando escolher |
|---|---|---|
| **PDF integral + API do DOU** (recomendado) | Baixa os PDFs oficiais do dia, procura as raízes de CNPJ no texto e confirma cada achado na API do DOU para guardar o link da matéria | Sempre, salvo orientação do suporte |
| **API do DOU (direto)** | Pergunta à API do DOU por cada CNPJ | Se o site dos PDFs estiver fora; fica mais lento com muitas empresas |
| **Desligado** | Usa só o INLABS local | Apenas se o INLABS estiver instalado e funcionando |

O aviso "O INLABS local não está instalado nesta versão" é normal e não é um problema: os campos de usuário e senha do INLABS ficam travados porque não são usados.

## Limpeza do sistema

> **Atenção:** estas ações **não podem ser desfeitas**. Antes, faça um backup ([7. Atualização e problemas](07_atualizacao_e_problemas.md#backup)).

| Botão | O que apaga |
|---|---|
| **Limpar dados** | Tudo: empresas, menções, histórico de eventos, execuções e logs de execução. As configurações e rotinas ficam |
| **Limpar INLABS** | Dias com mais de 120 dias no banco do INLABS local (só faz diferença se ele estiver instalado) |
| **Limpar histórico** | O **Histórico de eventos** da Visão geral |
| **Limpar menções** | **Todas** as menções do painel |

## Logs do sistema

Mostra o registro principal (`registrale.log`) e um registro por busca executada. Use quando o suporte pedir ou para entender um erro.

## Sistema e atualizações

- **Versão e Atualizações:** mostra a versão atual e o botão **Verificar atualizações** ([7. Atualização e problemas](07_atualizacao_e_problemas.md)).
- **Assistente de Importação:** traz empresas, menções, configurações, modelos e rotinas de uma instalação anterior. Um backup do banco atual é feito antes.
- **Refazer configuração inicial:** reabre o assistente de 9 passos sem apagar nada.
