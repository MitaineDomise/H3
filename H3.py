__author__ = 'Man'

import GUI.GUIMain
import gettext
import logging

gettext.install("H3", localedir="GUI/lang", unicode=True, names=['ngettext', ])
logging.basicConfig(filename='log.txt', filemode='w', level=logging.DEBUG)

if __name__ == '__main__':
    GUI.GUIMain.run()

