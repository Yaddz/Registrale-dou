# 02. Decisões, validação e pendências

Registro do que foi decidido na migração do Registrale-DOU para aplicativo Windows (novembro/2026), de como o comportamento é validado e do que ficou em aberto. O histórico por versão está no [`CHANGELOG.md`](../../CHANGELOG.md); o funcionamento para o analista, no [manual](../manual/README.md).

---

## 1. Decisões de arquitetura

| Tema | Decisão | Motivo |
|---|---|---|
| Execução | Executor local (`LocalExecutor`) dentro do painel, sem Airflow nem Docker | Um analista só; Airflow + Docker usavam ~2 GB de RAM e exigiam WSL/Docker Desktop |
| Núcleo de busca | `src/` do upstream intacto, rodando sobre `compat/airflow_shim/` | Continuar recebendo atualizações do Ro-DOU oficial com conflitos mínimos ([`UPSTREAM.md`](UPSTREAM.md)) |
| Agendamento | APScheduler num único processo | Substitui o scheduler do Airflow e evita o agendador do Sheets duplicado por vários workers |
| Servidor web | Waitress (1 processo, várias threads) | gunicorn não roda no Windows |
| Dados do painel | SQLite (`database.db`) | Já era o banco do painel; backup é copiar um arquivo |
| Fonte da busca diária | PDF integral do dia (`pesquisa.in.gov.br`) com confirmação na API do DOU; API do DOU como reserva | O INLABS ficou fora do ar por mais de um mês em 2026 e o PostgreSQL portátil não vai no instalador |
| INLABS local | PostgreSQL portátil opcional, gerido pelo app. O build oficial usa `-SkipPostgresDownload` | Falta um SHA-256 confiável do pacote; a contingência cobre a busca sem ele |
| Empacotamento | Python 3.11 *embeddable* + dependências + Inno Setup → `Registrale-Setup-x.y.z.exe` | Menos falso positivo de antivírus que PyInstaller; fácil de inspecionar |
| Execução no Windows | Launcher na bandeja (pystray), início com o Windows, janela própria (pywebview/WebView2) e navegador como reserva. Electron descartado | O analista não usa terminal; WebView2 já vem no Windows e não pesa ~150 MB como o Electron |
| Diretórios | Programa em `%LOCALAPPDATA%\Programs\Registrale`; dados em `%LOCALAPPDATA%\Registrale`; PDFs em `Documentos\Registrale\DOU` (configurável) | Atualizar ou reinstalar não apaga dados |
| Atualização | Verificação nas Releases do GitHub + instalador validado por SHA-256 | Simples e auditável |
| Lista de clientes | `dag_confs/Pesquisa_cnpj.yaml` é gerado pelo painel, fica fora do git e é removido do pacote pelo `build.ps1` | Não distribuir CNPJs de clientes no instalador |
| Releases e numeração | Em 26/11/2026 as releases e tags `v1.0.0` a `v1.3.2` foram apagadas do GitHub e a numeração recomeçou na `v1.0.0` (commit `7e2c4f0`, instalador gerado pelo CI). O histórico do git continua com a lista antiga de CNPJs (sem reescrita, por decisão do usuário). Uma instalação 1.3.2 precisa instalar a 1.0.0 por cima uma vez, porque o atualizador só oferece números maiores | O instalador da antiga `v1.0.0` continha a lista de CNPJs de clientes |
| Padrões da rotina principal | Seções 1, 2, 3 e Extra; `department: []`; `is_exact_search: false`; `field: TUDO`; 8h em dias úteis | Mesma cobertura da baseline; filtro de órgão escondeu menções reais da Seção 3 (hotfix 1.3.1) |
| Filtro de órgão | Siglas convertidas para o nome oficial do DOU ao gravar o YAML (`services/organ_aliases.py`); o SQLite guarda o que o usuário digitou | O núcleo compara com o nome em `hierarchyList` |
| SMTP | Desligado por padrão; sem servidor, nada é enviado e um único evento é registrado | Evita "conexão recusada" a cada busca em instalações sem e-mail |
| Avisos da Visão geral | Só problema real (`services/health_alerts.py`); integração desligada nunca gera aviso | O antigo "Integrações pendentes" ficava sempre visível |
| Assistente de primeiro uso | 9 passos; "Pular" desliga explicitamente a integração do passo, para não sobrar pendência; segredos nunca voltam ao navegador pelos endpoints do assistente | Instalação limpa pronta ou conscientemente desligada |
| Manual | Fonte única em `docs/manual/` (Markdown), mostrado na aba Manual por `GET /api/manual?format=sections` e copiado pelo `build.ps1` | Antes havia um manual em HTML fixo na tela, que ficou desatualizado |
| Plataforma de uso | Só desktop, de 800 a 1920 px de largura | O app não é usado no celular |

