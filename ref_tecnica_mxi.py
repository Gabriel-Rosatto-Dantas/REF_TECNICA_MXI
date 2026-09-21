# ============================================================
# VERIFICAR REF TECNICA - MXI
#
# VERSAO DE PRODUCAO
#
# FLUXO:
# ------------------------------------------------------------
# 1. Google Sheets
# 2. Login MXI via Selenium
# 3. Cookies Selenium -> requests.Session
# 4. Pesquisa PN
# 5. Identifica Manufacturer
# 6. SEMPRE procura FORM PSS
# 7. Download dos PDFs em /downloads
# 8. Atualiza STATUS e DETALHE_STATUS
#
#
# REGRAS:
# ------------------------------------------------------------
#
# FORM PSS encontrado:
#
#   STATUS = PDF BAIXADO
#
#
# FORM PSS nao encontrado + Manufacturer QSC:
#
#   STATUS = ITEM FABRICADO MRO - SEM FORM PSS
#
#
# FORM PSS nao encontrado + fabricante normal:
#
#   STATUS = SEM FORM PSS
#
#
# LINK_PDF nao e alterado.
#
# ============================================================


# ============================================================
# IMPORTS
# ============================================================

import os
import sys
import re
import time
import socket
import shutil
import logging
import configparser

from pathlib import Path

from urllib.parse import (
    urlparse,
    urljoin,
    unquote
)


import requests
import urllib3

from bs4 import BeautifulSoup


import gspread

from google.oauth2 import service_account


from selenium import webdriver

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from selenium.webdriver.common.by import By

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException
)


# ============================================================
# BASE
# ============================================================

BASE_DIR = Path(
    __file__
).resolve().parent


CONFIG_FILE = (
    BASE_DIR /
    "config.ini"
)


# ============================================================
# CONFIG
# ============================================================

def carregar_config():

    if not CONFIG_FILE.exists():

        raise FileNotFoundError(
            f"config.ini nao encontrado: {CONFIG_FILE}"
        )


    config = configparser.ConfigParser(
        interpolation=None
    )


    config.read(
        CONFIG_FILE,
        encoding="utf-8"
    )


    secoes = [
        "GOOGLE",
        "MXI",
        "MXI_API",
        "SELENIUM",
        "PROCESSING",
        "PATHS"
    ]


    for secao in secoes:

        if secao not in config:

            raise RuntimeError(
                f"Secao [{secao}] nao encontrada no config.ini"
            )


    return config


CONFIG = carregar_config()


# ============================================================
# UTILITARIOS
# ============================================================

def caminho_projeto(valor):

    path = Path(
        valor.strip()
    )


    if path.is_absolute():

        return path


    return (
        BASE_DIR /
        path
    )


def extrair_google_id(valor):

    valor = valor.strip()


    match = re.search(
        r"/d/([A-Za-z0-9_-]+)",
        valor
    )


    if match:

        return match.group(
            1
        )


    return valor


def normalizar_texto(valor):

    return (
        str(
            valor or ""
        )
        .strip()
        .upper()
    )


def normalizar_pn(valor):

    return re.sub(
        r"\s+",
        "",
        str(
            valor or ""
        )
    ).upper()


def nome_seguro(nome):

    nome = str(
        nome or ""
    ).strip()


    nome = re.sub(
        r'[<>:"/\\|?*]+',
        "_",
        nome
    )


    nome = re.sub(
        r"\s+",
        " ",
        nome
    )


    nome = nome.strip(
        " ."
    )


    if not nome:

        nome = "arquivo"


    return nome


# ============================================================
# CONFIG GOOGLE
# ============================================================

SHEETS_CREDENTIALS_FILE = caminho_projeto(
    CONFIG["GOOGLE"].get(
        "sheets_credentials_file",
        "credentials.json"
    )
)


SHEET_ID = extrair_google_id(
    CONFIG["GOOGLE"][
        "sheet"
    ]
)


SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]


# ============================================================
# CONFIG MXI
# ============================================================

MXI_LOGIN_URL = CONFIG["MXI"][
    "login_url"
].strip()


MXI_USER = CONFIG["MXI"][
    "username"
].strip()


MXI_PASSWORD = CONFIG["MXI"][
    "password"
]


MXI_SUCCESS_ELEMENT_ID = CONFIG["MXI"].get(
    "success_element_id",
    "idMxTitle"
).strip()


MXI_SUCCESS_TEXT = CONFIG["MXI"].get(
    "success_text",
    "To Do List"
).strip()


# ============================================================
# MXI API
# ============================================================

MXI_PART_SEARCH_URL = CONFIG[
    "MXI_API"
][
    "part_search_url"
].strip()


MXI_SEARCH_TYPE = CONFIG["MXI_API"].get(
    "search_type",
    "OEM"
).strip()


MXI_MAX_RESULTS = CONFIG["MXI_API"].getint(
    "max_results",
    fallback=100
)


MXI_VERIFY_SSL = CONFIG["MXI_API"].getboolean(
    "verify_ssl",
    fallback=False
)


