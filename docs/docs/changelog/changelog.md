
## Changelog

## [0.14.0] - 2026-09-02

* **Proteção e Estabilidade de Buscas Temporárias (API DOU & Histórico)**:
  * Verificação ativa via API REST do Airflow antes de qualquer limpeza de DAGs temporárias (`cleanup_orphaned_temp_dags`), preservando execuções com status `running` ou `queued`.
  * Janela de tolerância estendida para 1 hora (`max_age_seconds=3600`) em `get_routines()` e no boot da aplicação, evitando interrupções em buscas volumosas.
  * Elevação do `--max-requests` de 200 para 5.000 (e jitter para 500) no Gunicorn, prevenindo término prematuro de threads daemon em segundo plano causadas por polling da UI.
  * Resgate e consolidação no SQLite das menções capturadas via API Oficial do DOU em pesquisas de meses fora da janela INLABS (> 120 dias).
* **Automações e Scripts Windows**:
  * Correções nos scripts `instalar.bat` (parênteses no `echo`) e `desinstalar.bat` (parsing de `else` e destravamento de permissões com `takeown`/`icacls`).
* **Storage PostgreSQL**:
  * Persistência do PostgreSQL em Docker named volume para integridade do acervo histórico INLABS.

---

## [0.13.0] - 2026-08-29

* **PWA & Desktop App**: Suporte completo a Progressive Web App (manifest, ícones em alta resolução e service worker) e instalador desktop automatizado para Windows (`instalar.bat` / `desinstalar.bat`).
* **Exclusão de Registros Obsoletos (Sheets)**: Opção configurável para remover automaticamente empresas apagadas da planilha Google Sheets.
* **Filtros e Relatórios**: Normalização semântica do filtro de seções do DOU (`matchSection`) e exportações em memória via `io.BytesIO`.
* **Performance e Banco**: 4 novos índices no SQLite, conexão singleton para PostgreSQL, compilação estática de regex e aumento do limite de sessões para 10.000.

---

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