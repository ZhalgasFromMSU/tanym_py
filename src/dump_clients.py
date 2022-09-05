import os
from openpyxl import Workbook

from .models import DatabaseConnector
from .dialogue_texts import PROBLEM_TYPES_STR

def dump_db(db: DatabaseConnector):
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Date"
    ws["B1"] = "City"
    ws["C1"] = "Sex"
    ws["D1"] = "Age"
    ws["E1"] = "Type"
    ws["F1"] = "Score"
    ws["G1"] = "Review"

    idx = 2
    for client in db.list_clients():
        ws["A{}".format(idx)] = client.date.strftime("%d/%m/%Y")
        ws["B{}".format(idx)] = client.city
        ws["C{}".format(idx)] = client.sex
        ws["D{}".format(idx)] = client.age
        ws["E{}".format(idx)] = PROBLEM_TYPES_STR[int(client.pr_type)]
        ws["F{}".format(idx)] = client.score
        ws["G{}".format(idx)] = client.review
        idx += 1

    if os.path.exists("data.xlsx"):
        os.remove("data.xlsx")
    wb.save("data.xlsx")
    return "data.xlsx"
