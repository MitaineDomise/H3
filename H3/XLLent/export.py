__author__ = 'Emmanuel'

import datetime
import locale

import xlsxwriter
import babel
import babel.dates


def bases_writer(bases):
    # First get a babel Locale object
    loc = babel.Locale.parse(locale.getdefaultlocale()[0], "_")
    # Make the timestamp for the filenameboth locally correct and windows-compatible
    timestamp = babel.dates.format_datetime(datetime.datetime.now(), locale=loc).replace('/', '-').replace(':', '.')

    filename = _("Bases exported {time}.xlsx").format(time=timestamp)
    wb = xlsxwriter.Workbook(filename)
    ws = wb.add_worksheet(_("Bases"))

    row_no = 0
    widths = [0, 0, 0, 0, 0, 0, 0, 0]

    # Format the excel dates to the proper "medium" representation
    dates = wb.add_format({'num_format': loc.date_formats["long"].pattern})

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

    # Autofit for dates is difficult
    ws.set_column(4, 5, 12)

    wb.close()
    return filename
