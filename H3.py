__author__ = 'Man'

import gettext
import logging
import argparse

import GUI.GUIMain


gettext.install("H3", localedir="GUI/lang", unicode=True, names=['ngettext', ])
logging.basicConfig(filename='log.txt', filemode='w', level=logging.DEBUG)

parser = argparse.ArgumentParser()
parser.add_argument("--init_remote",
                    help=_("Format the remote DB with the initial table structure."))
parser.add_argument("--nuke_remote",
                    help=_("DELETES the remote DB and the default user roles."))
parser.add_argument("--password",
                    help=_("Provide the master password to the remote DB."))
args = parser.parse_args()


if __name__ == '__main__':
    if args.init_remote:
        GUI.GUIMain.init_remote(args.init_remote, args.password)
    elif args.nuke_remote:
        GUI.GUIMain.nuke_remote(args.nuke_remote, args.password)
    else:
        GUI.GUIMain.run()

