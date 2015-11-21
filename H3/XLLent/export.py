__author__ = 'Emmanuel'

import xlsxwriter


def bases_writer(bases, timestamp):
    filename = _("Bases exported {time}.xlsx").format(time=timestamp)
    wb = xlsxwriter.Workbook(filename)
    ws = wb.add_worksheet(_("Bases"))

    row_no = 0
    widths = [0, 0, 0, 0, 0, 0, 0, 0]

    dates = wb.add_format({'num_format': 'd mmm yyyy'})

    for base in bases:
        ws.write(row_no, 0, base.code)
        if len(base.code) > widths[0]:
            widths[0] = len(base.code)
        ws.write(row_no, 1, base.identifier)
        if len(base.identifier) > widths[1]:
            widths[1] = len(base.identifier)
        ws.write(row_no, 2, base.parent)
        if len(base.parent) > widths[2]:
            widths[2] = len(base.parent)
        ws.write(row_no, 3, base.full_name)
        if len(base.full_name) > widths[3]:
            widths[3] = len(base.full_name)
        ws.write(row_no, 4, base.opened_date, dates)
        ws.write(row_no, 5, base.closed_date, dates)
        ws.write(row_no, 6, base.country)
        if len(base.country) > widths[6]:
            widths[6] = len(base.country)
        ws.write(row_no, 7, base.time_zone)
        if len(base.time_zone) > widths[7]:
            widths[7] = len(base.time_zone)
        row_no += 1

    for index in range(0, len(widths)):
        ws.set_column(index, index, widths[index])

    ws.set_column(4, 5, 12)

    wb.close()
    return filename
