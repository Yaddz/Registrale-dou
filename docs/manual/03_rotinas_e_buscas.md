# 3. Rotinas e buscas

Uma **rotina** é uma busca programada: diz *o que* procurar, *onde* (seções e órgãos do DOU), *quando* e *para quem* mandar o e-mail. A aba **Rotinas** mostra todas elas.

## Os dois tipos de rotina

| Tipo | O que procura | Quem mantém |
|---|---|---|
| **Rotina principal** | Os CNPJs de todas as empresas ativas | O próprio Registrale: a lista de CNPJs se atualiza sozinha quando você cadastra, pausa ou sincroniza empresas |
| **Personalizada** | Palavras ou termos que você escolher (ex.: "pregão eletrônico", nome de um sócio) | Você, pelo botão **Nova rotina** (só administrador) |

## Configuração recomendada da rotina principal

Estes são os valores que o assistente deixa prontos e que dão a cobertura mais completa:

| Opção | Valor recomendado | Por quê |
|---|---|---|
| Frequência | 8h, segunda a sexta | O DOU sai cedo nos dias úteis |
| Seções do DOU | Seção 1, Seção 2, Seção 3 e Edições Extras | Empresas aparecem em todas: normas (1), pessoal (2), contratos e editais (3) |
| Órgãos específicos | Vazio (todos os órgãos) | Um filtro de órgão pode esconder menções reais |
| Busca por termo exato | Desligada | Assim a busca acha matriz e filiais pela raiz do CNPJ |

> **Cuidado com o filtro de órgão.** Se preencher **Órgãos específicos**, use o nome como aparece no DOU (ex.: *Agência Nacional de Vigilância Sanitária*). Siglas comuns como ANVISA, INPI, MAPA ou ANP são convertidas sozinhas. Com filtro, o Registrale só aceita uma menção depois de confirmar na API do DOU que ela é mesmo daquele órgão.

## Mudar uma rotina

Na aba **Rotinas**, clique na engrenagem (**Configurar rotina**). A janela tem três partes:

1. **Identificação e agenda:** nome e **Frequência de busca** (horários prontos ou **Personalizado (Cron)** para quem conhece o formato).
2. **Parâmetros de busca:** termos (um por linha), seções, órgãos, busca exata e termos a ignorar. Na rotina principal, aqui ficam também os atalhos para adicionar empresas e o **Monitoramento por Origem**.
3. **Configuração de alertas:** **E-mails de Destino** e **Assunto do E-mail**. Se o envio de e-mail estiver desligado, esses campos ficam travados e podem ficar vazios.

Clique em **Salvar configurações**. A mudança vale a partir da próxima busca.

**Pausar uma rotina:** use o interruptor no cartão da rotina (**Ativa** / **Pausada**). Rotina pausada não roda no horário nem pode ser disparada à mão.

**Excluir:** só rotinas personalizadas, pelo ícone de lixeira. A rotina principal não pode ser excluída.

## Pesquisar agora ou um dia específico

1. No cartão da rotina, clique em **Pesquisar no DOU** (rotina principal) ou **Executar agora** (personalizada).
2. Deixe a data em branco para pesquisar **hoje**, ou digite uma data no formato `DD/MM/AAAA`.
3. Clique em **Iniciar Busca**.

O painel avisa se a data cair num fim de semana ou feriado (dias sem edição regular do DOU). A busca roda em segundo plano: acompanhe pela barra de status no topo e pelo **Histórico de eventos**.

## Busca mensal

Serve para conferir um mês inteiro de uma vez, por exemplo ao cadastrar empresas novas ou para auditoria.

1. No cartão da rotina, clique em **Busca mensal**.
2. Escolha o **Mês** e o **Ano**.
3. Clique em **Verificar e iniciar** e confirme na janela seguinte, que mostra quantos dias serão pesquisados e de onde.

O Registrale pesquisa cada dia útil do mês e escolhe sozinho a melhor fonte para cada dia. **É demorado** (pode levar horas num mês cheio). Você pode fechar a janela: o programa continua trabalhando pela bandeja. No fim, as menções aparecem na aba **Menções** e, com o e-mail ligado, chega um relatório.

## Como saber se a busca deu certo

O resultado de cada busca aparece no **Histórico de eventos** e na barra de status:

| Resultado | O que significa | O que fazer |
|---|---|---|
| **Busca Concluída** | Todas as seções do dia foram lidas | Nada. Se não houver menções, é porque nenhuma empresa apareceu |
| **Concluída com pendências** | Alguma seção ainda não tinha sido publicada ou não respondeu. As menções já encontradas foram gravadas | Nada: o Registrale tenta de novo sozinho |
| **Erro Envio E-mail** | A busca funcionou e as menções estão salvas; só o e-mail falhou | Revise o servidor de e-mail ([6. Configurações](06_configuracoes.md#e-mail-smtp)) |

**"Sem menções" é diferente de "busca incompleta".** Se o status é **Busca Concluída** e não há menções, o dia foi lido por inteiro e nenhum cliente apareceu.

### Novas tentativas automáticas

Quando uma busca termina **com pendências**, o Registrale tenta de novo **a cada 60 minutos**, até **4 vezes** no mesmo dia e no máximo até as **22h**. O e-mail dessas novas tentativas traz **só as menções novas**, para você não receber a mesma coisa duas vezes.

### E se o computador estava desligado às 8h?

Assim que o Registrale abrir, ele faz a busca que ficou para trás (uma vez por dia).
