"""Parse the advocate-search result HTML (adv_data) into structured rows.

bharat-courts' parse_case_status_html keeps only case number + parties + CNR.
We need more: the full viewHistory() arguments (internal case_no, court_code)
to fetch history/PDFs, the advocate-name column (for seed harvesting), and the
establishment each case belongs to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup


def split_js_args(arg_str: str) -> list[str]:
    """Split a JS call's argument list on top-level commas, stripping quotes."""
    parts = re.split(r",(?=(?:[^']*'[^']*')*[^']*$)", arg_str)
    return [p.strip().strip("'\"") for p in parts]


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip())


def _split_parties(td) -> tuple[str, str]:
    # The portal emits malformed "Pet<br>Vs</br>Resp" (the </br> becomes a 2nd
    # <br>), so split on the literal "Vs" delimiter (capital V). Names rarely
    # contain a capital "Vs", so this is safe and also handles glued "PatilVsThe".
    for br in td.find_all("br"):
        br.replace_with(" ")
    text = _clean(td.get_text(" "))
    parts = re.split(r"Vs\.?", text, maxsplit=1)
    if len(parts) == 2:
        return _clean(parts[0]), _clean(parts[1])
    return text, ""


def _split_advocates(td) -> list[str]:
    for br in td.find_all("br"):
        br.replace_with("\n")
    raw = td.get_text("\n")
    names = [_clean(x) for x in raw.split("\n")]
    return [n for n in names if n]


@dataclass
class AdvocateCaseRow:
    serial: str
    establishment: str
    case_number_full: str
    petitioner: str
    respondent: str
    advocates: list[str] = field(default_factory=list)
    # viewHistory(case_no, cino, court_code, hideparty, search_flag, state, dist, complex, search_by)
    case_no: str = ""
    cino: str = ""          # CNR (unique case id)
    court_code: str = ""    # establishment court code (1/2/3)
    state_code: str = ""
    dist_code: str = ""
    complex_code: str = ""
    search_flag: str = "CScaseNumber"
    search_by: str = "CSAdvName"

    @property
    def case_type(self) -> str:
        return self.case_number_full.rsplit("/", 2)[0] if "/" in self.case_number_full else self.case_number_full

    @property
    def year(self) -> str:
        bits = self.case_number_full.rsplit("/", 2)
        return bits[-1] if len(bits) == 3 else ""

    @property
    def registration_number(self) -> str:
        bits = self.case_number_full.rsplit("/", 2)
        return bits[-2] if len(bits) == 3 else ""


def parse_advocate_results(html: str) -> list[AdvocateCaseRow]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="dispTable") or soup.find("table")
    if not table:
        return []

    rows: list[AdvocateCaseRow] = []
    current_establishment = ""
    for tr in table.find_all("tr"):
        th = tr.find("th")
        if th is not None and th.get("colspan"):
            current_establishment = _clean(th.get_text())
            continue
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue

        serial = _clean(tds[0].get_text())
        case_number_full = _clean(tds[1].get_text())
        petitioner, respondent = _split_parties(tds[2])
        advocates = _split_advocates(tds[3])

        case_no = cino = court_code = state = dist = cmplx = ""
        search_flag, search_by = "CScaseNumber", "CSAdvName"
        link = tds[4].find("a")
        onclick = (link.get("onclick") if link else "") or ""
        m = re.search(r"viewHistory\(([^)]*)\)", onclick)
        if m:
            a = split_js_args(m.group(1))
            a += [""] * (9 - len(a))
            case_no, cino, court_code, _hideparty, search_flag, state, dist, cmplx, search_by = a[:9]

        rows.append(
            AdvocateCaseRow(
                serial=serial,
                establishment=current_establishment,
                case_number_full=case_number_full,
                petitioner=petitioner,
                respondent=respondent,
                advocates=advocates,
                case_no=case_no,
                cino=cino,
                court_code=court_code,
                state_code=state,
                dist_code=dist,
                complex_code=cmplx,
                search_flag=search_flag,
                search_by=search_by,
            )
        )
    return rows
