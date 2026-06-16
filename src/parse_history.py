"""Parse the case-history HTML (viewHistory `data_list`) into:
  - CaseDetail: status, nature of disposal (win/loss signal), decision date, judge
  - OrderRow list: final orders/judgements with the displayPdf() args needed to
    fetch the actual PDF.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from parse_advocate import split_js_args


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip())


@dataclass
class OrderRow:
    order_number: str
    order_date: str
    label: str
    # displayPdf(normal_v, case_val, court_code, filename, appFlag)
    normal_v: str = ""
    case_val: str = ""
    court_code: str = ""
    filename: str = ""
    app_flag: str = ""


@dataclass
class CaseDetail:
    case_status: str = ""
    nature_of_disposal: str = ""
    decision_date: str = ""
    filing_date: str = ""
    judge: str = ""
    orders: list[OrderRow] = field(default_factory=list)


def _row_label_value(tr) -> tuple[str, str]:
    cells = tr.find_all(["th", "td"])
    if len(cells) < 2:
        return "", ""
    return _clean(cells[0].get_text()), _clean(cells[-1].get_text())


def parse_case_history(html: str) -> CaseDetail:
    soup = BeautifulSoup(html, "lxml")
    detail = CaseDetail()

    status_table = soup.find("table", class_=re.compile(r"case_status_table"))
    if status_table:
        for tr in status_table.find_all("tr"):
            label, value = _row_label_value(tr)
            low = label.lower()
            if "nature of disposal" in low:
                detail.nature_of_disposal = value
            elif "case status" in low:
                detail.case_status = value
            elif "decision date" in low:
                detail.decision_date = value
            elif "judge" in low:
                detail.judge = value

    details_table = soup.find("table", class_=re.compile(r"case_details_table"))
    if details_table:
        for tr in details_table.find_all("tr"):
            label, value = _row_label_value(tr)
            if "filing date" in label.lower():
                detail.filing_date = value

    order_table = soup.find("table", class_=re.compile(r"order_table"))
    if order_table:
        for tr in order_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            order_number = _clean(tds[0].get_text())
            order_date = _clean(tds[1].get_text())
            link = tr.find("a")
            onclick = (link.get("onclick") if link else "") or ""
            label = _clean(link.get_text()) if link else ""
            o = OrderRow(order_number=order_number, order_date=order_date, label=label)
            m = re.search(r"displayPdf\(([^)]*)\)", onclick)
            if m:
                a = split_js_args(m.group(1))
                a += [""] * (5 - len(a))
                o.normal_v, o.case_val, o.court_code, o.filename, o.app_flag = a[:5]
            detail.orders.append(o)

    return detail
