# 5. PDFs integrais do DOU e Armazenamento

## Arquivamento automático

O Registrale-DOU pode baixar e guardar automaticamente o **PDF integral** de cada seção do DOU (`pesquisa.in.gov.br`, sem necessidade de login) como registro permanente das publicações.

- O recurso é ativado ou desativado pelo interruptor padronizado em **Configurações → Arquivo PDF DOU**.
- O status do arquivamento (em execução, último dia arquivado e eventuais falhas) aparece diretamente no painel.

## Pasta e organização

Você pode configurar a pasta de destino (padrão: `Documentos\Registrale\DOU`) e o layout dos arquivos:

| Layout | Estrutura gerada |
|---|---|
| `ano_mes` (padrão) | `<pasta>\2026\11\DOU_2026-11-24_Secao1.pdf` |
| `ano` | `<pasta>\2026\DOU_2026-11-24_Secao1.pdf` |
| `nenhum` | `<pasta>\DOU_2026-11-24_Secao1.pdf` |

Os nomes seguem `DOU_<AAAA-MM-DD>_Secao1.pdf`, com `Secao2`, `Secao3` e `SecaoExtra` para as demais seções. **Reorganizar PDFs existentes** (com confirmação) move arquivos antigos para o layout escolhido sem sobrescrever nada.

## Disparo manual e mensal de PDFs

Na seção de arquivamento, você pode baixar manualmente os PDFs de:

- **Arquivar data específica** (botão **Baixar dia**)
- **Arquivar mês completo** (seletor de mês e ano, botão **Baixar mês**)

## Aba Armazenamento

Em **Configurações → Armazenamento**, o cartão **PDFs do DOU** mostra a pasta atual, o total de dias arquivados, arquivos e espaço ocupado e um **Resumo por mês** (dias, arquivos e espaço). O botão **Abrir pasta** abre a pasta no Explorador e **Atualizar** recarrega os números. Abaixo, o **Cache interno** (PDFs temporários e textos extraídos) aparece à parte, pois é usado na busca por PDF quando o arquivamento está desativado.