if not MXI_VERIFY_SSL:

    urllib3.disable_warnings(
        urllib3.exceptions.InsecureRequestWarning
    )


# ============================================================
# SELENIUM
# ============================================================

HEADLESS = CONFIG["SELENIUM"].getboolean(
    "headless",
    fallback=False
)


PAGE_LOAD_STRATEGY = CONFIG["SELENIUM"].get(
    "page_load_strategy",
    "none"
).strip().lower()


PAGE_TIMEOUT = CONFIG["SELENIUM"].getint(
    "page_timeout",
    fallback=30
)


LOGIN_TIMEOUT = CONFIG["SELENIUM"].getint(
    "login_timeout",
    fallback=60
)


LOGIN_CLICK_TIMEOUT = CONFIG["SELENIUM"].getint(
    "login_click_timeout",
    fallback=10
)


IMPLICIT_WAIT = CONFIG["SELENIUM"].getfloat(
    "implicit_wait",
    fallback=1
)


MAXIMIZE_WINDOW = CONFIG["SELENIUM"].getboolean(
    "maximize_window",
    fallback=True
)


IGNORE_CERTIFICATE_ERRORS = CONFIG[
    "SELENIUM"
].getboolean(
    "ignore_certificate_errors",
    fallback=True
)


POST_LOGIN_WAIT = CONFIG["SELENIUM"].getfloat(
    "post_login_wait",
    fallback=2
)


# ============================================================
# PROCESSAMENTO
# ============================================================

PROCESS_ONLY_BLANK_STATUS = CONFIG[
    "PROCESSING"
].getboolean(
    "process_only_blank_status",
    fallback=True
)


RETRY_STATUSES = {
    item.strip().upper()
    for item in CONFIG["PROCESSING"].get(
        "retry_statuses",
        (
            "ERRO,"
            "ERRO DRIVE,"
            "SEM PDF,"
            "SEM ANEXO,"
            "ITEM FABRICADO MRO"
        )
    ).split(",")
    if item.strip()
}


MAX_ITEMS = CONFIG["PROCESSING"].getint(
    "max_items",
    fallback=0
)


DELAY_BETWEEN_ITEMS = CONFIG[
    "PROCESSING"
].getfloat(
    "delay_between_items",
    fallback=0.3
)


ONLY_PDF = CONFIG[
    "PROCESSING"
].getboolean(
    "only_pdf",
    fallback=True
)


ATTACHMENT_NAME_CONTAINS = CONFIG[
    "PROCESSING"
].get(
    "attachment_name_contains",
    "FORM PSS"
).strip()


# ============================================================
# PATHS
# ============================================================

DOWNLOAD_DIR = caminho_projeto(
    CONFIG["PATHS"].get(
        "download_dir",
        "downloads"
    )
)


DOWNLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True
)


LOG_FILE = caminho_projeto(
    CONFIG["PATHS"].get(
        "log_file",
        "mxi_automacao.log"
    )
)


# ============================================================
# LOG
# ============================================================

logger = logging.getLogger(
    "REF_TECNICA"
)


logger.setLevel(
    logging.INFO
)


logger.handlers.clear()


formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S"
)


console_handler = logging.StreamHandler(
    sys.stdout
)


console_handler.setFormatter(
    formatter
)


file_handler = logging.FileHandler(
    LOG_FILE,
    mode="a",
    encoding="utf-8"
)


file_handler.setFormatter(
    formatter
)


logger.addHandler(
    console_handler
)


logger.addHandler(
    file_handler
)


# ============================================================
# NIVEIS VISUAIS
# ============================================================

def log_info(mensagem):

    logger.info(
        mensagem
    )


def log_ok(mensagem):

    # Utilizamos INFO internamente para nao precisar
    # criar um novo logging level.

    timestamp = time.strftime(
        "%H:%M:%S"
    )

    linha = (
        f"{timestamp} | "
        f"{'OK':<7} | "
        f"{mensagem}"
    )

    print(
        linha
    )


    try:

        with open(
            LOG_FILE,
            "a",
            encoding="utf-8"
        ) as arquivo:

            arquivo.write(
                linha + "\n"
            )

    except Exception:

        pass


def log_status(rotulo, mensagem):

    timestamp = time.strftime(
        "%H:%M:%S"
    )


    linha = (
        f"{timestamp} | "
        f"{rotulo:<7} | "
        f"{mensagem}"
    )


    print(
        linha
    )


    try:

        with open(
            LOG_FILE,
            "a",
            encoding="utf-8"
        ) as arquivo:

            arquivo.write(
                linha + "\n"
            )

    except Exception:

        pass


# ============================================================
# GOOGLE SHEETS
# ============================================================

