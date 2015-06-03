__author__ = 'Man'

import gettext
import logging
import argparse

import GUI.GUIMain


gettext.install("H3", localedir="GUI/lang", unicode=True, names=['ngettext', ])
logging.basicConfig(filename='log.txt', filemode='w', level=logging.DEBUG)

parser = argparse.ArgumentParser()
parser.add_argument("--init_remote",
                    help="Format the remote DB with the initial table structure.")
args = parser.parse_args()


if __name__ == '__main__':
    if args.init_remote:
        GUI.GUIMain.init_remote(args.init_remote)
    else:
        GUI.GUIMain.run()

