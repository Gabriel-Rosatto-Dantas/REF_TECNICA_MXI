# REF_TECNICA_PLANNING

Automacao em Python para consultar **Part Numbers (PNs)** no sistema **Maintenix / MXI**, identificar o fabricante do item, localizar anexos do tipo **FORM PSS**, baixar os PDFs e atualizar o Google Sheets **VERIFICAR REF TECNICA** com o resultado de cada consulta.

O projeto foi desenvolvido para rodar localmente no Windows, via **VS Code / PowerShell**, utilizando Selenium apenas para realizar o login no MXI. Depois do login, as consultas e downloads sao realizados por HTTP usando a mesma sessao autenticada.

> **Importante:** o projeto nao faz upload automatico dos PDFs para o Google Drive. Os arquivos sao baixados para a pasta local `downloads/` e o upload para o Drive deve ser feito manualmente.

---

## 1. Funcionalidades

O script executa o seguinte fluxo:

1. Le as configuracoes do arquivo `config.ini`.
2. Autentica no Google Sheets usando uma **Service Account** via `credentials.json`.
3. Abre a planilha configurada e identifica as abas que possuem PNs.
4. Testa a conectividade com o servidor MXI.
5. Abre o Google Chrome com Selenium.
6. Realiza o login no Maintenix / MXI.
7. Transfere os cookies da sessao do Selenium para `requests.Session`.
8. Para cada PN pendente na planilha:
   - pesquisa o PN no MXI;
   - identifica o `Manufacturer`;
   - identifica se o item e fabricado internamente pelo MRO;
   - abre o `Part Details`;
   - consulta a aba `Details`;
   - procura anexos cujo nome contenha `FORM PSS`;
   - baixa o PDF, quando encontrado;
   - atualiza `STATUS` e `DETALHE_STATUS` no Google Sheets.
9. Exibe um resumo final da execucao no terminal.

---

## 2. Regra de negocio do MRO

O campo **Manufacturer** retornado na pesquisa do MXI e utilizado para identificar itens fabricados internamente.

Todo fabricante cujo codigo comeca com:

```text
QSC
```

e considerado **Item Fabricado MRO**.

Exemplos:

```text
QSCMY22
QSCMY25
QSC123
```

### Importante

O fato de um item ser MRO **nao impede a busca do FORM PSS**.

O script sempre procura o documento tecnico primeiro.

A logica e:

```text
Pesquisar PN
    |
    +--> Identificar Manufacturer
    |
    +--> Procurar FORM PSS
             |
             +--> Encontrado
             |       |
             |       +--> Baixar PDF
             |
             +--> Nao encontrado
                     |
                     +--> Manufacturer comeca com QSC?
                              |
                              +--> Sim: ITEM FABRICADO MRO - SEM FORM PSS
                              |
                              +--> Nao: SEM FORM PSS
```

---

## 3. Status utilizados na planilha

O script atualiza as colunas:

| Coluna | Nome | Utilizacao |
|---|---|---|
| A | `Part Number` | PN consultado |
| B | `STATUS` | Resultado principal da consulta |
| C | `DETALHE_STATUS` | Informacoes complementares |
| D | `LINK_PDF` | Nao e alterada automaticamente |

### `PDF BAIXADO`

O FORM PSS foi localizado e o arquivo PDF foi salvo localmente.

Exemplo:

```text
STATUS:
PDF BAIXADO

DETALHE_STATUS:
FORM PSS - D2557294427000-T.pdf | Manufacturer: ABC123
```

Se o item tambem for fabricado pelo MRO:

```text
FORM PSS - XXXXX.pdf | Manufacturer: QSCMY22 | Item Fabricado MRO
```

### `ITEM FABRICADO MRO - SEM FORM PSS`

O item possui `Manufacturer` iniciado por `QSC`, mas nenhum FORM PSS foi encontrado.

Exemplo:

