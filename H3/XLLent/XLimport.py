__author__ = 'Emmanuel'

import datetime
import locale

import openpyxl
import openpyxl.comments
import openpyxl.utils
import babel
import babel.dates

from ..core import AlchemyClassDefs as Acd


class BasesReader:
    def __init__(self, filename):
        self.wb = openpyxl.load_workbook(filename)

        self.cell_range = self.wb.get_named_range("YoupiTable")
        range_string = self.cell_range.destinations[0][1]

        self.table = list()

        for row in self.wb.active.iter_rows(range_string):
            self.table.append(row)

        self.current_row_no = 0
        # parents_ws = self.wb.get_sheet_by_name("Data")
        # parents_data = parents_ws.range("A1:B20")
        #
        # self.parents_dict = dict()
        # for line in parents_data:
        #     self.parents_dict.update({line[1].value: line[0].value})

    def feed_line(self):
        if self.current_row_no >= len(self.table):
            return False
        else:
            row = self.table[self.current_row_no]
            # noinspection PyArgumentList
            new_base = Acd.WorkBase(base="BASE-1",
                                    period="PERMANENT",
                                    identifier=row[0].value,
                                    full_name=row[2].value,
                                    opened_date=row[3].value,
                                    closed_date=row[4].value,
                                    country=row[5].value,
                                    time_zone=row[6].value)
            return new_base

    def write_line_result(self, result):
        comment = openpyxl.comments.Comment("", "")
        if result == "ERR":
            comment = openpyxl.comments.Comment(_("Import failed"), _("H3 Excel import module"))
        elif result == "OK":
            comment = openpyxl.comments.Comment(_("Imported successfully"), _("H3 Excel import module"))
        self.table[self.current_row_no][0].comment = comment

    def advance(self):
        self.current_row_no += 1

    def save(self):
        loc = babel.Locale.parse(locale.getdefaultlocale()[0], "_")
        timestamp = babel.dates.format_datetime(datetime.datetime.now(), locale=loc).replace('/', '-').replace(':', '.')
        name = "Import log {timestamp}.xlsx".format(timestamp=timestamp)
        self.wb.save(name)
        return name
