__author__ = 'Man'

import configparser
import logging
import datetime

from . import AlchemyLocal, AlchemyRemote
from . import AlchemyClassDefs as Acd

logger = logging.getLogger(__name__)


class H3AlchemyCore:
    """
    This is the central module for data manipulation. Now relies on SQLAlchemy's ORM.
    """
    def __init__(self):
        """
        Creates the values and objects used throughout a work session.
        """

        self.local_db = AlchemyLocal.H3AlchemyLocalDB(None)
        self.remote_db = AlchemyRemote.H3AlchemyRemoteDB(None)
        self.user_state = ""

        self.current_job_contract = Acd.JobContract()
        self.base_visibility = []

        self.contract_actions = list()
        self.delegations = list()

        self.language = "EN_UK"

        self.options = configparser.ConfigParser()

    # General utility functions

    @staticmethod
    def ping_remote(address):
        temp_remote_db = AlchemyRemote.H3AlchemyRemoteDB(address)
        if temp_remote_db.login('reader', 'weak'):
            return 1
        else:
            return 0

    @staticmethod
    def init_remote(location, password):
        new_db = AlchemyRemote.H3AlchemyRemoteDB(location)
        new_db.master_login('postgres', password)
        logger.debug(_("Connected with master DB credentials"))
        new_db.initialize(password)

    @staticmethod
    def nuke_remote(location, password):
        target_db = AlchemyRemote.H3AlchemyRemoteDB(location)
        target_db.master_login('postgres', password)
        logger.debug(_("Connected with master DB credentials"))
        target_db.nuke()

    @staticmethod
    def ping_local(location):
        """
        Checks if the local DB path points to a H3 database
        :param location:
        :return:
        """
        if location == "":
            return 0  # open() doesn't error out on an empty filename
        try:
            open(location)  # Try to open location
            temp_local_db = AlchemyLocal.H3AlchemyLocalDB(location)
            if temp_local_db.has_a_base():
                return 1  # This is a H3 DB
            else:
                return 0  # This is NOT a H3 DB, file will not be written to
        except IOError:
            return -1  # No file here, OK to create

    # Wizard-related functions

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
                self.remote_db = AlchemyRemote.H3AlchemyRemoteDB(temp_remote_db_location)
                if self.ping_local(temp_local_db_location) == 1:
                    self.local_db = AlchemyLocal.H3AlchemyLocalDB(temp_local_db_location)
                    if self.options.has_option('H3 Options', 'current user'):
                        username = self.options.get('H3 Options', 'current user')
                        self.current_job_contract = self.local_db.get_current_job_contract(username)
                        if self.local_db.get_user(username):
                            return True

    def setup_databases(self, local, remote):
        """
        Creates the local and remote DB instances and saves their location to the config file.
        Called from the setup wizard.
        """
        self.local_db = AlchemyLocal.H3AlchemyLocalDB(local)
        self.local_db.init_public_tables()
        self.remote_db = AlchemyRemote.H3AlchemyRemoteDB(remote)
        if not self.options.has_section('DB Locations'):
            self.options.add_section('DB Locations')
        self.options.set('DB Locations', 'local', local)
        self.options.set('DB Locations', 'remote', remote)
        self.options.write(open('config.txt', 'w'))

    def find_user(self, username):
        """
        Called from the wizard to find out the status of the "new user" credentials provided.
        :param username: the username to set up.
        """
        user = self.local_db.get_user(username)
        if user:
            self.user_state = "local"
        else:
            self.remote_db.login('reader', 'weak')
            user = self.remote_db.get_from_primary_key(Acd.User, username)
            if user:
                if self.remote_db.login(username, username + 'YOUPIE'):
                    # TODO : Find a better way than this to make a new user's pw
                    self.user_state = "new"
                else:
                    self.user_state = "remote"
        if user:
            self.wizard_user_details(username)

    def get_current_user_job_contract(self, username):
        """
        Called by wizard on finding a user which isn't in the local DB but IS in the remote.
        """
        self.remote_db.login('reader', 'weak')
        self.current_job_contract = self.remote_db.get_current_job_contract(username)

    def wizard_user_details(self, username):
        """
        Update the current user's personal and career details in the live core and in the config file.
        Used by the wizard (which will use the reader credentials on remote).
        User can be already in the local DB, in remote, or brand new in remote.
        User can have no job (wizard aborts) or be from another base (wizard will download that base's table).
        """
        if not self.options.has_section('H3 Options'):
            self.options.add_section('H3 Options')

        self.options.set('H3 Options', 'current user', username)

        if self.user_state == "local":
            self.current_job_contract = self.local_db.get_current_job_contract(username)
        elif self.user_state == "remote":
            self.remote_db.login('reader', 'weak')
            self.current_job_contract = self.remote_db.get_current_job_contract(username)
        if self.current_job_contract:
            self.update_base_visibility(self.current_job_contract.base)
            self.options.set('H3 Options', 'Root Base', self.current_job_contract.base)

            local_bases_list = self.local_db.get_local_bases()

            if self.current_job_contract.base not in local_bases_list:
                logger.info(_("User {name} is currently affected to {base}, which isn't part of the local DB.")
                            .format(name=username, base=self.current_job_contract.base))
                self.user_state = "new_base"
        else:
            logger.info(_("User {name} doesn't currently have a contract")
                        .format(name=username))
            self.user_state = "no_job"

        self.options.write(open('config.txt', 'w'))

    # Functions used by wizard AND application

    def update_base_visibility(self, base_name):
        """
        Queries local database for the organisational tree, then walks it to extract a list of sub-bases
        :param base_name: root of the extracted subtree
        """
        org_table = self.local_db.read_table(Acd.WorkBase)
        self.base_visibility = []
        self.base_visibility.append(base_name)
        tree_row = [base_name]
        next_row = list()
        while tree_row:
            for base in tree_row:
                for record in org_table:
                    if record.parent == base:
                        if record.parent != record.code:
                            next_row.append(record.code)
                            self.base_visibility.append(record.code)
            tree_row = next_row
            next_row = list()

    # Login functions

    def local_login(self, username, password):
        """
        Logs in at app-level, in the local DB.
        """
        if self.local_db.login(username, password):
            self.update_user_status(username)
        else:
            self.user_state = "nok"

    def remote_login(self, username, password):
        """
        Creates the link into the remote DB, with SQL credentials.
        Should be able to survive disconnects.
        :param username:
        :param password:
        :return:
        """
        # TODO : If success, start a timer that will ping and sync the remote DB according to options.
        if self.remote_db.login(username, password):
            pass

    # Application functions

    def update_user_status(self, username):
        """
        Update the current user's personal and career status in the live core and in the config file.
        Used on local login.
        :return:
        """
        self.options.set('H3 Options', 'current user', username)
        self.current_job_contract = self.local_db.get_current_job_contract(username)

        if self.current_job_contract:
            self.options.set('H3 Options', 'Root Base', self.current_job_contract.base)
            self.update_base_visibility(self.current_job_contract.base)
            local_bases_list = self.local_db.get_local_bases()
            if self.current_job_contract.base not in local_bases_list:
                logger.info(_("User {name} is currently affected to {base}, which isn't part of the local DB.")
                            .format(name=username, base=self.current_job_contract.base))
                self.user_state = "new_base"
            else:
                self.user_state = "ok"
        else:
            logger.info(_("User {name} doesn't currently have a contract")
                        .format(name=username))
            self.user_state = "no_job"

        self.options.write(open('config.txt', 'w'))

    def get_actions(self):
        self.contract_actions = self.local_db.get_contract_actions(self.current_job_contract)
        self.delegations = self.local_db.get_current_delegations(self.current_job_contract)

    def get_base(self, base_code):
        return self.local_db.get_base(base_code)

    def get_user(self, username):
        return self.local_db.get_user(username)

    def read_table(self, class_of_table, location):
        if location == "local":
            return self.local_db.read_table(class_of_table)
        elif location == "remote":
            return self.remote_db.read_table(class_of_table)

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

    def create_base(self, base):
        """
        Builds the user object and sends it to the remote engine for app- and SQL-level setup.
        :param base:
        :return:
        """
        sync_entry = Acd.SyncJournal(origin_jc=self.current_job_contract,
                                     target_jc=self.current_job_contract,
                                     type="CREATE",
                                     table="bases",
                                     key=base.code,
                                     status="UNSUBMITTED",
                                     local_timestamp=datetime.datetime.now())
        self.local_db.put(base)
        self.local_db.put(sync_entry)

    def sync_up(self):
        """

        :return:
        """

    def sync_down(self):
        """
        Syncing the latest data from remote as available / at set intervals.
        :return:
        """
        current_cursor = self.local_db.get_last_synced_entry()
        updates = self.remote_db.get_updates(current_cursor, self.current_job_contract)
        self.process_updates(updates)

    def process_updates(self, updates):
        hundred_percent = len(updates)  # Preparing for progress bar...
        for update in updates:
            class_to_update = self.get_class_by_table_name(update.table)
            record = self.remote_db.get_from_primary_key(class_to_update, update.key)
            if update.type == "create" or update.type == "update":
                self.local_db.put([record, ])
            elif update.type == "delete":
                self.local_db.delete([record, ])

    @staticmethod
    def get_class_by_table_name(tablename):
        for c in Acd.Base._decl_class_registry.values():
            if hasattr(c, '__tablename__') and c.__tablename__ == tablename:
                return c

    def get_visible_users(self):
        """
        Returns the users in the remote user list that belong to the visible bases,
        e.g the ones belonging to the install base or below
        :return:
        """
        return self.remote_db.get_visible_users(self.base_visibility)

    def remote_pw_change(self, username, old_pass, new_pass):
        self.remote_db.login(username, old_pass)
        if self.remote_db.update_pass(username, old_pass, new_pass):
            logger.debug(_("Password change successful for user {login}")
                         .format(login=username))
        else:
            logger.error(_("Couldn't change password in remote for user {login}")
                         .format(login=username))

    def get_action_descriptions(self, id):
        return self.local_db.get_action_descriptions(id, self.language)

    def get_user_count(self, base_code):
        return self.remote_db.user_count(base_code)