```text
STATUS:
ITEM FABRICADO MRO - SEM FORM PSS

DETALHE_STATUS:
Manufacturer: QSCMY22
```

### `SEM FORM PSS`

O PN existe no MXI, mas nenhum FORM PSS foi localizado e o fabricante nao e identificado como MRO.

### `PN NAO ENCONTRADO`

O PN informado na planilha nao foi encontrado na pesquisa do MXI.

### `ERRO`

O PN nao pode ser processado devido a algum erro inesperado, por exemplo:

- falha de comunicacao com o MXI;
- sessao expirada;
- erro ao abrir o Part Details;
- FORM PSS encontrado, mas falha durante o download;
- erro ao atualizar o Google Sheets.

---

## 4. Estrutura recomendada do projeto

```text
REF_TECNICA_PLANNING/
|
|-- ref_tecnica_mxi.py
|-- config.ini
|-- credentials.json
|-- requirements.txt
|-- README.md
|-- mxi_automacao.log
|
`-- downloads/
    |-- FORM PSS - PN1.pdf
    |-- FORM PSS - PN2.pdf
    |-- FORM PSS - PN3.pdf
    `-- ...
```

Todos os PDFs sao salvos diretamente dentro de `downloads/`.

O script **nao cria uma subpasta para cada PN**.

---

## 5. Pre-requisitos

### Sistema operacional

O projeto foi preparado para uso no Windows.

### Python

Recomendado:

```text
Python 3.11 ou superior
```

O projeto ja foi executado com Python 3.13.

Para conferir a versao instalada:

```powershell
python --version
```

### Google Chrome

O Google Chrome deve estar instalado na maquina.

O Selenium procura automaticamente o executavel em locais comuns do Windows, incluindo:

```text
C:\Program Files\Google\Chrome\Application\chrome.exe
```

Com as versoes recentes do Selenium, o Selenium Manager normalmente gerencia automaticamente o ChromeDriver compativel.

### Rede corporativa / VPN

O computador precisa conseguir acessar o servidor interno do MXI configurado em `config.ini`.

Se o ambiente corporativo exigir VPN, ela deve estar conectada antes da execucao do script.

---

## 6. Criar o ambiente virtual

Abra o terminal do VS Code dentro da pasta do projeto.

Crie o ambiente virtual:

```powershell
python -m venv venv
```

Ative o ambiente:

```powershell
.\venv\Scripts\Activate.ps1
```

O terminal deve passar a mostrar algo semelhante a:

```text
(venv) PS C:\...\REF_TECNICA_PLANNING>
```

---

## 7. Instalar dependencias

Com o ambiente virtual ativo:

```powershell
pip install -r requirements.txt
```

Para atualizar o `pip` antes da instalacao:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

As bibliotecas externas utilizadas pelo projeto sao:

- `selenium`: login automatizado no MXI;
- `requests`: chamadas HTTP autenticadas ao MXI;
- `urllib3`: suporte HTTP e configuracao SSL;
- `beautifulsoup4`: leitura e interpretacao do HTML retornado pelo MXI;
- `gspread`: leitura e atualizacao do Google Sheets;
- `google-auth`: autenticacao com a Service Account.

Os demais imports do script fazem parte da biblioteca padrao do Python e nao precisam constar no `requirements.txt`.

---

## 8. Configurar o Google Sheets

O projeto utiliza uma Service Account para acessar a planilha.

O arquivo deve estar salvo como:

```text
credentials.json
```

na mesma pasta do script.

Exemplo:

```text
REF_TECNICA_PLANNING/
|-- ref_tecnica_mxi.py
|-- config.ini
`-- credentials.json
```

A planilha precisa estar compartilhada com o e-mail da Service Account presente no campo:

```json
"client_email": "...@....iam.gserviceaccount.com"
```

A conta deve possuir permissao suficiente para editar as colunas de status.

> Nunca publique o arquivo `credentials.json` em GitHub, GitLab, Teams, e-mail ou repositorio publico.

---

## 9. Configuracao do `config.ini`

Exemplo de configuracao:

```ini
[GOOGLE]
sheets_credentials_file = credentials.json
sheet = https://docs.google.com/spreadsheets/d/SEU_SHEET_ID/edit


