__author__ = 'Emmanuel'

import datetime
import locale

import xlsxwriter
import xlsxwriter.utility
import babel
import babel.dates


def bases_writer(bases):
    # First get a babel Locale object
    loc = babel.Locale.parse(locale.getdefaultlocale()[0], "_")
    # Make the timestamp for the filename both locally correct and windows-compatible
    timestamp = babel.dates.format_datetime(datetime.datetime.now(), locale=loc).replace('/', '-').replace(':', '.')

    filename = _("Bases exported {time}.xlsx").format(time=timestamp)
    wb = xlsxwriter.Workbook(filename)
    ws = wb.add_worksheet("Bases")
    data_ws = wb.add_worksheet("Data")

    title = _("\nH3 Export Bases")
    date_time = _("Exported &D at &T")
    page_count = _("Page &P of &N")
    ws.set_header('&L&G&C&30{title}&R{date_time}\n{page_count}'
                  .format(title=title, date_time=date_time, page_count=page_count),
                  {'image_left': 'H3\GUI\QtDesigns\images\H3big.png'})

    ws.set_margins(top=1.6)

    # Format the excel dates to the locale-appropriate representation
    dates = wb.add_format({'num_format': loc.date_formats["short"].pattern})

    row_no = 0

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
        widths.append(len(header_row[i]))
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

    j = 0
    for base in bases:
        data_ws.write_string(j, 0, base.code)
        data_ws.write_string(j, 1, base.identifier)
        j += 1

    wb.define_name('DataTable', '=Data!$A:$B')

    ws.add_table(0, 0, len(table_data), len(row) - 1,
                 {'data': table_data,
                  'name': "Bases",
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

    # Special cases for dates : second writing pass and fixed width.
    # Use this pass to overwrite parent with a formula pulling the base name
    for line in range(1, len(table_data) + 1):
        ws.write(line, 3, table_data[line - 1][3], dates)
        ws.write(line, 4, table_data[line - 1][4], dates)
        formula = '=VLOOKUP("{parent_code}",DataTable,2,FALSE)'.format(parent_code=table_data[line - 1][1])
        ws.write_formula(line, 1, formula)
        # Completely excessive data validation
        # ws.data_validation(line, 1, line, 1, {'validate': 'list', 'source': '=$A$2:{cell_before}'
        #                    .format(cell_before=xlsxwriter.utility.xl_rowcol_to_cell(line-1, 0, True, True))})
    widths[3] = len(header_row[3])
    widths[4] = len(header_row[4])

    # Calculate column widths
    for line in table_data:
        for col in range(0, len(line)):
            if col not in [1, 3, 4] and len(line[col]) > widths[col]:
                widths[col] = len(line[col])

    # Since we used base identifiers for the parent column, copy that width if necessary
    if widths[0] > widths[1]:
        widths[1] = widths[0]

    for index in range(0, len(widths)):
        ws.set_column(index, index, widths[index])

    ws.print_area(0, 0, len(table_data) - 1, len(header_row) - 1)
    ws.fit_to_pages(1, 0)

    data_ws.hide()

    wb.close()
    return filename
