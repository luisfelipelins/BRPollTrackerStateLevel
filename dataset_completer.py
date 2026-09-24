import numpy as np
import pandas as pd
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import requests
import re
import unicodedata
from ddgs import DDGS
from html import unescape
from html.parser import HTMLParser
import os
import json
import csv
import time

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATUS_PATH = DATA_DIR / "poll_status.csv"
TSE_URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/pesquisa_eleitoral/pesquisa_eleitoral_2026.zip"
TSE_PAGE = "https://dadosabertos.tse.jus.br/dataset/pesquisas-eleitorais-2026"
TSE_CSV = "pesquisa_eleitoral_2026_BRASIL.csv"

mapa_institutos_2026 = {
    "MDA-PESQUISA DE OPINIAO PUBLICA E CONSULT. ESTATIST. LTDA - EPP": "MDA",
    "QUAEST PESQUISAS, CONSULTORIA E PROJETOS LTDA.": "Quaest",
    "DATAFOLHA INSTITUTO DE PESQUISAS LTDA.": "Datafolha",
    "ATLASINTEL": "AtlasIntel/Internet",
    "INSTITUTO PARANA DE PESQUISAS E ANALISE DE CONSUMIDOR LTDA": "Paraná Pesquisas",
    "NEXUS": "FSB",
    "PODERDATA": "PoderData",
    "BOAS IDEIAS, ESTRATEGIA E INTELIGENCIA DIGITAL.": "Ideia Big Data",
    "IPEC": "Ipec",
    "REAL TIME BIG DATA": "Real Time Big Data",
    "100 CIDADES": "Futura"
}

SEARCH_NAMES = {
    "MDA": ["MDA", "CNT/MDA"],
    "Quaest": ["Quaest"],
    "Datafolha": ["Datafolha"],
    "AtlasIntel/Internet": ["AtlasIntel"],
    "Paraná Pesquisas": ["Paraná Pesquisas"],
    "FSB": ["Nexus", "BTG/Nexus"],
    "PoderData": ["PoderData"],
    "Ideia Big Data": ["Ideia Big Data"],
    "Ipec": ["Ipec"],
    "Real Time Big Data": ["Real Time Big Data"],
    "Futura": ["Futura", "100% Cidades"]
}

UF_NAMES = {
    "AC": "ACRE", "AL": "ALAGOAS", "AP": "AMAPA", "AM": "AMAZONAS", "BA": "BAHIA",
    "CE": "CEARA", "DF": "DISTRITO FEDERAL", "ES": "ESPIRITO SANTO", "GO": "GOIAS",
    "MA": "MARANHAO", "MT": "MATO GROSSO", "MS": "MATO GROSSO DO SUL",
    "MG": "MINAS GERAIS", "PA": "PARA", "PB": "PARAIBA", "PR": "PARANA",
    "PE": "PERNAMBUCO", "PI": "PIAUI", "RJ": "RIO DE JANEIRO",
    "RN": "RIO GRANDE DO NORTE", "RS": "RIO GRANDE DO SUL", "RO": "RONDONIA",
    "RR": "RORAIMA", "SC": "SANTA CATARINA", "SP": "SAO PAULO",
    "SE": "SERGIPE", "TO": "TOCANTINS"
}

def clean_polls(path, start_date):
    df = pd.read_csv(path, sep=";", encoding="latin1")
    df["DT_DIVULGACAO"] = pd.to_datetime(df["DT_DIVULGACAO"], errors="coerce")
    start_date = pd.to_datetime(start_date)

    # Keep only polls containing information for President
    df = df[df["DS_CARGO"].fillna("").str.contains(r"\bPRESIDENTE\b", case=False, regex=True)].copy()

    # Map institutes using exact TSE names
    df["instituto"] = df["NM_EMPRESA"].map(mapa_institutos_2026)
    missing = df["instituto"].isna()
    df.loc[missing, "instituto"] = df.loc[missing, "NM_EMPRESA_FANTASIA"].map(mapa_institutos_2026)

    # Keep only institutes of interest and polls from start date onward
    df = df[df["instituto"].notna() & (df["DT_DIVULGACAO"] >= start_date)].copy()

    # Format poll ID
    df["numero_pesquisa"] = df["NR_PROTOCOLO_REGISTRO"].astype(str).str.replace(r"^([A-Z]{2})(\d{5})(\d{4})$", r"\1-\2/\3", regex=True)

    # Remove duplicates and sort
    df = df.drop_duplicates(subset="NR_PROTOCOLO_REGISTRO")
    df = df.sort_values(["DT_DIVULGACAO", "instituto"]).reset_index(drop=True)
    return df