---

## 2. Baseline de paridade

Gravada a partir do modo Docker antes da migração e usada para validar qualquer executor novo:

- **Novembro/2026** (03 a 23/11, 14 dias úteis; 20/11 é feriado), rotina principal → **26 menções de 16 empresas** (25 pares empresa/dia: 22 com CNPJ completo e 3 só pela raiz). Fixture: `tests/fixtures/baseline/nov2026_mentions.json`.
- **Outubro/2026**, restrito às mesmas 16 empresas → 18 menções de 9 empresas. Fixture: `tests/fixtures/baseline/oct2026_mentions_16empresas.json`.
- Dias únicos: 19/11 → 0 menções; 03/11 e 23/11 incluem a SURGITEC só pela raiz (`24.684.423`).

**Rotina de teste:** em vez da lista real de clientes, use as 16 empresas com menção em novembro, geradas em tempo de execução por `tests/local/rotina_teste.py` a partir da fixture (CNPJs já públicos no DOU). Não versione listas de clientes.

```bash
uv run pytest tests/local/test_parity_nov2026.py -m live -v   # ~20 min, rede real
```

---

## 3. Resultado da homologação

| Item | Resultado | Evidência resumida |
|---|---|---|
| Paridade local × Docker (novembro, outubro e 5 dias únicos) | Aprovado | Conjunto `(cnpj, data, link)` idêntico nos modos API e PDF + API |
| Contingência sem INLABS (modos `pdf` e `api`) | Aprovado | Novembro: 26 menções / 16 empresas nos dois modos |
| Resiliência (DOU lento, INLABS em manutenção, PDF fora, captcha, SMTP errado, PC desligado, buscas simultâneas) | Aprovado | Testes offline dedicados; captcha não é contornado (cai para a API) |
| Instalação, atualização 1.2.0 → 1.3.0 e desinstalação em VM Windows 10 limpa | Aprovado | Dados e PDFs preservados; desinstalação silenciosa mantém `database.db` |
| Upstream (`tools/sync_upstream.py` + testes) | Aprovado | Merge sem conflitos e suíte verde |
| Desempenho | Aprovado | Windows: abertura ~11 s, RAM ~130 MB; busca diária pelo PDF ~2,5 min a frio |
| Execução real fora do pytest (Windows) | Aprovado | `launcher.pyw` + busca de 23/11 pelo PDF: 4 menções |
| INLABS real (3 dias baixados) | **Pendência aceita** | Portal em "Manutenção Programada"; coberto só por testes offline |
| 5 dias úteis de agendamento e de PDFs no PC do analista | **Pendência aceita** | Acompanhar no uso real; um dia sem e-mail ou sem PDF reabre o item |
| Nova tentativa automática de ponta a ponta (Etapa 6, por simulação) — 26/11/2026 | Aprovado | `tests/local/test_retry_ponta_a_ponta.py`, offline e com relógio simulado, usando o agendador real (`RegistraleScheduler`, APScheduler com jobstore SQLite, e o mesmo `run_job` que dispara os jobs, inclusive a regra de *misfire*), o `LocalExecutor` real e `watch_dag_and_update_mentions` com SMTP simulado. Cenários: **(1)** busca das 14h com a Edição Extra ainda fora do PDF → `partial`, histórico "Busca com Pendências" + "Busca Incompleta", job `retry::` às 15h05 (tentativa 1/4); às 15h a Extra saiu → `success`, nenhum retry novo e o 2º e-mail traz só a menção nova; **(2)** fonte sempre incompleta → exatamente 4 novas tentativas (11h a 14h) e a 5ª não é agendada, com "Sem novas tentativas hoje" no histórico; **(3)** `partial` às 21h10 → nenhuma nova tentativa (22h10 ≥ 22h) e "Busca Concluída com Pendências"; **(4)** PC desligado até o dia seguinte → o APScheduler descarta o job vencido (`EVENT_JOB_MISSED`, folga de 600 s) e, mesmo disparado, a data do dia o barra; com 5 min de atraso roda normalmente; **(5)** SMTP falhando na nova tentativa → menções gravadas, "Busca Concluída" antes de "Erro Envio E-mail". Nenhum defeito de comportamento encontrado; só a diferença de nomes no histórico (com e-mail enviado o evento é "Busca com Pendências", sem envio é "Busca Concluída com Pendências"). **Não cobre:** o horário real de publicação do DOU (quando a Extra/Seção 3 aparece no PDF e na API), o agendador rodando horas seguidas no PC do analista (suspensão, hibernação, relógio do Windows) e o servidor SMTP real |
| Checklist de interface (seção 7 de `06_design_system.md`) com login ligado — 26/11/2026 | Aprovado após correções | Cópia dos dados (porta 5056, e-mail/sincronizações/rotina principal desligados), usuários de teste `master` e `user`, 800/1024/1280/1920 px, claro e escuro: 15 telas por combinação no master (7 abas + 9 subabas de Configurações) e 6 no `user` (Configurações some do menu), além da tela de login nos dois temas. Verificação automática por tela: sem rolagem horizontal da página, sem elemento fora da largura, nenhum ícone Lucide sem renderizar, nenhum texto < 11 px, nenhum peso > 600. Corrigido no caminho: setas das pílulas de Configurações nunca apareciam ao abrir a aba pelo menu (o cálculo rodava com a seção oculta; agora um `ResizeObserver` recalcula) e o degradê delas era invisível (classe Tailwind não gerada; trocado por `linear-gradient` com `var(--bg)`); `<b>`, `<strong>` e `<th>` saíam com peso 700 (regra base `font-weight: 600`); lixeira sem ícone na linha de usuário recém-criado. Achado não corrigido: com o perfil `user` (consulta) o servidor ainda aceita excluir menções (`DELETE /api/mentions`) e disparar sincronização (`POST /api/sync`), e os botões aparecem — ver seção 4 |