[MXI]
login_url = https://SEU_SERVIDOR/maintenix/common/security/login.jsp
username = SEU_USUARIO
password = SUA_SENHA

success_element_id = idMxTitle
success_text = To Do List


[MXI_API]
part_search_url = https://SEU_SERVIDOR/maintenix/web/part/PartSearchByType.jsp

search_type = OEM
max_results = 100
verify_ssl = false


[SELENIUM]
headless = false
page_load_strategy = none

page_timeout = 30
login_timeout = 60
login_click_timeout = 10

implicit_wait = 1
maximize_window = true
ignore_certificate_errors = true
post_login_wait = 2


[PROCESSING]
process_only_blank_status = true

retry_statuses = ERRO,ERRO DRIVE,SEM PDF,SEM ANEXO,ITEM FABRICADO MRO

max_items = 0
delay_between_items = 0.3

only_pdf = true
attachment_name_contains = FORM PSS


[PATHS]
download_dir = downloads
log_file = mxi_automacao.log
```

### Seguranca do `config.ini`

Como o arquivo pode conter usuario e senha corporativos, ele deve ser tratado como arquivo sensivel.

Nao envie o `config.ini` para repositorios publicos.

---

## 10. Principais configuracoes

### `headless`

```ini
headless = false
```

Chrome visivel durante o login.

Para executar sem mostrar a janela do navegador:

```ini
headless = true
```

Se houver qualquer problema de login, recomenda-se voltar para `false` para facilitar a verificacao.

### `max_items`

Controla quantos itens podem ser processados na execucao.

Todos os itens:

```ini
max_items = 0
```

Teste com 10 itens:

```ini
max_items = 10
```

Essa configuracao e util antes de liberar uma execucao completa.

### `delay_between_items`

Intervalo entre cada PN:

```ini
delay_between_items = 0.3
```

O valor e informado em segundos.

### `attachment_name_contains`

Filtro utilizado para identificar o documento desejado:

```ini
attachment_name_contains = FORM PSS
```

Assim, outros attachments existentes no Part Details sao ignorados.

### `process_only_blank_status`

```ini
process_only_blank_status = true
```

Com essa opcao ativa, PNs que ja possuem um status final nao sao processados novamente.

---

## 11. Reprocessamento de erros

A configuracao:

```ini
retry_statuses = ERRO,ERRO DRIVE,SEM PDF,SEM ANEXO,ITEM FABRICADO MRO
```

faz com que esses status sejam processados novamente mesmo quando a coluna `STATUS` ja esta preenchida.

Isso tambem permite corrigir resultados gerados por versoes anteriores do script.

Por exemplo, uma versao antiga utilizava:

```text
ITEM FABRICADO MRO
```

sem procurar o FORM PSS.

Esse status foi incluido em `retry_statuses` para garantir que o PN seja consultado novamente pela logica atual.

Depois que todos os registros antigos forem corrigidos, essa lista pode ser simplificada para algo como:

```ini
retry_statuses = ERRO
```

---

## 12. Executar o projeto

Com o `venv` ativo:

```powershell
python -u ref_tecnica_mxi.py
```

Exemplo de saida:

```text
13:52:01 | INFO    | Iniciando VERIFICAR REF TECNICA
13:52:03 | OK      | Google Sheets conectado | 4 abas | 491 PNs
13:52:06 | OK      | Login MXI realizado
13:52:06 | INFO    | 478 itens pendentes para processamento

13:52:07 | INFO    | [1/478] Airbus | PN 00495-109-000
13:52:08 | OK      | 00495-109-000 | PDF BAIXADO | FORM PSS - 00495-109-000.pdf