def add_new_polls(tse_polls, data_path=DATA_DIR / "data.csv"):
    data_path = Path(data_path)
    data = pd.read_csv(data_path, encoding="utf-8", encoding_errors="replace", low_memory=False)
    tse = tse_polls.drop_duplicates("numero_pesquisa").copy()

    # A poll is new only if its TSE registration number is not already in data.csv
    existing_polls = set(data["numero_registro"].dropna().astype(str).str.strip())
    new_polls = tse[~tse["numero_pesquisa"].astype(str).str.strip().isin(existing_polls)].copy()
    new_polls["uf_inferida"] = new_polls["DS_METODOLOGIA_PESQUISA"].apply(infer_uf)

    if new_polls.empty:
        print("No new polls found.")
        return pd.DataFrame(columns=data.columns)

    print(f"Found {len(new_polls)} new polls:")
    print(new_polls[["numero_pesquisa", "DT_DIVULGACAO", "instituto", "uf_inferida"]].to_string(index=False))

    # Create two blank rows per new poll
    candidates = pd.DataFrame({"nome_candidato": ["Lula", "Flávio Bolsonaro"]})
    polls = new_polls.merge(candidates, how="cross")

    rows = pd.DataFrame(np.nan, index=range(len(polls)), columns=data.columns)
    rows["id_pesquisa"] = polls["NR_PROTOCOLO_REGISTRO"].values
    rows["ano"] = 2026
    rows["sigla_uf"] = polls["uf_inferida"].replace("BR", np.nan).values
    rows["cargo"] = "presidente"

    dates = pd.to_datetime(polls["DT_DIVULGACAO"], errors="coerce")
    rows["data"] = [f"{d.month}/{d.day}/{d.year}" if pd.notna(d) else np.nan for d in dates]

    rows["instituto"] = polls["instituto"].values
    rows["numero_registro"] = polls["numero_pesquisa"].values
    rows["tipo"] = "estimulada"
    rows["turno"] = 2
    rows["nome_candidato"] = polls["nome_candidato"].values
    rows["percentual"] = np.nan

    rows.to_csv(data_path, mode="a", header=False, index=False, encoding="utf-8")
    print(f"Added {len(new_polls)} new polls ({len(rows)} rows).")
    return rows

def download_tse_data(output_path=DATA_DIR / "tse.csv"):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-User": "?1"
    }

    print("Downloading TSE data...")

    with requests.Session() as session:
        session.headers.update(headers)
        session.get(TSE_PAGE, timeout=30)

        response = session.get(TSE_URL, headers={"Referer": TSE_PAGE}, timeout=120)
        print(f"TSE response: HTTP {response.status_code}")
        response.raise_for_status()

    with ZipFile(BytesIO(response.content)) as archive:
        if TSE_CSV not in archive.namelist():
            raise FileNotFoundError(f"{TSE_CSV} not found inside TSE ZIP.")
        output_path.write_bytes(archive.read(TSE_CSV))

    print(f"TSE data saved to {output_path}")
    return output_path

def normalize_text(text):
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().upper()

def infer_uf(metodologia):
    text = normalize_text(metodologia)

    # 1. Explicit UF in parentheses: "(SP)", "(MS)", etc.
    for uf in UF_NAMES:
        if re.search(rf"\({uf}\)", text):
            return uf

    # 2. Look for state names only in geographic contexts
    contexts = [
        "ESTADO DE ", "ESTADO DO ", "ESTADO DA ",
        "ELEITORADO DE ", "ELEITORADO DO ", "ELEITORADO DA ",
        "POPULACAO DE ", "POPULACAO DO ", "POPULACAO DA ",
        "POPULACAO BRASILEIRA DE ",
        "RESIDENTE NO ESTADO DE ", "RESIDENTE NO ESTADO DO ", "RESIDENTE NO ESTADO DA ",
        "RESIDENTE NO ", "RESIDENTE EM ", "RESIDENTES EM ",
        "CARACTERISTICAS DO ELEITORADO DE ",
        "PESQUISA REALIZADA NO ESTADO DE ", "PESQUISA REALIZADA NO ESTADO DO ", "PESQUISA REALIZADA NO ESTADO DA "
    ]

    # Longest names first so "MATO GROSSO DO SUL" is checked before "MATO GROSSO"
    states = sorted(UF_NAMES.items(), key=lambda x: len(x[1]), reverse=True)

    for uf, state in states:
        for context in contexts:
            if re.search(re.escape(context + state) + r"\b", text):
                return uf

    # 3. National polls
    national_patterns = [
        r"\bELEITORADO BRASILEIRO\b",
        r"\bCONJUNTO DO ELEITORADO BRASILEIRO\b",
        r"\bPOPULACAO BRASILEIRA\b",
        r"\bRESIDENTE NO BRASIL\b",
        r"\bELEITORES E ELEITORAS DO BRASIL\b",
        r"\bELEITORADO DE BRASIL\b",
        r"\bPESQUISA REALIZADA NO BRASIL\b",
        r"\bTODO O PAIS\b",
        r"\bTERRITORIO NACIONAL\b",
        r"\bAMBITO NACIONAL\b"
    ]

    if any(re.search(pattern, text) for pattern in national_patterns):
        return "BR"

    return "BR"

