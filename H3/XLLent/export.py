__author__ = 'Emmanuel'

import datetime
import locale

import xlsxwriter
import babel
import babel.dates


def bases_writer(bases):
    # First get a babel Locale object
    loc = babel.Locale.parse(locale.getdefaultlocale()[0], "_")
    # Make the timestamp for the filename both locally correct and windows-compatible
    timestamp = babel.dates.format_datetime(datetime.datetime.now(), locale=loc).replace('/', '-').replace(':', '.')

    filename = _("Bases exported {time}.xlsx").format(time=timestamp)
    wb = xlsxwriter.Workbook(filename)
    ws = wb.add_worksheet(_("Bases"))

    title = _("\nH3 Export Bases")
    date_time = _("Exported &D at &T")
    page_count = _("Page &P of &N")
    ws.set_header('&L&G&C&30{title}&R{date_time}\n{page_count}'
                  .format(title=title, date_time=date_time, page_count=page_count),
                  {'image_left': 'H3\GUI\QtDesigns\images\H3big.png'})

    ws.set_margins(top=2)

    # Format the excel dates to the locale-appropriate representation
    dates = wb.add_format({'num_format': loc.date_formats["short"].pattern})

    row_no = 0

    # TODO: pull parent description out of a hidden data worksheet
    table_data = list()

    header_row = [_("Identifier"),
                  _("Parent"),
                  _("Full Name"),
                  _("Opening date"),
                  _("Closing date"),
                  _("Country code"),
                  _("Time zone")]

    widths = list()
    for i in range(0, len(header_row)):
        widths.append(0)
    row = list()
    for base in bases:
        row = list()
        row.append(base.identifier)
        row.append(base.parent)
        row.append(base.full_name)
        row.append(base.opened_date)
        row.append(base.closed_date)
        row.append(base.country)
        row.append(base.time_zone)
        table_data.append(row)
        row_no += 1

    ws.add_table(0, 0, len(table_data), len(row) - 1,
                 {'data': table_data,
                  'autofilter': False,
                  'style': 'Table Style Medium 15',
                  'columns':
                      [{'header': header_row[0]},
                       {'header': header_row[1]},
                       {'header': header_row[2]},
                       {'header': header_row[3]},
                       {'header': header_row[4]},
                       {'header': header_row[5]},
                       {'header': header_row[6]}]})

    # Special cases for dates : second writing pass and fixed width
    for line in range(1, len(table_data) + 1):
        ws.write(line, 3, table_data[line - 1][3], dates)
        ws.write(line, 4, table_data[line - 1][4], dates)
    widths[3] = len(header_row[3])
    widths[4] = len(header_row[4])

    # Calculate column widths
    table_data.insert(0, header_row)
    for line in table_data:
        for col in range(0, len(line)):
            if col != 3 and col != 4 and len(line[col]) > widths[col]:
                widths[col] = len(line[col])

    for index in range(0, len(widths)):
        ws.set_column(index, index, widths[index])

    ws.print_area(0, 0, len(table_data) - 1, len(header_row) - 1)
    ws.fit_to_pages(1, 0)

    wb.close()
    return filename
