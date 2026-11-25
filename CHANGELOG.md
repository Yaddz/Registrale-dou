# Changelog — Registrale-DOU

Histórico de versões do aplicativo desktop **Registrale-DOU** (Windows).  
O histórico anterior ao fork (base **Ro-DOU**, até `0.14.0`) está arquivado em [`docs/upstream/CHANGELOG.md`](docs/upstream/CHANGELOG.md) e no repositório oficial do [Ro-DOU](https://github.com/gestaogovbr/Ro-dou).

---

## [1.3.0] — 2026-11-25 (Sprints 11 a 16)

### Busca e confiabilidade (Sprint 11)
- Busca diária sem dependência do PostgreSQL portátil do INLABS quando ausente no instalador (`-SkipPostgresDownload`).
- Fim dos erros repetidos `NoneType is not iterable` no log ao consultar o INLABS indisponível.
- Rastreamento de cobertura por seção (Seções 1, 2, 3 e Edição Extra) com status **"Concluída com pendências"** (`partial`) quando falta seção ou confirmação.
- Nova tentativa automática no mesmo dia (intervalo de 60 min, até 4 tentativas, até 22h), enviando e-mail apenas das menções novas.
- Confirmação obrigatória pela API do DOU (`strict_confirm`) quando há filtro de órgão (`department`) na rotina.
- Alinhamento dos parâmetros padrão da rotina principal com a baseline (`department: []`, `is_exact_search: false`, `field: TUDO`, Seções 1/2/3 + `EDICAO_EXTRA`).

### Configurações, SMTP e atividade (Sprint 12)
- Interruptores de ativar/pausar unificados num único modelo visual e persistindo o estado no banco.
- Assistente de configuração reconhecendo corretamente integrações e rotinas pausadas.
- Interruptor global de SMTP desligado desabilita campos de e-mail dependentes, permite salvar sem destinatários e bloqueia envios em todo o app mantendo o registro de menções.
- Interruptor padronizado para o arquivamento de PDFs do DOU.
- Painel de atividade visível para tarefas em segundo plano e botão **Atualizar** na barra de ações.

### Interface e armazenamento de PDFs (Sprint 13)
- Ajustes visuais na barra lateral recolhida, cards de alerta, tela do Google Sheets (campo de intervalo de sincronização) e template de e-mail.
- Nova aba **Armazenamento** exibindo os meses de PDFs arquivados e o espaço ocupado em disco.

### Onboarding completo (Sprint 14)
- Assistente guiado de primeiro uso cobrindo pasta e organização dos PDFs, rotina inicial, cadastro de empresas (manual, Google Sheets ou GestãoClick), SMTP, INLABS e resumo final.

### Documentação unificada e limpeza (Sprint 15)
- Consolidação da documentação em `docs/` (`manual/`, `tecnico/`, `upstream/` e `projeto/`), removendo duplicatas e páginas de Docker/WSL/Kubernetes do MkDocs.
- Manual único do analista atualizado cobrindo os Sprints 11 a 14, consumido diretamente pelo painel (`/api/manual`) e pelo instalador.
- Limpeza de sobras locais do repositório e separação do `CHANGELOG.md` próprio do Registrale-DOU.

---

## [1.2.0] — 2026-11-24 (Sprints 9 e 10)

### Novidades
- Janela própria no Windows via `pywebview` (WebView2), com fallback automático para o navegador padrão e minimização para a bandeja do sistema.
- Ícone oficial do Registrale-DOU aplicado no executável e atalhos do instalador.
- Escolha da pasta e do layout de organização dos PDFs do DOU (`ano_mes`, `ano`, `nenhum`) no primeiro acesso e em Configurações.
- Status detalhado do arquivamento de PDFs, máscara de data (`DD/MM/AAAA`), seletor de mês e exibição da última sincronização.
- Avisos dispensáveis no painel, interruptor de ativação/desativação do SMTP e remoção da lista de clientes do pacote do instalador.
- Login opcional no acesso local (`localhost`).

---

## [1.1.0] — 2026-11-24 (Sprints 6.1 a 8)

### Novidades
- Remoção completa de Docker, Apache Airflow e gunicorn; execução 100% local com **Waitress** + **APScheduler** e shim de compatibilidade (`compat/airflow_shim/`).
- Contingência automática para INLABS indisponível ou em manutenção via busca no **PDF integral do DOU** (`pesquisa.in.gov.br`) com confirmação na API do DOU (`inlabs_fallback`: `pdf` | `api` | `off`).
- Validação de paridade de 100% com a baseline de novembro/2026 (26 menções de 16 empresas, incluindo identificação apenas pela raiz de CNPJ).

---

## [1.0.0] — 2026-11-23 (Sprints 0 a 6)

### Lançamento do aplicativo Windows
- Instalador nativo para Windows (`Registrale-Setup-x.y.z.exe`) com Python 3.11 *embeddable* e Inno Setup, sem necessidade de Docker ou WSL.
- Launcher na bandeja do sistema (`windows/launcher.pyw`) com inicialização automática com o Windows.
- Executor local (`LocalExecutor`) com persistência de execuções em `job_runs` (SQLite) e logs rotacionados por execução.
- Arquivamento automático dos PDFs integrais do DOU e suporte opcional ao PostgreSQL portátil para carga INLABS.
- Migração de dados de instalações anteriores e verificador de atualizações via GitHub Releases com validação SHA-256.