def find_pending_polls(data_path=DATA_DIR / "data.csv", as_of=None):
    data = pd.read_csv(data_path, encoding="utf-8", encoding_errors="replace", low_memory=False)

    data["data"] = pd.to_datetime(data["data"], errors="coerce")
    data["percentual_num"] = pd.to_numeric(data["percentual"], errors="coerce")

    if as_of is None:
        as_of = pd.Timestamp.today().normalize()
    else:
        as_of = pd.to_datetime(as_of).normalize()

    # Keep only 2026 presidential runoff polls whose publication date has arrived
    eligible = data[
        (data["ano"] == 2026) &
        (data["cargo"].astype(str).str.lower() == "presidente") &
        (pd.to_numeric(data["turno"], errors="coerce") == 2) &
        (data["data"] <= as_of)
    ].copy()

    # A poll is pending if at least one candidate still has no result
    pending_rows = eligible[eligible["percentual_num"].isna()].copy()

    if pending_rows.empty:
        return pd.DataFrame(columns=["numero_registro", "data", "instituto", "sigla_uf", "missing_candidates"])

    pending = (
        pending_rows
        .groupby(["numero_registro", "data", "instituto", "sigla_uf"], dropna=False)["nome_candidato"]
        .agg(lambda x: ", ".join(x.astype(str)))
        .reset_index(name="missing_candidates")
        .sort_values(["data", "instituto"])
        .reset_index(drop=True)
    )

    return pending

def sync_poll_status(pending, status_path=STATUS_PATH):
    status_path = Path(status_path)
    columns = [
        "numero_registro", "result_status", "last_checked", "source_url",
        "source_type", "ai_model", "notes", "attempt_count"
    ]

    if status_path.exists():
        status = pd.read_csv(status_path, encoding="utf-8", low_memory=False)
    else:
        status = pd.DataFrame(columns=columns)

    schema_changed = False
    for col in columns:
        if col not in status.columns:
            status[col] = 0 if col == "attempt_count" else np.nan
            schema_changed = True

    status["attempt_count"] = pd.to_numeric(status["attempt_count"], errors="coerce").fillna(0).astype(int)

    # Reopen legacy no_runoff classifications: this status is no longer used
    legacy_no_runoff = status["result_status"].eq("no_runoff")
    if legacy_no_runoff.any():
        status.loc[legacy_no_runoff, "result_status"] = "pending"
        status.loc[legacy_no_runoff, "last_checked"] = np.nan
        status.loc[legacy_no_runoff, "attempt_count"] = 0
        status.loc[legacy_no_runoff, "notes"] = "Reopened after removing no_runoff status."
        schema_changed = True

    existing = set(status["numero_registro"].dropna().astype(str).str.strip())
    new_polls = pending[~pending["numero_registro"].astype(str).str.strip().isin(existing)][["numero_registro"]].drop_duplicates().copy()

    if new_polls.empty:
        if schema_changed:
            status.to_csv(status_path, index=False, encoding="utf-8")
        print("No new polls to add to poll_status.csv.")
        return status

    new_polls["result_status"] = "pending"
    new_polls["last_checked"] = np.nan
    new_polls["source_url"] = np.nan
    new_polls["source_type"] = np.nan
    new_polls["ai_model"] = np.nan
    new_polls["notes"] = np.nan
    new_polls["attempt_count"] = 0

    status = pd.concat([status, new_polls[columns]], ignore_index=True)
    status.to_csv(status_path, index=False, encoding="utf-8")
    print(f"Added {len(new_polls)} polls to poll_status.csv.")
    return status