def conectar_google_sheets():

    if not SHEETS_CREDENTIALS_FILE.exists():

        raise FileNotFoundError(
            "credentials.json nao encontrado."
        )


    credentials = (
        service_account.Credentials
        .from_service_account_file(
            str(
                SHEETS_CREDENTIALS_FILE
            ),
            scopes=SHEETS_SCOPES
        )
    )


    gc = gspread.authorize(
        credentials
    )


    spreadsheet = gc.open_by_key(
        SHEET_ID
    )


    worksheets = spreadsheet.worksheets()


    total_pns = 0


    for worksheet in worksheets:

        valores = worksheet.col_values(
            1
        )


        total_pns += len(
            [
                valor
                for valor in valores[1:]
                if valor.strip()
            ]
        )


    log_ok(
        (
            "Google Sheets conectado"
            f" | {len(worksheets)} abas"
            f" | {total_pns} PNs"
        )
    )


    return spreadsheet


# ============================================================
# DNS
# ============================================================

def testar_dns_mxi():

    host = urlparse(
        MXI_LOGIN_URL
    ).hostname


    try:

        socket.gethostbyname(
            host
        )


    except Exception as e:

        raise RuntimeError(
            f"MXI indisponivel / problema de rede ou VPN: {e}"
        )


# ============================================================
# CHROME
# ============================================================

def localizar_chrome():

    candidatos = [
        Path(
            os.environ.get(
                "PROGRAMFILES",
                r"C:\Program Files"
            )
        )
        /
        "Google/Chrome/Application/chrome.exe",

        Path(
            os.environ.get(
                "PROGRAMFILES(X86)",
                r"C:\Program Files (x86)"
            )
        )
        /
        "Google/Chrome/Application/chrome.exe",

        Path(
            os.environ.get(
                "LOCALAPPDATA",
                ""
            )
        )
        /
        "Google/Chrome/Application/chrome.exe"
    ]


    for candidato in candidatos:

        if candidato.exists():

            return str(
                candidato
            )


    return shutil.which(
        "chrome"
    )


def criar_driver():

    chrome_binary = localizar_chrome()


    if not chrome_binary:

        raise RuntimeError(
            "Google Chrome nao encontrado."
        )


    options = Options()


    options.page_load_strategy = (
        PAGE_LOAD_STRATEGY
    )


    options.binary_location = (
        chrome_binary
    )


    if HEADLESS:

        options.add_argument(
            "--headless=new"
        )


    if MAXIMIZE_WINDOW:

        options.add_argument(
            "--start-maximized"
        )


    options.add_argument(
        "--disable-notifications"
    )


    options.add_argument(
        "--disable-popup-blocking"
    )


    options.add_argument(
        "--disable-logging"
    )


    options.add_argument(
        "--log-level=3"
    )


    if IGNORE_CERTIFICATE_ERRORS:

        options.add_argument(
            "--ignore-certificate-errors"
        )


        options.add_argument(
            "--allow-insecure-localhost"
        )


    service = Service()


    driver = webdriver.Chrome(
        service=service,
        options=options
    )


    driver.set_page_load_timeout(
        PAGE_TIMEOUT
    )


    driver.set_script_timeout(
        PAGE_TIMEOUT
    )


    driver.implicitly_wait(
        IMPLICIT_WAIT
    )


    return driver


# ============================================================
# LOGIN MXI
# ============================================================

def login_mxi(
    driver
):

    driver.get(
        MXI_LOGIN_URL
    )


    wait = WebDriverWait(
        driver,
        30,
        poll_frequency=0.5
    )


    usuario = wait.until(
        EC.visibility_of_element_located(
            (
                By.ID,
                "j_username"
            )
        )
    )


    senha = wait.until(
        EC.visibility_of_element_located(
            (
                By.ID,
                "j_password"
            )
        )
    )


    botao = wait.until(
        EC.element_to_be_clickable(
            (
                By.ID,
                "idButtonLogin"
            )
        )
    )


    usuario.clear()


    usuario.send_keys(
        MXI_USER
    )


    senha.clear()


    senha.send_keys(
        MXI_PASSWORD
    )


    try:

        driver.set_page_load_timeout(
            LOGIN_CLICK_TIMEOUT
        )


        botao.click()


    except (
        TimeoutException,
        WebDriverException
    ):

        # O MXI pode travar o renderer durante o redirect.
        # Nao significa necessariamente falha de login.
        pass


    finally:

        try:

            driver.set_page_load_timeout(
                PAGE_TIMEOUT
            )

        except Exception:

            pass


    wait_login = WebDriverWait(
        driver,
        LOGIN_TIMEOUT,
        poll_frequency=0.5
    )


    elemento = wait_login.until(
        EC.visibility_of_element_located(
            (
                By.ID,
                MXI_SUCCESS_ELEMENT_ID
            )
        )
    )


    wait_login.until(
        EC.text_to_be_present_in_element(
            (
                By.ID,
                MXI_SUCCESS_ELEMENT_ID
            ),
            MXI_SUCCESS_TEXT
        )
    )


    if (
        MXI_SUCCESS_TEXT
        not in
        elemento.text
    ):

        raise RuntimeError(
            "Login MXI nao confirmado."
        )


    if POST_LOGIN_WAIT > 0:

        time.sleep(
            POST_LOGIN_WAIT
        )


    log_ok(
        "Login MXI realizado"
    )


