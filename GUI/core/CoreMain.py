# coding: utf-8
__author__ = 'Man'
import hashlib
import gettext

import localdb
import remotedb


_ = gettext.gettext


class H3core():
    """
    This is the central module for pure data manipulation. Shouldn't be used a lot as most data will be
    processed with SQL in the local and remote databases. Serves as glue code if GUI or DB interfaces have to be changed
    """

    Messages = {"user_data_dl_fail": _("Error when downloading user info [core]"),
                "no_new_user_slot": _("Creation of that user hasn't been planned"),
                "remote_login_failed": _("Couldn't log in to remote database"),
                "local_login_failed": _("Couldn't log in to local database")
                }

    def __init__(self, parent):
        self.GuiParent = parent
        self.local_db = localdb.LocalDBMainV1.H3SQLiteLocalDB(self)
        self.remote_db = remotedb.RemoteDBMain.H3PostGreRemoteDB(self)
        self.user_first_name = None
        self.user_last_name = None
        self.user_job = None
        self.user_home_base = None
        self.user_bases = list()

    def local_login(self, user, password):
        """ This hashes the password like PostGreSQL does and gets the user info from the local table.
        """
        hashed_pass = 'md5' + hashlib.md5(password + user).hexdigest()
        if self.local_db.login(user, hashed_pass):
            self.update_user_details(user)
            return 1

    def update_user_details(self, username):
        user_details = self.local_db.read_user_details(username)
        self.user_first_name = user_details[0]
        self.user_last_name = user_details[1]
        self.user_job = user_details[2]
        self.user_home_base = user_details[3]
        org_table = self.local_db.read_hierarchy()
        tree_row = ['NRB', ]
        next_row = list()
        while tree_row:
            for base in tree_row:
                for record in org_table:
                    if record[1] == base:
                        next_row.append(record[0])
                        self.user_bases.append(record[0])
            tree_row = next_row
            next_row = list()
        print self.user_bases


    def set_server_address(self, address):
        self.remote_db.server_address = address

    def new_user(self, user, password):
        """
        Connects to remoteDB and checks the user has been marked as waiting to be set up with a magic password.
        then grabs public and user-specific tables.

        """
        if self.remote_db.first_connection(user):
            hashed_pass = 'md5' + hashlib.md5(password + user).hexdigest()
            if self.remote_db.update_pass(user, password, hashed_pass):
                user_line = self.remote_db.get_user_data(user)
                if user_line:
                    self.local_db.update_users(user_line)
                    self.local_db.commit()
                    hierarchy_dump = self.remote_db.grab_table('hierarchy')
                    if hierarchy_dump:
                        self.local_db.update_hierarchy(hierarchy_dump)
                        return 1
                    else:
                        pass
                        # couldn't grab hierarchy from remote
                else:
                    pass
                    # couldn't get user data from remote
            else:
                pass
                # couldn't change password in remote
        else:
            pass
            # couldn't login to remote with temp password