def get_polls_to_search(pending, status, as_of=None):
    if pending.empty:
        return pending.copy()

    if as_of is None:
        as_of = pd.Timestamp.now()
    else:
        as_of = pd.to_datetime(as_of)

    status = status.copy()
    status["last_checked"] = pd.to_datetime(status["last_checked"], errors="coerce")
    if "attempt_count" not in status.columns:
        status["attempt_count"] = 0
    status["attempt_count"] = pd.to_numeric(status["attempt_count"], errors="coerce").fillna(0).astype(int)

    queue = pending.merge(
        status[["numero_registro", "result_status", "last_checked", "attempt_count"]],
        on="numero_registro",
        how="left"
    )

    queue["data"] = pd.to_datetime(queue["data"], errors="coerce")
    queue["age_days"] = (as_of.normalize() - queue["data"].dt.normalize()).dt.days

    # 0-5 days old: retry every 6 hours
    # 6+ days old: retry every 24 hours
    # >8 days old: record_not_found() makes it unresolved after 3 unsuccessful attempts
    queue["retry_hours"] = np.where(queue["age_days"] <= 5, 6, 24)

    never_checked = queue["last_checked"].isna()
    retry_deadline = queue["last_checked"] + pd.to_timedelta(queue["retry_hours"], unit="h")
    retry_time = retry_deadline <= as_of

    searchable_status = queue["result_status"].isin(["pending", "not_found"])
    queue = queue[searchable_status & (never_checked | retry_time)].copy()

    return queue.sort_values(["data", "instituto"]).reset_index(drop=True)

def build_search_queries(poll):
    registro = poll["numero_registro"]
    instituto = poll["instituto"]
    search_names = SEARCH_NAMES.get(instituto, [instituto])

    date = pd.to_datetime(poll["data"])
    date_str = date.strftime("%d/%m/%Y")

    queries = [
        f'"{registro}" pesquisa',
        f'"{registro}" Lula',
        f'"{registro}" "Flávio Bolsonaro"'
    ]

    for name in search_names:
        queries.append(f'"{registro}" "{name}"')
        queries.append(f'"{name}" Lula "Flávio Bolsonaro" "2º turno" {date_str}')

    return queries

def score_search_result(result, poll):
    target_registro = poll["numero_registro"]
    instituto = poll["instituto"]
    search_names = SEARCH_NAMES.get(instituto, [instituto])

    title = normalize_text(result.get("title", ""))
    snippet = normalize_text(result.get("snippet", ""))
    text = f"{title} {snippet}"
    target_text = normalize_text(target_registro)

    score = 0

    # Find TSE registration numbers mentioned in the result
    registros = set(re.findall(r"\b[A-Z]{2}-\d{5}/2026\b", text))

    # Exact registration number is extremely strong evidence
    if target_text in registros:
        score += 100

    # If another registration is explicitly mentioned, reject the result
    elif registros:
        return -1000

    # Institute name
    if any(normalize_text(name) in text for name in search_names):
        score += 20

    # Candidates
    if "LULA" in text:
        score += 5
    if "FLAVIO BOLSONARO" in text:
        score += 5

    # Runoff
    if "2 TURNO" in text or "SEGUNDO TURNO" in text:
        score += 10

    return score

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ["script", "style"]:
            self.skip = True

    def handle_endtag(self, tag):
        if tag in ["script", "style"]:
            self.skip = False

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)

    def get_text(self):
        return " ".join(self.text)