13:52:09 | INFO    | [2/478] Airbus | PN 867874-403A-T
13:52:10 | MRO     | 867874-403A-T | SEM FORM PSS | Manufacturer: QSCMY22

13:52:11 | INFO    | [3/478] Airbus | PN XXXXX
13:52:12 | SEM PSS | XXXXX | Manufacturer: ABC123
```

Ao final:

```text
------------------------------------------------------------
RESUMO
------------------------------------------------------------
Processados............... 478
PDFs baixados............ 82
MRO sem FORM PSS......... 27
Sem FORM PSS............. 355
PN nao encontrado........ 9
Erros.................... 5
------------------------------------------------------------
PDFs: C:\...\REF_TECNICA_PLANNING\downloads
Log : C:\...\REF_TECNICA_PLANNING\mxi_automacao.log
```

---

## 13. Downloads

Todos os PDFs encontrados sao gravados diretamente em:

```text
downloads/
```

Exemplo:

```text
downloads/
|-- FORM PSS - D2557294427000-T.pdf
|-- FORM PSS - 00495-109-000.pdf
|-- FORM PSS - XXXXX.pdf
`-- FORM PSS - YYYYY.pdf
```

Depois da execucao, os arquivos podem ser enviados manualmente para a pasta corporativa do Google Drive.

A coluna `LINK_PDF` nao e modificada pelo script para permitir que o link seja preenchido apos o upload manual.

---

## 14. Log da aplicacao

A execucao tambem e registrada em:

```text
mxi_automacao.log
```

O log e propositalmente enxuto e mostra apenas informacoes relevantes para acompanhamento operacional.

Exemplos:

```text
14:00:01 | INFO    | Iniciando VERIFICAR REF TECNICA
14:00:03 | OK      | Google Sheets conectado | 4 abas | 491 PNs
14:00:06 | OK      | Login MXI realizado
14:00:07 | INFO    | [1/478] Airbus | PN 00495-109-000
14:00:08 | OK      | 00495-109-000 | PDF BAIXADO | FORM PSS - 00495-109-000.pdf
```

---

## 15. Interromper a execucao

Para interromper manualmente:

```text
CTRL + C
```

O script fecha a sessao HTTP e o Chrome antes de terminar sempre que possivel.

Como cada PN concluido e atualizado imediatamente no Google Sheets, uma nova execucao pode continuar pelos itens ainda pendentes.

---

## 16. Como continuar uma execucao interrompida

Nao e necessario determinar manualmente em qual linha o script parou.

Com:

```ini
process_only_blank_status = true
```

o script ignora os itens com status final e monta uma nova fila somente com os itens pendentes ou com status configurados em `retry_statuses`.

Basta executar novamente:

```powershell
python -u ref_tecnica_mxi.py
```

---

## 17. Problemas comuns

### MXI nao abre

Verifique:

- VPN corporativa;
- conexao com a rede LATAM;
- acesso ao hostname configurado no `login_url`;
- firewall corporativo.

O erro pode aparecer como:

```text
MXI indisponivel / problema de rede ou VPN
```

### Login fica parado

Confirme:

- usuario;
- senha;
- acesso normal ao MXI pelo navegador;
- `headless = false` para acompanhar visualmente o login.

O script considera o login concluido quando encontra:

```html
<span id="idMxTitle">To Do List</span>
```

### `PN NAO ENCONTRADO`

Confirme o PN diretamente no MXI usando **Search by OEM part number**.

Tambem verifique caracteres adicionais, espacos e hifens no Google Sheets.

### `SEM FORM PSS`

O PN foi encontrado, mas a aba **Details > Attachments** nao possui um anexo cujo nome corresponda ao filtro:

```ini
attachment_name_contains = FORM PSS
```

### `ITEM FABRICADO MRO - SEM FORM PSS`

O item nao possui FORM PSS, mas o `Manufacturer` comeca com `QSC`.