Aprovação para remover Docker/Airflow dada pelo responsável do projeto em 24/11/2026.

---

## 4. Pendências conhecidas

- **Nova tentativa automática no uso real:** a cadeia completa foi validada por simulação de ponta a ponta em 26/11/2026 (seção 3). Falta observar no PC do analista um dia real com seção publicada tarde (horário real do DOU e agendador rodando horas seguidas).
- **Perfil `user` (consulta) não é só leitura no servidor** (achado no checklist de 26/11/2026): `DELETE /api/mentions` e `POST /api/sync` só exigem login, e a interface mostra a lixeira das menções e o "Sincronizar bases" para esse perfil. Decidir se `user` deve ser somente leitura e, se sim, exigir `master` nessas rotas e esconder os botões.

## 5. Backlog

- **PostgreSQL portátil no instalador:** embutir os binários com SHA-256 fixo ou aposentar o INLABS local em favor de PDF + API.
- **Busca por razão social** (citações sem CNPJ, como despachos do CADE), marcada "por nome" e sujeita a revisão por causa dos falsos positivos.
- **Segredos na tela de Configurações:** `GET /api/settings` ainda envia senhas e a chave do Google ao navegador do master; campo enviado vazio não deve apagar token salvo.

---

## 6. Como validar mudanças sem tocar no app instalado

**Interface com cópia dos dados.** Copie `%LOCALAPPDATA%\Registrale` para uma pasta temporária e suba outra instância numa porta livre:

```powershell
$env:REGISTRALE_DATA_DIR = "$env:TEMP\registrale-teste"
uv run registrale --port 5055
```

`REGISTRALE_DB_PATH` e `REGISTRALE_ROUTINES_DIR` também podem ser apontados para a cópia. Nunca teste contra o banco real do analista.

**Atualizar o app instalado com uma correção** (sem gerar instalador): backup de `database.db`, cópia dos arquivos alterados de `rodou_dashboard/` para `%LOCALAPPDATA%\Programs\Registrale\app\`, remoção dos `__pycache__` e **Reiniciar** pelo menu da bandeja.

**VM Windows de homologação** (container `dockurr/windows` no Podman, `windows-registrale`):

- Subir com `podman start windows-registrale`; acesso por noVNC em `http://localhost:8006` ou RDP na porta 3389.
- O repositório aparece no Windows como `\\host.lan\Data`. A pasta não aceita gravar arquivos novos a partir do guest: devolva resultados por HTTP para um receptor no host.
- Para digitar pelo noVNC, preencha `#noVNC_clipboard_text` e acione `#noVNC_clipboard_send_button` pelo JavaScript da página.
- Antes de instalar, faça backup de `%LOCALAPPDATA%\Registrale` dentro da VM; para instalação limpa, mova (não apague) as pastas de dados e do programa.
- Tempos de referência: build ~3 min, pytest ~1,5 min, novembro pela contingência PDF ~15–20 min.