def fetch_page_text(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")

        if "text/html" not in content_type:
            print(f"Skipping non-HTML page: {url}")
            return None

        parser = HTMLTextExtractor()
        parser.feed(response.text)

        text = unescape(parser.get_text())
        text = re.sub(r"\s+", " ", text).strip()

        return text

    except Exception as e:
        print(f"Could not open page: {e}")
        return None

def fetch_top_pages(results, top_n=4):
    pages = []

    usable_results = [result for result in results if result["score"] >= 0]

    for result in usable_results[:top_n]:
        print(f"\nOpening: {result['title']}")
        print(f"URL: {result['url']}")

        text = fetch_page_text(result["url"])

        if not text:
            print("Could not extract page text.")
            continue

        page = result.copy()
        page["page_text"] = text

        pages.append(page)

        print(f"Page text extracted: {len(text):,} characters")

    return pages

def search_poll_web(poll, max_results=10):
    queries = build_search_queries(poll)
    results = []
    successful_queries = 0
    technical_errors = 0

    print(f"\nSearching {poll['numero_registro']} - {poll['instituto']}")

    with DDGS() as ddgs:
        for query in queries:
            print(f"\nQuery: {query}")

            try:
                search_results = ddgs.text(query, max_results=max_results)
                successful_queries += 1

                for result in search_results:
                    item = {
                        "query": query,
                        "title": result.get("title"),
                        "url": result.get("href"),
                        "snippet": result.get("body")
                    }

                    if not any([item["title"], item["url"], item["snippet"]]):
                        continue

                    results.append(item)

                    print(f"\nTitle: {item['title']}")
                    print(f"URL: {item['url']}")
                    print(f"Snippet: {item['snippet']}")

            except Exception as e:
                technical_errors += 1
                print(f"Search failed: {e}")

    if successful_queries == 0 and technical_errors > 0:
        raise RuntimeError(f"All {technical_errors} search queries failed technically.")

    # Score the results
    for result in results:
        result["score"] = score_search_result(result, poll)

    # Remove duplicated URLs, keeping the highest score
    unique_results = {}

    for result in results:
        url = result.get("url")

        if not url:
            continue

        if url not in unique_results or result["score"] > unique_results[url]["score"]:
            unique_results[url] = result

    results = list(unique_results.values())

    # Rank the remaining results
    results = sorted(results, key=lambda x: x["score"], reverse=True)

    print("\nRanked results:")
    for result in results:
        print(f"\nScore: {result['score']}")
        print(f"Title: {result['title']}")
        print(f"URL: {result['url']}")
        print(f"Snippet: {result['snippet']}")

    return results

def analyze_pages_with_ai(poll, pages):
    api_key_path = ROOT / "openrouter_api_key.txt"

    if not api_key_path.exists():
        raise FileNotFoundError("openrouter_api_key.txt not found.")

    api_key = api_key_path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("openrouter_api_key.txt is empty.")

    if not pages:
        return {
            "found": False,
            "status": "not_found",
            "lula": None,
            "flavio_bolsonaro": None,
            "source_url": None,
            "reason": "No pages available for analysis."
        }

    evidence = ""
    for i, page in enumerate(pages, start=1):
        text = page["page_text"][:12000]
        evidence += f"""
SOURCE {i}
URL: {page['url']}
TITLE: {page['title']}
TEXT:
{text}

"""

    prompt = f"""
You are extracting Brazilian presidential polling results.

TARGET POLL:
Registration number: {poll['numero_registro']}
Institute: {poll['instituto']}
Publication date: {pd.to_datetime(poll['data']).strftime('%d/%m/%Y')}
State: {poll['sigla_uf']}
Missing candidates: {poll['missing_candidates']}

We need the stimulated SECOND-ROUND scenario between:
- Lula
- Flávio Bolsonaro

Below are web pages found by a search engine.

Your task is to determine whether the supplied evidence contains the results of THIS SPECIFIC TARGET POLL.

Be extremely conservative.
Do NOT use results from another poll, another date, another institute, another registration number, or another electoral scenario.

Use exactly one of these statuses:
- "found": the evidence clearly identifies the target poll and gives the Lula vs Flávio Bolsonaro stimulated second-round percentages.
- "cancelled": the evidence clearly identifies the target poll and explicitly establishes that it was cancelled, annulled, withdrawn, or definitively not released. A temporary suspension alone is NOT enough; use "not_found" unless the evidence establishes a final cancellation/non-publication.
- "not_found": there is not enough evidence to identify the requested second-round result. This includes cases where you only find first-round results. Do NOT infer that no runoff existed merely because the supplied pages do not show it.

If a page contains Lula and Flávio Bolsonaro percentages but you cannot establish that they belong to the target poll, use "not_found".
If another TSE registration number is explicitly associated with the numbers, use "not_found".
Only return found=true when status="found". For every other status, return found=false.
For "cancelled", source_url must point to the supplied source that supports that conclusion.
Return percentages as numbers, without the % sign.

Return ONLY valid JSON using exactly this structure:
{{
    "found": true or false,
    "status": "found" or "not_found" or "cancelled",
    "lula": number or null,
    "flavio_bolsonaro": number or null,
    "source_url": string or null,
    "reason": "short explanation"
}}

EVIDENCE:
{evidence}
"""

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "openrouter/free",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0
        },
        timeout=(10, 90)
    )

    response.raise_for_status()
    response_data = response.json()
    model = response_data.get("model")
    content = response_data.get("choices", [{}])[0].get("message", {}).get("content")

    if not content:
        raise RuntimeError(f"OpenRouter returned empty content. Model: {model}")

    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content)

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"OpenRouter returned non-JSON content. Model: {model}. Response: {content[:500]}"
        )

    result["ai_model"] = model
    return result