# ============================================================
# HTTP SESSION
# ============================================================

def criar_session_mxi(
    driver
):

    session = requests.Session()


    try:

        user_agent = driver.execute_script(
            "return navigator.userAgent;"
        )


    except Exception:

        user_agent = (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64)"
        )


    session.headers.update(
        {
            "User-Agent": user_agent,

            "Accept-Language": (
                "pt-BR,pt;q=0.9,"
                "en-US;q=0.8,en;q=0.7"
            )
        }
    )


    for cookie in driver.get_cookies():

        argumentos = {
            "name": cookie[
                "name"
            ],

            "value": cookie[
                "value"
            ],

            "path": cookie.get(
                "path",
                "/"
            )
        }


        if cookie.get(
            "domain"
        ):

            argumentos[
                "domain"
            ] = cookie[
                "domain"
            ]


        session.cookies.set(
            **argumentos
        )


    return session


# ============================================================
# LOGIN PAGE?
# ============================================================

def pagina_e_login(
    html
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    if soup.find(
        id="j_username"
    ):

        return True


    title_tag = soup.find(
        "title"
    )


    if (
        title_tag
        and
        "please login"
        in
        title_tag.get_text(
            " ",
            strip=True
        ).lower()
    ):

        return True


    return False


# ============================================================
# FORMULARIO SEARCH
# ============================================================

def extrair_formulario_busca(
    html
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    campo = soup.find(
        attrs={
            "name": "aPartNo_OEM"
        }
    )


    if campo is None:

        raise RuntimeError(
            "Campo de pesquisa OEM nao encontrado."
        )


    form = campo.find_parent(
        "form"
    )


    if form is None:

        raise RuntimeError(
            "Formulario Part Search nao encontrado."
        )


    dados = {}


    for input_tag in form.find_all(
        "input"
    ):

        nome = input_tag.get(
            "name"
        )


        if not nome:

            continue


        tipo = input_tag.get(
            "type",
            "text"
        ).lower()


        if tipo in {
            "submit",
            "button",
            "reset",
            "image",
            "file"
        }:

            continue


        if (
            tipo
            in {
                "checkbox",
                "radio"
            }
            and
            not input_tag.has_attr(
                "checked"
            )
        ):

            continue


        dados[
            nome
        ] = input_tag.get(
            "value",
            ""
        )


    for select in form.find_all(
        "select"
    ):

        nome = select.get(
            "name"
        )


        if not nome:

            continue


        option = select.find(
            "option",
            selected=True
        )


        if option is None:

            option = select.find(
                "option"
            )


        if option:

            dados[
                nome
            ] = option.get(
                "value",
                ""
            )


    return {
        "action": form.get(
            "action",
            ""
        ),

        "data": dados
    }


# ============================================================
# LOCALIZAR RESULTADO EXATO
# ============================================================

def localizar_linha_resultado(
    soup,
    pn
):

    pn_normalizado = normalizar_pn(
        pn
    )


    candidatos = []


    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get(
            "href",
            ""
        )


        if "PartDetails.jsp" not in href:

            continue


        candidatos.append(
            link
        )


        texto = normalizar_pn(
            link.get_text(
                " ",
                strip=True
            )
        )


        if texto == pn_normalizado:

            return (
                link,
                link.find_parent(
                    "tr"
                )
            )


    if len(
        candidatos
    ) == 1:

        link = candidatos[
            0
        ]


        return (
            link,
            link.find_parent(
                "tr"
            )
        )


    return (
        None,
        None
    )


# ============================================================
# MANUFACTURER
# ============================================================

def extrair_manufacturer_da_linha(
    row
):

    if row is None:

        return ""


    table = row.find_parent(
        "table"
    )


    # ========================================================
    # IDENTIFICAR PELO CABECALHO
    # ========================================================

    if table:

        header_row = None


        for linha in table.find_all(
            "tr"
        ):

            if linha is row:

                break


            cells = linha.find_all(
                [
                    "td",
                    "th"
                ],
                recursive=False
            )


            textos = [
                normalizar_texto(
                    cell.get_text(
                        " ",
                        strip=True
                    )
                )
                for cell in cells
            ]


            if any(
                "MANUFACTURER"
                in texto
                for texto in textos
            ):

                header_row = linha


        if header_row:

            headers = header_row.find_all(
                [
                    "td",
                    "th"
                ],
                recursive=False
            )


            cells = row.find_all(
                [
                    "td",
                    "th"
                ],
                recursive=False
            )


            for index, header in enumerate(
                headers
            ):

                texto = normalizar_texto(
                    header.get_text(
                        " ",
                        strip=True
                    )
                )


                if (
                    "MANUFACTURER"
                    in texto
                    and
                    index < len(
                        cells
                    )
                ):

                    valor = cells[
                        index
                    ].get_text(
                        " ",
                        strip=True
                    ).strip()


                    if valor:

                        return valor


    # ========================================================
    # FALLBACK PARA QSC
    # ========================================================

    texto_linha = row.get_text(
        " ",
        strip=True
    )


    match = re.search(
        r"\bQSC[A-Z0-9._/-]*\b",
        texto_linha,
        flags=re.IGNORECASE
    )


    if match:

        return match.group(
            0
        )


    # ========================================================
    # FALLBACK POSICIONAL
    # ========================================================

    cells = row.find_all(
        [
            "td",
            "th"
        ],
        recursive=False
    )


    if len(
        cells
    ) >= 5:

        return cells[
            4
        ].get_text(
            " ",
            strip=True
        ).strip()


    return ""


# ============================================================
# RESULTADO PART SEARCH
# ============================================================

def extrair_dados_resultado_pn(
    html,
    pn,
    base_url
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    link, row = localizar_linha_resultado(
        soup,
        pn
    )


    if link is None:

        return {
            "part_details_url": None,
            "manufacturer": ""
        }


    return {
        "part_details_url": urljoin(
            base_url,
            link.get(
                "href",
                ""
            )
        ),

        "manufacturer": (
            extrair_manufacturer_da_linha(
                row
            )
        )
    }


# ============================================================
# MRO
# ============================================================

def fabricante_e_mro(
    manufacturer
):

    return normalizar_texto(
        manufacturer
    ).startswith(
        "QSC"
    )


# ============================================================
# PESQUISAR PN
# ============================================================

def pesquisar_pn_mxi(
    session,
    pn
):

    response_get = session.get(
        MXI_PART_SEARCH_URL,
        timeout=30,
        verify=MXI_VERIFY_SSL,
        allow_redirects=True
    )


    response_get.raise_for_status()


    if pagina_e_login(
        response_get.text
    ):

        raise RuntimeError(
            "Sessao MXI expirada."
        )


    formulario = extrair_formulario_busca(
        response_get.text
    )


    dados = dict(
        formulario[
            "data"
        ]
    )


    dados[
        "aSearchType"
    ] = MXI_SEARCH_TYPE


    dados[
        "aPartNo_OEM"
    ] = pn


    dados[
        "aMaxResults"
    ] = str(
        MXI_MAX_RESULTS
    )


    dados[
        "aSearch"
    ] = "true"


    action = formulario.get(
        "action",
        ""
    )


    post_url = (
        urljoin(
            response_get.url,
            action
        )
        if action
        else
        MXI_PART_SEARCH_URL
    )


    parsed = urlparse(
        MXI_PART_SEARCH_URL
    )


    response = session.post(
        post_url,

        data=dados,

        headers={
            "Referer": response_get.url,

            "Origin": (
                f"{parsed.scheme}://"
                f"{parsed.netloc}"
            ),

            "Content-Type": (
                "application/x-www-form-urlencoded"
            )
        },

        timeout=30,

        verify=MXI_VERIFY_SSL,

        allow_redirects=True
    )


    response.raise_for_status()


    if pagina_e_login(
        response.text
    ):

        raise RuntimeError(
            "Sessao MXI expirada."
        )


    texto = BeautifulSoup(
        response.text,
        "html.parser"
    ).get_text(
        " ",
        strip=True
    )


    quantidade = None


    match = re.search(
        r"(\d+)\s+part\s+was\s+found",
        texto,
        flags=re.IGNORECASE
    )


    if not match:

        match = re.search(
            r"(\d+)\s+parts\s+were\s+found",
            texto,
            flags=re.IGNORECASE
        )


    if match:

        quantidade = int(
            match.group(
                1
            )
        )


    encontrado = (
        quantidade is not None
        and
        quantidade > 0
    )


    if not encontrado:

        return {
            "encontrado": False,

            "manufacturer": "",

            "fabricado_mro": False,

            "part_details_url": None
        }


    resultado = extrair_dados_resultado_pn(
        response.text,
        pn,
        response.url
    )


    manufacturer = resultado.get(
        "manufacturer",
        ""
    ).strip()


    return {
        "encontrado": True,

        "manufacturer": manufacturer,

        "fabricado_mro": fabricante_e_mro(
            manufacturer
        ),

        "part_details_url": resultado.get(
            "part_details_url"
        )
    }


# ============================================================
# URL DETAILS
# ============================================================

def criar_url_details_tab(
    part_details_url
):

    if re.search(
        r"([?&])aTab=",
        part_details_url,
        flags=re.IGNORECASE
    ):

        return re.sub(
            r"([?&])aTab=[^&]*",
            r"\1aTab=idTabDetails",
            part_details_url,
            flags=re.IGNORECASE
        )


    separador = (
        "&"
        if "?" in part_details_url
        else "?"
    )


    return (
        part_details_url
        +
        separador
        +
        "aTab=idTabDetails"
    )


# ============================================================
# ATTACHMENTS
# ============================================================

def obter_attachments(
    session,
    part_details_url
):

    details_url = criar_url_details_tab(
        part_details_url
    )


    response = session.get(
        details_url,

        headers={
            "Referer": part_details_url
        },

        timeout=30,

        verify=MXI_VERIFY_SSL,

        allow_redirects=True
    )


    response.raise_for_status()


    if pagina_e_login(
        response.text
    ):

        raise RuntimeError(
            "Sessao MXI expirada."
        )


    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )


    encontrados = []


    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get(
            "href",
            ""
        )


        if (
            "/maintenix/servlet/ViewAttachment"
            not in href
        ):

            continue


        encontrados.append(
            {
                "name": link.get_text(
                    " ",
                    strip=True
                ),

                "url": urljoin(
                    response.url,
                    href
                ),

                "referer": response.url
            }
        )


    # ========================================================
    # REMOVE DUPLICADOS
    # ========================================================

    unicos = []

    vistos = set()


    for item in encontrados:

        if item[
            "url"
        ] in vistos:

            continue


        vistos.add(
            item[
                "url"
            ]
        )


        unicos.append(
            item
        )


    # ========================================================
    # FILTRO
    # ========================================================

    if ATTACHMENT_NAME_CONTAINS:

        filtro = (
            ATTACHMENT_NAME_CONTAINS
            .lower()
        )


        unicos = [
            item
            for item in unicos
            if filtro
            in item[
                "name"
            ].lower()
        ]


    return unicos


# ============================================================
# CONTENT DISPOSITION
# ============================================================

def extrair_nome_content_disposition(
    response
):

    valor = response.headers.get(
        "Content-Disposition",
        ""
    )


    if not valor:

        return None


    match = re.search(
        r"filename\*=UTF-8''([^;]+)",
        valor,
        flags=re.IGNORECASE
    )


    if match:

        return unquote(
            match.group(
                1
            )
        )


    match = re.search(
        r'filename="?([^";]+)"?',
        valor,
        flags=re.IGNORECASE
    )


    if match:

        return match.group(
            1
        ).strip()


    return None


# ============================================================
# EVITAR SOBRESCREVER ARQUIVO DIFERENTE
# ============================================================

def caminho_download_disponivel(
    nome
):

    caminho = (
        DOWNLOAD_DIR /
        nome
    )


    if not caminho.exists():

        return caminho


    # O arquivo ja existe.
    # Como os nomes normalmente possuem PN,
    # reutilizamos o arquivo existente.

    return caminho


# ============================================================
# DOWNLOAD
# ============================================================

def baixar_attachment(
    session,
    pn,
    attachment
):

    response = session.get(
        attachment[
            "url"
        ],

        headers={
            "Referer": attachment.get(
                "referer",
                ""
            )
        },

        timeout=120,

        verify=MXI_VERIFY_SSL,

        allow_redirects=True,

        stream=True
    )


    response.raise_for_status()


    content_type = (
        response.headers.get(
            "Content-Type",
            ""
        )
        .lower()
    )


    if "text/html" in content_type:

        raise RuntimeError(
            "MXI retornou HTML no lugar do PDF."
        )


    nome_servidor = (
        extrair_nome_content_disposition(
            response
        )
    )


    nome = (
        attachment.get(
            "name"
        )
        or
        nome_servidor
        or
        f"{pn}.pdf"
    )


    nome = nome_seguro(
        nome
    )


    if not nome.lower().endswith(
        ".pdf"
    ):

        nome += ".pdf"


    caminho = caminho_download_disponivel(
        nome
    )


    iterator = response.iter_content(
        chunk_size=65536
    )


    try:

        primeiro = next(
            iterator
        )


    except StopIteration:

        primeiro = b""


    if not primeiro:

        raise RuntimeError(
            "Arquivo vazio."
        )


    parece_pdf = (
        primeiro
        .lstrip()
        .startswith(
            b"%PDF"
        )
        or
        "application/pdf"
        in content_type
    )


    if ONLY_PDF and not parece_pdf:

        raise RuntimeError(
            "Attachment encontrado, mas nao e um PDF valido."
        )


    with open(
        caminho,
        "wb"
    ) as arquivo:

        arquivo.write(
            primeiro
        )


        for chunk in iterator:

            if chunk:

                arquivo.write(
                    chunk
                )


    return caminho


# ============================================================
# PROCESSAR PN
# ============================================================

def processar_pn(
    session,
    pn
):

    busca = pesquisar_pn_mxi(
        session,
        pn
    )


    # ========================================================
    # PN NAO EXISTE
    # ========================================================

    if not busca[
        "encontrado"
    ]:

        return {
            "status": "PN NAO ENCONTRADO",

            "detalhe": (
                "Part Number nao encontrado no MXI."
            )
        }


    manufacturer = busca.get(
        "manufacturer",
        ""
    ).strip()


    fabricado_mro = busca.get(
        "fabricado_mro",
        False
    )


    part_details_url = busca.get(
        "part_details_url"
    )


    if not part_details_url:

        return {
            "status": "ERRO",

            "detalhe": (
                "PN encontrado, mas Part Details "
                "nao foi localizado."
            )
        }


    # ========================================================
    # SEMPRE PROCURAR FORM PSS
    # ========================================================

    attachments = obter_attachments(
        session,
        part_details_url
    )


    # ========================================================
    # NAO POSSUI FORM PSS
    # ========================================================

    if not attachments:

        if fabricado_mro:

            return {
                "status": (
                    "ITEM FABRICADO MRO - SEM FORM PSS"
                ),

                "detalhe": (
                    f"Manufacturer: {manufacturer}"
                )
            }


        return {
            "status": "SEM FORM PSS",

            "detalhe": (
                f"Manufacturer: "
                f"{manufacturer or 'NAO IDENTIFICADO'}"
            )
        }


    # ========================================================
    # DOWNLOAD DOS FORM PSS
    # ========================================================

    downloads = []

    erros = []


    for attachment in attachments:

        try:

            caminho = baixar_attachment(
                session,
                pn,
                attachment
            )


            downloads.append(
                caminho
            )


        except Exception as e:

            erros.append(
                str(
                    e
                )
            )


    # ========================================================
    # PDF BAIXADO
    # ========================================================

    if downloads:

        nomes = [
            caminho.name
            for caminho in downloads
        ]


        detalhe = (
            " | ".join(
                nomes
            )
        )


        if manufacturer:

            detalhe += (
                f" | Manufacturer: {manufacturer}"
            )


        if fabricado_mro:

            detalhe += (
                " | Item Fabricado MRO"
            )


        return {
            "status": "PDF BAIXADO",

            "detalhe": detalhe
        }


    # ========================================================
    # EXISTIA PSS, MAS DOWNLOAD FALHOU
    # ========================================================

    return {
        "status": "ERRO",

        "detalhe": (
            "FORM PSS encontrado, "
            "mas download falhou: "
            +
            " | ".join(
                erros
            )
        )[
            :10000
        ]
    }


# ============================================================
# SHEET
# ============================================================

def validar_headers(
    worksheet
):

    headers = worksheet.row_values(
        1
    )


    esperado = [
        "Part Number",
        "STATUS",
        "DETALHE_STATUS",
        "LINK_PDF"
    ]


    if headers[
        :4
    ] != esperado:

        raise RuntimeError(
            (
                f"Cabecalho incorreto na aba "
                f"{worksheet.title}"
            )
        )


def atualizar_linha(
    worksheet,
    row,
    resultado
):

    # ========================================================
    # SOMENTE B:C
    #
    # LINK_PDF (D) NAO E ALTERADO.
    # ========================================================

    worksheet.update(
        range_name=(
            f"B{row}:C{row}"
        ),

        values=[
            [
                resultado.get(
                    "status",
                    ""
                ),

                resultado.get(
                    "detalhe",
                    ""
                )
            ]
        ]
    )


# ============================================================
# CARREGAR FILA
# ============================================================

def carregar_fila(
    spreadsheet
):

    fila = []


    for worksheet in spreadsheet.worksheets():

        validar_headers(
            worksheet
        )


        linhas = worksheet.get_all_values()


        for row, linha in enumerate(
            linhas[
                1:
            ],
            start=2
        ):

            pn = (
                linha[
                    0
                ].strip()
                if len(
                    linha
                ) >= 1
                else ""
            )


            status = (
                linha[
                    1
                ].strip()
                if len(
                    linha
                ) >= 2
                else ""
            )


            if not pn:

                continue


            # =================================================
            # LINHA JA FINALIZADA
            # =================================================

            if (
                PROCESS_ONLY_BLANK_STATUS
                and
                status
                and
                normalizar_texto(
                    status
                )
                not in RETRY_STATUSES
            ):

                continue


            fila.append(
                {
                    "worksheet": worksheet,

                    "aba": worksheet.title,

                    "row": row,

                    "pn": pn
                }
            )


    if (
        MAX_ITEMS > 0
        and
        len(
            fila
        ) > MAX_ITEMS
    ):

        fila = fila[
            :MAX_ITEMS
        ]


    return fila


# ============================================================
# PROCESSAMENTO
# ============================================================

def executar_planilha(
    spreadsheet,
    session
):

    fila = carregar_fila(
        spreadsheet
    )


    total = len(
        fila
    )


    if total == 0:

        log_ok(
            "Nenhum item pendente."
        )


        return


    log_info(
        f"{total} itens pendentes para processamento"
    )


    estatisticas = {
        "processados": 0,
        "pdf": 0,
        "mro": 0,
        "sem_pss": 0,
        "nao_encontrado": 0,
        "erro": 0
    }


    for numero, item in enumerate(
        fila,
        start=1
    ):

        worksheet = item[
            "worksheet"
        ]


        aba = item[
            "aba"
        ]


        row = item[
            "row"
        ]


        pn = item[
            "pn"
        ]


        log_info(
            (
                f"[{numero}/{total}] "
                f"{aba} | PN {pn}"
            )
        )


        try:

            resultado = processar_pn(
                session,
                pn
            )


        except Exception as e:

            logger.exception(
                "Falha inesperada no PN %s",
                pn
            )


            resultado = {
                "status": "ERRO",

                "detalhe": (
                    f"{type(e).__name__}: {e}"
                )[
                    :10000
                ]
            }


        # ====================================================
        # SHEETS
        # ====================================================

        try:

            atualizar_linha(
                worksheet,
                row,
                resultado
            )


        except Exception as e:

            logger.error(
                (
                    "Falha ao atualizar planilha"
                    f" | {aba}"
                    f" | PN {pn}"
                    f" | {e}"
                )
            )


            estatisticas[
                "erro"
            ] += 1


            continue


        estatisticas[
            "processados"
        ] += 1


        status = resultado.get(
            "status",
            ""
        )


        detalhe = resultado.get(
            "detalhe",
            ""
        )


        status_norm = normalizar_texto(
            status
        )


        # ====================================================
        # LOG LIMPO POR RESULTADO
        # ====================================================

        if status_norm == "PDF BAIXADO":

            estatisticas[
                "pdf"
            ] += 1


            nomes_pdf = detalhe.split(
                " | Manufacturer:"
            )[
                0
            ]


            log_status(
                "OK",
                (
                    f"{pn} | "
                    f"PDF BAIXADO | "
                    f"{nomes_pdf}"
                )
            )


        elif (
            status_norm
            ==
            "ITEM FABRICADO MRO - SEM FORM PSS"
        ):

            estatisticas[
                "mro"
            ] += 1


            log_status(
                "MRO",
                (
                    f"{pn} | "
                    f"SEM FORM PSS | "
                    f"{detalhe}"
                )
            )


        elif status_norm == "SEM FORM PSS":

            estatisticas[
                "sem_pss"
            ] += 1


            log_status(
                "SEM PSS",
                (
                    f"{pn} | "
                    f"{detalhe}"
                )
            )


        elif status_norm == "PN NAO ENCONTRADO":

            estatisticas[
                "nao_encontrado"
            ] += 1


            log_status(
                "NAO MXI",
                (
                    f"{pn} | "
                    f"PN nao encontrado"
                )
            )


        else:

            estatisticas[
                "erro"
            ] += 1


            log_status(
                "ERRO",
                (
                    f"{pn} | "
                    f"{detalhe}"
                )
            )


        # ====================================================
        # DELAY
        # ====================================================

        if DELAY_BETWEEN_ITEMS > 0:

            time.sleep(
                DELAY_BETWEEN_ITEMS
            )


    # ========================================================
    # RESUMO
    # ========================================================

    print()
    print(
        "-" * 60
    )
    print(
        "RESUMO"
    )
    print(
        "-" * 60
    )


    print(
        f"Processados............... "
        f"{estatisticas['processados']}"
    )


    print(
        f"PDFs baixados............ "
        f"{estatisticas['pdf']}"
    )


    print(
        f"MRO sem FORM PSS......... "
        f"{estatisticas['mro']}"
    )


    print(
        f"Sem FORM PSS............. "
        f"{estatisticas['sem_pss']}"
    )


    print(
        f"PN nao encontrado........ "
        f"{estatisticas['nao_encontrado']}"
    )


    print(
        f"Erros.................... "
        f"{estatisticas['erro']}"
    )


    print(
        "-" * 60
    )


    print(
        f"PDFs: {DOWNLOAD_DIR}"
    )


    print(
        f"Log : {LOG_FILE}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    driver = None

    session = None


    try:

        log_info(
            "Iniciando VERIFICAR REF TECNICA"
        )


        # ====================================================
        # GOOGLE SHEETS
        # ====================================================

        spreadsheet = conectar_google_sheets()


        # ====================================================
        # REDE
        # ====================================================

        testar_dns_mxi()


        # ====================================================
        # CHROME
        # ====================================================

        driver = criar_driver()


        # ====================================================
        # MXI LOGIN
        # ====================================================

        login_mxi(
            driver
        )


        # ====================================================
        # HTTP SESSION
        # ====================================================

        session = criar_session_mxi(
            driver
        )


        # ====================================================
        # PROCESSAR
        # ====================================================

        executar_planilha(
            spreadsheet,
            session
        )


        log_ok(
            "Automacao finalizada"
        )


    # ========================================================
    # INTERRUPCAO MANUAL
    # ========================================================

    except KeyboardInterrupt:

        print()


        logger.warning(
            "Execucao interrompida pelo usuario."
        )


    # ========================================================
    # ERRO GERAL
    # ========================================================

    except Exception as e:

        logger.exception(
            (
                f"Automacao interrompida"
                f" | {type(e).__name__}: {e}"
            )
        )


    # ========================================================
    # ENCERRAMENTO
    # ========================================================

    finally:

        if session:

            try:

                session.close()

            except Exception:

                pass


        if driver:

            try:

                driver.quit()

            except Exception:

                pass


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()