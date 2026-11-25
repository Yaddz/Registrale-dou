![banner](docs/img/banner.png)

# Registrale-DOU

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.1-black.svg)](https://flask.palletsprojects.com/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

O **Registrale-DOU** é um aplicativo desktop para Windows para monitoramento automatizado, auditoria e *clipping* contínuo de publicações no **Diário Oficial da União (DOU — Seções 1, 2, 3 e Edições Extras)** que citam empresas clientes por raiz de CNPJ.

É um fork customizado do **[Ro-DOU](https://gestaogovbr.github.io/Ro-dou/)** (Ministério da Gestão e da Inovação em Serviços Públicos — MGI), empacotado com painel web próprio (Flask + Waitress + APScheduler), banco SQLite, arquivamento automático do PDF integral do DOU e integração opcional com PostgreSQL portátil para o INLABS.

---

## Requisitos

- **Sistema operacional:** Windows 10 ou Windows 11 (64 bits)
- **Acesso à rede:** conexão com a internet para consultar `in.gov.br`, `pesquisa.in.gov.br`, `inlabs.in.gov.br` (opcional), Google Sheets / GestãoClick e servidor SMTP
- **Espaço em disco:** ~300 MB para o programa (ou ~800 MB com PostgreSQL portátil para INLABS) + espaço para os PDFs arquivados

---

## Instalação (Windows)

1. Baixe o instalador `Registrale-Setup-x.y.z.exe` (e confira o hash `.sha256` publicado na release).
2. Execute o instalador. Não é necessário Docker, WSL, terminal ou instalação prévia de Python.
3. O instalador grava o aplicativo em `%LOCALAPPDATA%\Programs\Registrale`, cria o atalho na Área de Trabalho e registra a inicialização automática com o Windows (`Startup\Registrale-DOU.lnk`).
4. Ao iniciar, o ícone do Registrale aparece na **bandeja do sistema** (ao lado do relógio) e abre o painel em uma **janela própria** (ou no navegador padrão em `http://localhost:5000`, caso o WebView2 não esteja disponível).
5. No primeiro acesso como administrador (`master`), o assistente pergunta **onde guardar os PDFs do DOU** e qual organização de pastas usar (`Por ano e mês`, `Só por ano` ou `Tudo na mesma pasta`).

---

## Primeiro uso

Na primeira abertura do painel:

1. **Importação opcional:** se você utilizava uma instalação anterior, o assistente permite importar o banco `database.db` e as rotinas YAML existentes.
2. **Credenciais e integrações:** acesse **Configurações** para informar:
   - **SMTP (opcional):** servidor, porta, usuário, senha e remetente para envio dos alertas por e-mail (pode ser desligado pelo interruptor em *Configurações → Integrações*; quando desligado, as menções continuam sendo gravadas no painel);
   - **Google Sheets / GestãoClick:** credenciais da planilha ou ERP para sincronização automática da lista de CNPJs;
   - **INLABS (opcional):** usuário e senha do portal `inlabs.in.gov.br`. Quando o INLABS estiver indisponível ou em manutenção, a contingência configurada (`inlabs_fallback`: `pdf` padrão ou `api`) usa o PDF integral do dia confirmado na API do DOU.
3. **Empresas e rotina principal (`Pesquisa_cnpj.yaml`):** uma instalação limpa começa com 0 CNPJs monitorados; sincronize com o Google Sheets/GestãoClick ou adicione empresas manualmente e defina os destinatários da rotina.

---

## Uso diário

- **Bandeja do sistema e janela própria:** o painel roda em janela dedicada (WebView2); fechar a janela apenas a minimiza para a bandeja, mantendo o agendador ativo. Clique com o botão direito no ícone da bandeja para abrir o painel, consultar o status, ver logs, reiniciar ou encerrar o aplicativo.
- **Execução automática:** o agendador interno (`APScheduler`) executa as rotinas ativas nos horários configurados (com recuperação de *misfire* caso o PC estivesse desligado no horário) e sincroniza as empresas da planilha.
- **Buscas manuais e mensais:** pelo painel é possível disparar uma rotina para uma data específica (`DD/MM/AAAA`) ou rodar a consolidação de um mês inteiro.
- **Menções e relatórios:** as menções ficam salvas no histórico local antes do envio de e-mail e podem ser exportadas em Excel (`.xlsx`) ou PDF corporativo.

---

## Onde ficam dados, logs e PDFs

| Conteúdo | Caminho padrão no Windows | Observação |
|---|---|---|
| Programa instalado | `%LOCALAPPDATA%\Programs\Registrale` | Substituído a cada atualização |
| Banco SQLite (`database.db`), agendador, rotinas YAML e logs | `%LOCALAPPDATA%\Registrale` | Preservado ao atualizar ou desinstalar |
| PDFs integrais do DOU | `Documentos\Registrale\DOU` | Configurável no primeiro uso e em **Configurações → Arquivo PDF DOU** (layouts: `AAAA/MM/`, `AAAA/` ou pasta única) |

---

## Atualização e desinstalação

- **Atualização:** pelo próprio painel (**Configurações → Verificar atualizações**) ou executando o novo `Registrale-Setup-x.y.z.exe` por cima da instalação atual. Os dados em `%LOCALAPPDATA%\Registrale` são preservados.
- **Desinstalação:** via *Configurações do Windows → Aplicativos* (ou `unins000.exe` na pasta do programa). A desinstalação remove o aplicativo e os atalhos, preservando seus dados locais.

---

## Desenvolvimento local e testes

Requer Python 3.11 e [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --group dev
uv run registrale                     # inicia o painel em http://127.0.0.1:5000
uv run pytest -m "not live" -q        # suíte offline (núcleo + painel)
```

Para gerar o instalador Windows (em ambiente Windows com Inno Setup 6):

```powershell
.\windows\build.ps1
```

---

## Atualizações do Ro-DOU oficial (upstream)

O núcleo de busca (`src/`) permanece compatível com o repositório oficial do Ro-DOU (`upstream/main`) por meio do shim em `compat/airflow_shim/`. O procedimento completo de merge, a lista de patches locais e os caminhos removidos estão documentados em [`docs/tecnico/UPSTREAM.md`](docs/tecnico/UPSTREAM.md).

```bash
uv run python tools/sync_upstream.py
```

---

## Documentação

- [`docs/manual/`](docs/manual/README.md) — Manual único do analista (também acessível dentro do painel)
- [`docs/tecnico/`](docs/tecnico/01_visao_geral_e_arquitetura.md) — Arquitetura, funcionalidades, integrações, API REST, build Windows e Design System
- [`docs/upstream/`](docs/upstream/pesquisa_dou.md) — Guias de pesquisa, operadores e parâmetros do Ro-DOU aplicáveis ao app
- [`docs/projeto/PLANO.md`](docs/projeto/PLANO.md) — Plano de migração, decisões de arquitetura e histórico dos sprints
- [`CHANGELOG.md`](CHANGELOG.md) — Histórico de versões do Registrale-DOU

---

## Créditos e licença

O **Registrale-DOU** é baseado no projeto de código aberto **[Ro-DOU](https://gestaogovbr.github.io/Ro-dou/)**, desenvolvido e mantido pela Secretaria de Gestão e Inovação do **Ministério da Gestão e da Inovação em Serviços Públicos (MGI)**, licenciado sob a **Apache License 2.0** ([`LICENSE`](LICENSE)).