def update_poll_status(numero_registro, result_status, status_path=STATUS_PATH, source_url=np.nan, source_type=np.nan, ai_model=np.nan, notes=np.nan):
    status_path = Path(status_path)
    status = pd.read_csv(status_path, encoding="utf-8", low_memory=False)

    if "attempt_count" not in status.columns:
        status["attempt_count"] = 0

    mask = status["numero_registro"].astype(str).str.strip() == str(numero_registro).strip()

    if not mask.any():
        print(f"{numero_registro} not found in poll_status.csv.")
        return

    status.loc[mask, "result_status"] = result_status
    status.loc[mask, "last_checked"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    status.loc[mask, "source_url"] = source_url
    status.loc[mask, "source_type"] = source_type
    status.loc[mask, "ai_model"] = ai_model
    status.loc[mask, "notes"] = notes

    status.to_csv(status_path, index=False, encoding="utf-8")
    print(f"{numero_registro}: status updated to {result_status}.")

def record_not_found(poll, status_path=STATUS_PATH, source_url=np.nan, source_type=np.nan, ai_model=np.nan, notes=np.nan):
    status_path = Path(status_path)
    status = pd.read_csv(status_path, encoding="utf-8", low_memory=False)

    if "attempt_count" not in status.columns:
        status["attempt_count"] = 0

    registro = str(poll["numero_registro"]).strip()
    mask = status["numero_registro"].astype(str).str.strip() == registro

    if not mask.any():
        print(f"{registro} not found in poll_status.csv.")
        return

    current_attempts = pd.to_numeric(status.loc[mask, "attempt_count"], errors="coerce").fillna(0)
    attempt_count = int(current_attempts.iloc[0]) + 1

    poll_date = pd.to_datetime(poll["data"], errors="coerce")
    today = pd.Timestamp.today().normalize()
    age_days = (today - poll_date.normalize()).days if pd.notna(poll_date) else 0

    result_status = "not_found"
    if age_days > 8 and attempt_count >= 3:
        result_status = "unresolved"
        unresolved_note = (
            f"Automatically marked unresolved after {attempt_count} unsuccessful attempts; "
            f"poll is {age_days} days old."
        )
        if pd.isna(notes) or not str(notes).strip():
            notes = unresolved_note
        else:
            notes = f"{notes} | {unresolved_note}"

    status.loc[mask, "attempt_count"] = attempt_count
    status.loc[mask, "result_status"] = result_status
    status.loc[mask, "last_checked"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    status.loc[mask, "source_url"] = source_url
    status.loc[mask, "source_type"] = source_type
    status.loc[mask, "ai_model"] = ai_model
    status.loc[mask, "notes"] = notes

    status.to_csv(status_path, index=False, encoding="utf-8")
    print(f"{registro}: status updated to {result_status} (unsuccessful attempts: {attempt_count}).")
    return result_status

def apply_ai_result(poll, ai_result, pages, data_path=DATA_DIR / "data.csv"):
    registro = str(poll["numero_registro"]).strip()
    ai_analysis = json.dumps(ai_result, ensure_ascii=False)

    model = ai_result.get("ai_model", np.nan)
    source_url = ai_result.get("source_url")
    found = bool(ai_result.get("found"))
    ai_status = str(ai_result.get("status", "")).strip().lower()

    if found:
        ai_status = "found"
    elif ai_status not in {"not_found", "cancelled"}:
        ai_status = "not_found"

    # 1. AI did not find the desired runoff result
    if not found:
        if ai_status == "not_found":
            record_not_found(poll, ai_model=model, notes=ai_analysis)
            print(f"{registro}: AI did not find a valid result.")
            return False

        # cancelled is terminal, so validate the supporting source
        source_page = next((page for page in pages if page.get("url") == source_url), None)

        if source_page is None:
            record_not_found(
                poll,
                ai_model=model,
                notes=f"AI claimed status={ai_status}, but returned an unknown source URL. AI analysis: {ai_analysis}"
            )
            print(f"{registro}: terminal AI status could not be validated; kept as retryable.")
            return False

        page_text = normalize_text(source_page.get("page_text", ""))
        if normalize_text(registro) not in page_text:
            record_not_found(
                poll,
                source_url=source_url,
                source_type="web",
                ai_model=model,
                notes=(
                    f"AI claimed status={ai_status}, but the exact registration was not found "
                    f"in the selected source. AI analysis: {ai_analysis}"
                )
            )
            print(f"{registro}: terminal AI status could not be validated; kept as retryable.")
            return False

        update_poll_status(
            registro,
            ai_status,
            source_url=source_url,
            source_type="web",
            ai_model=model,
            notes=ai_analysis
        )
        print(f"{registro}: classified as {ai_status}.")
        return False

    # 2. Validate percentages
    try:
        lula = float(ai_result["lula"])
        flavio = float(ai_result["flavio_bolsonaro"])
    except (TypeError, ValueError, KeyError):
        update_poll_status(
            registro,
            "manual_review",
            ai_model=model,
            notes=f"Invalid AI percentages. AI analysis: {ai_analysis}"
        )
        print(f"{registro}: invalid percentages returned by AI.")
        return False

    if not (0 <= lula <= 100 and 0 <= flavio <= 100):
        update_poll_status(
            registro,
            "manual_review",
            ai_model=model,
            notes=f"Percentages outside 0-100. AI analysis: {ai_analysis}"
        )
        print(f"{registro}: percentages outside valid range.")
        return False

    # 3. Source URL must be one of the pages supplied to the AI
    source_page = next((page for page in pages if page.get("url") == source_url), None)
    if source_page is None:
        update_poll_status(
            registro,
            "manual_review",
            ai_model=model,
            notes=f"AI returned an unknown source URL. AI analysis: {ai_analysis}"
        )
        print(f"{registro}: AI source URL was not among supplied pages.")
        return False

    # 4. Require the exact TSE registration in the selected source page
    page_text = normalize_text(source_page.get("page_text", ""))
    if normalize_text(registro) not in page_text:
        update_poll_status(
            registro,
            "manual_review",
            source_url=source_url,
            source_type="web",
            ai_model=model,
            notes=f"Exact registration not found in selected source page. AI analysis: {ai_analysis}"
        )
        print(f"{registro}: exact registration not found in source page. Sent to manual review.")
        return False

    # 5. Read data.csv byte-for-byte safely. Latin-1 maps every byte 1:1,
    # so mixed/legacy encodings cannot crash this step or corrupt untouched bytes.
    data_path = Path(data_path)
    with open(data_path, "r", encoding="latin1", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    data_encoding = "latin1"

    targets = {"LULA": lula, "FLAVIO BOLSONARO": flavio}
    candidate_rows = {"LULA": [], "FLAVIO BOLSONARO": []}

    for i, row in enumerate(rows):
        if str(row.get("numero_registro", "")).strip() != registro:
            continue

        candidate = normalize_text(row.get("nome_candidato", ""))
        if candidate == "LULA":
            candidate_rows["LULA"].append(i)
        elif candidate.startswith("FL") and "BOLSONARO" in candidate:
            candidate_rows["FLAVIO BOLSONARO"].append(i)

    if not candidate_rows["LULA"] or not candidate_rows["FLAVIO BOLSONARO"]:
        update_poll_status(
            registro,
            "manual_review",
            source_url=source_url,
            source_type="web",
            ai_model=model,
            notes=f"Candidate rows missing in data.csv. AI analysis: {ai_analysis}"
        )
        print(f"{registro}: candidate rows missing in data.csv.")
        return False

    # 6. Check existing values BEFORE writing anything
    for candidate, value in targets.items():
        for i in candidate_rows[candidate]:
            existing = str(rows[i].get("percentual", "")).strip()
            if existing and existing.lower() not in {"nan", "none"}:
                try:
                    existing_value = float(existing.replace(",", "."))
                except ValueError:
                    update_poll_status(
                        registro,
                        "manual_review",
                        source_url=source_url,
                        source_type="web",
                        ai_model=model,
                        notes=f"Existing percentage could not be parsed. AI analysis: {ai_analysis}"
                    )
                    return False

                if abs(existing_value - value) > 1e-9:
                    update_poll_status(
                        registro,
                        "conflict",
                        source_url=source_url,
                        source_type="web",
                        ai_model=model,
                        notes=f"AI result conflicts with existing data. AI analysis: {ai_analysis}"
                    )
                    print(f"{registro}: conflict for {candidate}: data.csv={existing_value}, AI={value}")
                    return False

    # 7. Fill ONLY blank values
    changes = 0
    for candidate, value in targets.items():
        for i in candidate_rows[candidate]:
            existing = str(rows[i].get("percentual", "")).strip()
            if not existing or existing.lower() in {"nan", "none"}:
                rows[i]["percentual"] = f"{value:g}"
                changes += 1

    # 8. Write safely through a temporary file
    if changes > 0:
        temp_path = data_path.with_name("data.tmp.csv")
        with open(temp_path, "w", encoding=data_encoding, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(data_path)

    # 9. Record successful AI analysis
    update_poll_status(
        registro,
        "found",
        source_url=source_url,
        source_type="web",
        ai_model=model,
        notes=ai_analysis
    )

    print(f"{registro}: validated successfully.")
    print(f"{registro}: filled {changes} missing value(s) in data.csv.")
    return True

if __name__ == "__main__":
    # Safety limit for AI calls in a single run
    MAX_AI_CALLS_PER_RUN = 40

    ai_calls = 0
    processed = 0

    # 1. Download latest TSE data
    tse_path = download_tse_data()

    # 2. Clean/filter 2026 presidential polls from institutes of interest
    polls_2026 = clean_polls(tse_path, "2026-08-03")

    # 3. Add newly registered polls to data.csv
    new_rows = add_new_polls(polls_2026, DATA_DIR / "data.csv")

    # 4. Find polls that still have missing results
    pending = find_pending_polls(DATA_DIR / "data.csv")

    print(f"\nPending polls: {len(pending)}")

    # 5. Synchronize poll_status.csv
    status = sync_poll_status(pending)

    # 6. Build queue of polls that should be searched now
    search_queue = get_polls_to_search(pending, status)

    print(f"Polls to search now: {len(search_queue)}")

    if search_queue.empty:
        print("\nNo polls need to be searched right now.")

    else:
        # 7. Process every poll currently eligible for search
        for i, (_, poll) in enumerate(search_queue.iterrows(), start=1):

            print("\n" + "=" * 80)
            print(
                f"Processing {i}/{len(search_queue)}: "
                f"{poll['numero_registro']} - {poll['instituto']}"
            )
            print("=" * 80)

            try:
                # 8. Search the web
                search_results = search_poll_web(poll)

                # No search results
                if not search_results:
                    record_not_found(
                        poll,
                        notes="No usable web search results found."
                    )

                    processed += 1
                    time.sleep(2)
                    continue

                # 9. Open the best search results
                pages = fetch_top_pages(search_results, top_n=4)

                print(f"\nPages successfully extracted: {len(pages)}")

                for j, page in enumerate(pages, start=1):
                    print(f"\nPage {j}")
                    print(f"Score: {page['score']}")
                    print(f"Title: {page['title']}")
                    print(f"URL: {page['url']}")
                    print(f"Text length: {len(page['page_text']):,} characters")

                # Search results existed, but no page could be opened
                if not pages:
                    update_poll_status(
                        poll["numero_registro"],
                        "pending",
                        notes="Search results were found, but no page text could be extracted."
                    )

                    processed += 1
                    time.sleep(2)
                    continue

                # 10. Safety stop before exceeding our own AI-call limit
                if ai_calls >= MAX_AI_CALLS_PER_RUN:
                    print(
                        f"\nAI safety limit reached "
                        f"({MAX_AI_CALLS_PER_RUN} calls)."
                    )
                    print("Stopping this run. Remaining polls stay pending.")
                    break

                # 11. Send pages to AI
                ai_result = analyze_pages_with_ai(poll, pages)
                ai_calls += 1

                print("\nAI analysis:")
                print(
                    json.dumps(
                        ai_result,
                        indent=2,
                        ensure_ascii=False
                    )
                )

                # 12. Validate and, if safe, write result to data.csv
                apply_ai_result(
                    poll,
                    ai_result,
                    pages
                )

                processed += 1

            except Exception as e:
                print(
                    f"\nTechnical error while processing "
                    f"{poll['numero_registro']}: {e}"
                )

                # Keep it retryable rather than falsely marking it not_found
                update_poll_status(
                    poll["numero_registro"],
                    "pending",
                    notes=f"Technical error: {e}"
                )

            # Small pause to avoid hammering search engines
            time.sleep(2)

    print("\n" + "=" * 80)
    print("RUN SUMMARY")
    print("=" * 80)
    print(f"Polls processed: {processed}")
    print(f"AI requests used: {ai_calls}")
    print(f"Polls remaining in this queue: {max(0, len(search_queue) - processed)}")