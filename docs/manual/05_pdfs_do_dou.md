# 5. PDFs do DOU

O Registrale pode guardar no seu computador o **PDF completo** de cada seção do DOU, todos os dias. Isso funciona como um arquivo de prova: mesmo que o site saia do ar, você tem a edição original.

Os PDFs vêm do site oficial `pesquisa.in.gov.br`, sem precisar de login.

## Ligar e escolher a pasta

Em **Configurações → Arquivo PDF DOU**:

1. Ligue **Arquivar PDFs**.
2. Em **Pasta de destino**, use **Procurar…** para escolher a pasta (padrão: `Documentos\Registrale\DOU`).
3. Em **Organização das pastas**, escolha uma das opções abaixo. A **Prévia** mostra como vai ficar.
4. Marque as **Seções arquivadas** e clique em **Salvar configurações**.

| Organização | Exemplo de onde o arquivo fica |
|---|---|
| Por ano e mês (padrão) | `DOU\2026\11\DOU_2026-11-24_Secao1.pdf` |
| Só por ano | `DOU\2026\DOU_2026-11-24_Secao1.pdf` |
| Tudo na mesma pasta | `DOU\DOU_2026-11-24_Secao1.pdf` |

Os arquivos se chamam `DOU_<data>_Secao1.pdf`, `Secao2`, `Secao3` e `SecaoExtra`.

Quando o PDF do dia já está arquivado, cada menção ganha também uma **Página destacada** em `<pasta dos PDFs>/destaques/<AAAA-MM-DD>/<cnpj_raiz>_<id>.pdf` (com a página da ocorrência e o CNPJ destacado). Você pode abri-la direto na aba **Menções** ou optar por anexá-la nos e-mails de alerta em **Configurações → Integrações**.

Se mudar a organização, o botão **Reorganizar PDFs existentes** move os arquivos antigos para o novo formato (pede confirmação antes). Nada é sobrescrito.

## Baixar um dia ou um mês que ficou para trás

Na mesma tela, em **Status e disparo manual**:

- **Arquivar data específica:** digite a data e clique em **Baixar dia**.
- **Arquivar mês completo:** escolha mês e ano e clique em **Baixar mês**.

O cartão mostra a última execução, o dia de referência e o resultado. Use **Atualizar status** para recarregar.

## Quanto espaço os PDFs ocupam

Em **Configurações → Armazenamento**, o cartão **PDFs do DOU** mostra:

- a pasta atual, os dias arquivados, o número de arquivos e o espaço ocupado;
- um **Resumo por mês**;
- o botão **Abrir pasta**, que abre a pasta no Explorador do Windows.

Mais abaixo, o **Cache interno** são cópias temporárias que o Registrale usa para ler o DOU. Ele existe mesmo com o arquivamento desligado e não substitui o seu arquivo de PDFs.
