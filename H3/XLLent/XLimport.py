__author__ = 'Emmanuel'

import openpyxl


def data_reader(filename):
    wb = openpyxl.load_workbook(filename, read_only=True)
    data_ws = wb["Data"]

    data = list()
    for row in data_ws.rows:
        individual_row = list()
        for cell in row:
            individual_row.append(cell.value)
        data.append(individual_row)

    del wb

    return data
