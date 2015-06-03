__author__ = 'Man'

import ConfigParser
import logging

from AlchemyLocal import H3AlchemyLocalDB
from AlchemyRemote import H3AlchemyRemoteDB
import AlchemyClassDefs as Acd


logger = logging.getLogger(__name__)


class H3AlchemyCore():
    """
    This is the central module for data manipulation. Now relies on SQLAlchemy's ORM.
    """
    def __init__(self):
        """
        Creates the values and objects used throughout a work session.
        """

        self.local_db = None
        self.remote_db = None
        self.user_state = None

        self.current_user = None
        self.full_name = None
        self.current_job = None
        self.job_desc = None
        self.base_code = None
        self.base_name = None
        self.base_visibility = []

        self.options = ConfigParser.ConfigParser()

    def ready(self):
        """
        Checks that options are set for local and remote DB locations plus a current user;
        If local DB is valid (ping returns true), will try to update that user's details and return True.
        """
        if self.options.read('config.txt'):
            if (self.options.has_option('DB Locations', 'local') and
               self.options.has_option('DB Locations', 'remote')):
                temp_local_db_location = self.options.get('DB Locations', 'local')
                temp_remote_db_location = self.options.get('DB Locations', 'remote')
                self.remote_db = H3AlchemyRemoteDB(self, temp_remote_db_location)
                if self.ping_local(temp_local_db_location) == 1:
                    self.local_db = H3AlchemyLocalDB(self, temp_local_db_location)
                    if self.options.has_option('H3 Options', 'current user'):
                        username = self.options.get('H3 Options', 'current user')
                        self.current_user = self.local_db.get_user(username)
                        if self.current_user:
                            return True

    def setup_databases(self, local, remote):
        """
        Creates the local and remote DB instances and saves their location to the config file.
        Called from the setup wizard.
        """
        self.local_db = H3AlchemyLocalDB(self, local)
        self.local_db.init_public_tables()
        self.download_hierarchy()
        self.remote_db = H3AlchemyRemoteDB(self, remote)
        if not self.options.has_section('DB Locations'):
            self.options.add_section('DB Locations')
        self.options.set('DB Locations', 'local', local)
        self.options.set('DB Locations', 'remote', remote)
        self.options.write(open('config.txt', 'wb'))

    def find_user(self, username):
        """
        Called from the setup process to find out the status of the "new user" credentials provided.
        :param username: the username to set up.
        """
        self.current_user = None
        self.current_user = self.local_db.get_user(username)
        if self.current_user:
            self.user_state = "local"
        else:
            self.current_user = self.remote_db.get_user(username)
            if self.current_user:
                if self.remote_db.login(username, username + 'YOUPIE'):
                    self.user_state = "new"
                else:
                    self.user_state = "remote"
        if self.current_user:
            self.update_user_details()

    def remote_pw_change(self, username, old_pass, new_pass):
        self.remote_db.login(username, old_pass)
        if self.remote_db.update_pass(username, old_pass, new_pass):
            logger.debug(_("Initial password setup successful for user {login}")
                         .format(login=username))
        else:
            logger.error(_("Couldn't change password in remote for user {login}")
                         .format(login=username))

    def download_user(self, user):
        """
        Called on finding a user which isn't in the local DB but IS in the remote.
        Downloads the user's personal and career info.
        """
        logger.debug(_("User {login} downloaded into local DB")
                     .format(login=user.login))
        jobs = self.remote_db.get_jobs(user.login)
        if jobs:
            self.local_db.put([user, ])
            self.local_db.put(jobs)
            logger.debug(ngettext("User {login}'s {number} job downloaded into local DB",
                                  "User {login}'s {number} jobs downloaded into local DB",
                                  len(jobs))
                         .format(login=user.login, number=len(jobs)))
        else:
            logger.warning(_("User {login} doesn't have any jobs !")
                           .format(login=user.login))

    def update_user_details(self):
        """
        Update the current user's personal and career details in the live core and in the config file
        :return:
        """
        self.full_name = _("{first} {last}") \
            .format(first=self.current_user.first_name,
                    last=self.current_user.last_name)

        if not self.options.has_section('H3 Options'):
            self.options.add_section('H3 Options')
        self.options.set('H3 Options', 'current user', self.current_user.login)

        if self.user_state == "local":
            self.current_job = self.local_db.get_current_job(self.current_user)
        else:
            self.current_job = self.remote_db.get_current_job(self.current_user)

        if self.current_job:
            self.job_desc = self.current_job.job_title
            self.base_code = self.current_job.base
            self.base_name = self.local_db.get_base_fullname(self.base_code)
            self.update_base_visibility(self.base_code)
            self.options.set('H3 Options', 'Root Base', self.base_code)

            local_bases_list = self.local_db.get_local_bases()
            unique_bases = []
            for base in local_bases_list:
                unique_bases.append(base.id)  # TODO: will that work with named tuple access ? (.id)

            if unicode(self.current_job.base) not in unique_bases:
                self.user_state = "new_base"
                logger.info(_("User {name} is currently affected to {base}, which isn't part of the local DB.")
                            .format(name=self.current_user.login, base=self.current_job.base))
        else:
            self.user_state = "no_job"
            logger.info(_("User {name} doesn't currently have a contract")
                        .format(name=self.current_user.login))

        self.options.write(open('config.txt', 'wb'))

    def update_base_visibility(self, base_name):
        """
        Queries local database for the organisational tree, then walks it to extract a list of sub-bases
        :param base_name: root of the extracted subtree
        """
        org_table = self.local_db.read_table(Acd.WorkBase)
        self.base_visibility.append(base_name)
        tree_row = [base_name]
        next_row = list()
        while tree_row:
            for base in tree_row:
                for record in org_table:
                    if record.parent == base:
                        next_row.append(record.id)
                        self.base_visibility.append(record.id)
            tree_row = next_row
            next_row = list()

    def local_login(self, username, password):
        """
        Logs in at app-level, in the local DB.
        then sets the core's current user.
        :return: True if login succeeded, False if failed
        """
        logged_user = self.local_db.login(username, password)
        if logged_user:
            self.current_user = logged_user
            self.update_user_details()
            return True
        else:
            return False

    def download_hierarchy(self):
        """
        First table to be populated entirely from remote as clients need to know the worldwide structure
        (For users who have had a worldwide career !)
        """
        # TODO: replace that with a proper sync
        org_table_data = self.remote_db.read_table(Acd.WorkBase)
        self.local_db.put(org_table_data)

    def remote_create_user(self, login, password, first_name, last_name):
        """
        Builds the user object and sends it to the remote engine for app- and SQL-level setup.
        :param login:
        :param password:
        :param first_name:
        :param last_name:
        :return:
        """
        user = Acd.User(login=login, pw_hash=password, first_name=first_name,
                        last_name=last_name)
        self.remote_db.create_user(user)

    def remote_create_base(self, base, parent, full):
        """
        Builds the user object and sends it to the remote engine for app- and SQL-level setup.
        :param base:
        :param parent:
        :param full:
        :return:
        """
        base = Acd.WorkBase(id=base, parent=parent, full_name=full)
        self.remote_db.create_base(base)

    def get_visible_users(self):
        """
        Returns the users in the remote user list that belong to the visible bases,
        e.g the ones belonging to the install base or below
        :return:
        """
        return self.remote_db.get_visible_users(self.base_visibility)

    def ping_local(self, path):
        """
        Checks if the local DB path points to a H3 database
        :param path:
        :return:
        """
        if path == "":
            return 0  # open() doesn't error out on an empty filename
        try:
            open(path)  # Try to open location
            temp_local_db = H3AlchemyLocalDB(self, path)
            if temp_local_db.has_a_base():
                return 1  # This is a H3 DB
            else:
                return 0  # This is NOT a H3 DB, file will not be written to
        except IOError:
            return -1  # No file here, OK to create

    def ping_remote(self, address):
        temp_remote_db = H3AlchemyRemoteDB(self, address)
        if temp_remote_db.login('reader', 'weak'):
            return 1
        else:
            return 0

    def init_remote(self, location):
        self.remote_db = H3AlchemyRemoteDB(None, location)
        self.remote_db.initialize()