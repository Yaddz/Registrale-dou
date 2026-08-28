
## Changelog

## [0.12.0] - 2026-08-28

* **Editor Visual de Templates de E-mail (WYSIWYG)**: Editor interativo em tempo real com Destaque Amarelo DOU (`#FFA`), menu flutuante de variáveis `{content}`, `{empresa}`, `{cnpj}`, `{secao}`, `{data}`, `{trecho}`, `{link}` e histórico Desfazer/Refazer.
* **Seletor de Data Lógica e Detecção de Feriados**: Suporte a formatos `DD/MM/AAAA` e `AAAA-MM-DD`, calendário flutuante estável, detecção de feriados nacionais e comutação para API DOU para datas > 120 dias.
* **Busca Mensal e Download INLABS em Lote**: Download multi-dias com sessão persistente sem bloqueio de taxa e suporte ao Cenário Misto.

---

## [0.1.0] - 2023-08-31

Altera a forma de encontrar os arquivos de configuração das DAGs (`dag_confs/*.yml`).

Antes considerava que a pasta `dag_confs/` estava na mesma raiz que os arquivos do ro-dou em `./src`. Agora o caminho da(s) pasta(s) deve ser informado pela variável de ambiente `RO_DOU__DAG_CONF_DIR` e separado por `:` quando mais de um.

**Exemplo:**

As pastas `/opt/airflow/dags/repo1/dag_confs` e `/opt/airflow/dags/repo2/dag_confs` possuem arquivos de configuração (yaml) para geração das DAGs do rodou. A variável de ambiente `RO_DOU__DAG_CONF_DIR` deve ser atribuída assim:

```shell
RO_DOU__DAG_CONF_DIR=/opt/airflow/dags/repo1/dag_confs:/opt/airflow/dags/repo2/dag_confs
```

Esta alteração permite que os arquivos de configuração das DAGs (`dag_confs/*.yml`) estejam em qualquer pasta da máquina ou container.