Esse resultado indica fabricacao interna do MRO sem documento FORM PSS anexado no MXI.

### `ERRO` durante o download

O MXI encontrou o FORM PSS, mas houve falha ao recuperar o arquivo.

Execute novamente. Como `ERRO` esta em `retry_statuses`, o PN sera automaticamente reprocessado.

### Google Sheets nao abre

Confirme:

- existencia de `credentials.json`;
- compartilhamento da planilha com o `client_email` da Service Account;
- permissao de edicao na planilha;
- ID correto da planilha no `config.ini`.

---

## 18. Atualizar dependencias

Para verificar pacotes instalados:

```powershell
pip list
```

Para atualizar as dependencias respeitando as faixas configuradas:

```powershell
pip install -U -r requirements.txt
```

---

## 19. Gerar uma lista exata do ambiente

O `requirements.txt` deste projeto utiliza faixas de versao para evitar dependencias desnecessariamente presas a uma unica versao.

Caso seja necessario criar um snapshot exato do ambiente atual:

```powershell
pip freeze > requirements-lock.txt
```

Esse arquivo pode ser utilizado para reproduzir exatamente o mesmo ambiente em outra maquina:

```powershell
pip install -r requirements-lock.txt
```

---

## 20. Seguranca

Os seguintes arquivos contem ou podem conter informacoes sensiveis:

```text
credentials.json
config.ini
```

Eles nao devem ser versionados em repositorios publicos.

E recomendado criar um `.gitignore` contendo pelo menos:

```gitignore
# Ambiente Python
venv/
.venv/
__pycache__/
*.pyc

# Credenciais / configuracoes locais
credentials.json
config.ini

# Downloads e logs
downloads/
*.log

# VS Code
.vscode/
```

Nunca grave usuario, senha ou chave privada diretamente no codigo Python.

---

## 21. Dependencias Python

O arquivo `requirements.txt` utilizado pelo projeto contem:

```text
selenium>=4.25,<5
requests>=2.32,<3
urllib3>=2.2,<3
beautifulsoup4>=4.12,<5
gspread>=6.1,<7
google-auth>=2.35,<3
```

---

## 22. Fluxo resumido

```text
Google Sheets
     |
     v
Lista de PNs pendentes
     |
     v
Login MXI (Selenium)
     |
     v
Sessao HTTP autenticada
     |
     v
Pesquisa OEM PN
     |
     +--> PN inexistente ----------------> PN NAO ENCONTRADO
     |
     v
Identificar Manufacturer
     |
     v
Part Details > Details > Attachments
     |
     +--> FORM PSS encontrado
     |        |
     |        v
     |     Download PDF
     |        |
     |        v
     |     PDF BAIXADO
     |
     +--> FORM PSS nao encontrado
              |
              +--> Manufacturer QSC --> ITEM FABRICADO MRO - SEM FORM PSS
              |
              `--> Outro fabricante --> SEM FORM PSS
```

---

## 23. Operacao recomendada

Antes de uma execucao grande, e recomendavel realizar inicialmente:

```ini
max_items = 5
```

Confirme que:

- o login MXI ocorreu normalmente;
- os status foram preenchidos corretamente;
- os PDFs apareceram em `downloads/`;
- itens `QSC` foram identificados corretamente;
- itens sem FORM PSS foram classificados corretamente.

Depois altere para:

```ini
max_items = 0
```

para processar todos os itens pendentes.

---

## 24. Resultado final esperado

Ao final de uma execucao bem-sucedida:

- cada PN consultado possui um status na planilha;
- FORM PSS existentes estao salvos na pasta `downloads/`;
- itens MRO sem FORM PSS sao identificados separadamente;
- itens sem documento sao sinalizados;
- PNs inexistentes sao identificados;
- erros permanecem disponiveis para reprocessamento;
- a coluna `LINK_PDF` permanece disponivel para preenchimento manual apos o upload ao Google Drive.
