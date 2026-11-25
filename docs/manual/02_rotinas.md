# 2. Rotinas, buscas e cobertura por seção

## Rotina principal (`Pesquisa_cnpj.yaml`)

A rotina principal é gerada automaticamente pelo painel a partir das empresas ativas cadastradas no banco, dividida em blocos de até **1.500 CNPJs** por bloco de busca.

### Padrões recomendados (baseline)

Para garantir a mesma cobertura da baseline validada do sistema, a rotina principal usa (conforme o assistente de primeiro uso):

- **Seções:** Seção 1, Seção 2, Seção 3 e **Edições Extras** (`SECAO_1`, `SECAO_2`, `SECAO_3`, `EDICAO_EXTRA`)
- **Órgãos (`department`):** vazio `[]` (pesquisa em **todos os órgãos**)
- **Busca exata (`is_exact_search`):** desligada (`false`)
- **Campo (`field`):** `TUDO`

> **Atenção ao filtrar órgãos:** quando uma rotina define filtro de órgão (`department` preenchido), a busca por contingência em PDF ativa a **confirmação obrigatória pela API do DOU** (`strict_confirm`) para garantir que a matéria pertença ao órgão selecionado.

## Agendamento automático e recuperação

- O agendador interno (`APScheduler`) executa as rotinas ativas no horário configurado (fuso `America/Sao_Paulo`).
- Se o computador estava desligado no horário agendado, o Registrale executa a rotina pendente assim que for iniciado (*misfire recovery*, uma vez por dia).
- **Interruptor ativar/pausar:** o interruptor na lista de rotinas salva o estado imediatamente e é reconhecido pelo assistente de configuração.

## Cobertura por seção e "Concluída com pendências"

Cada execução diária verifica se todas as seções esperadas (Seções 1, 2, 3 e Edições Extras disponíveis) foram efetivamente consultadas e confirmadas:

- **Concluída com sucesso:** todas as seções aplicáveis foram verificadas sem falhas.
- **Concluída com pendências (`partial`):** o dia teve resultado parcial (por exemplo, alguma seção ainda não estava publicada ou houve falha temporária de consulta/confirmação). A tela distingue claramente **"sem menções"** de **"busca incompleta"**.

### Nova tentativa automática no mesmo dia

Quando uma execução termina como **"Concluída com pendências"** (`partial`):

- O sistema agenda automaticamente uma nova tentativa para o mesmo dia a cada **60 minutos**.
- São realizadas até **4 tentativas** no mesmo dia, respeitando o limite das **22h**.
- Se o SMTP estiver ativo, o e-mail enviado após uma nova tentativa inclui **apenas as menções novas** ainda não notificadas, evitando alertas repetidos.

## Buscas manuais e busca mensal

- **Executar agora:** na lista de **Rotinas de busca**, o botão abre uma janela para escolher a data da edição do DOU a pesquisar. A rotina precisa estar ativa.
- **Busca mensal:** dispara a busca para todos os dias do mês escolhido (mês e ano), em um processo demorado acompanhado na barra de atividade.
