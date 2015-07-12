__author__ = 'Man'

import configparser
import logging

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

        self.current_user = Acd.User
        self.current_job_contract = Acd.JobContract
        self.base_visibility = []

        self.contract_actions = list()
        self.delegations = list()

        self.language = "EN_UK"

        self.options = configparser.ConfigParser()

    # General utility functions

    def ping_remote(self, address):
        temp_remote_db = AlchemyRemote.H3AlchemyRemoteDB(address)
        if temp_remote_db.login('reader', 'weak'):
            return 1
        else:
            return 0

    def init_remote(self, location, password):
        new_db = AlchemyRemote.H3AlchemyRemoteDB(location)
        new_db.master_login('postgres', password)
        logger.debug(_("Connected with master DB credentials"))
        new_db.initialize(password)

    def nuke_remote(self, location, password):
        target_db = AlchemyRemote.H3AlchemyRemoteDB(location)
        target_db.master_login('postgres', password)
        logger.debug(_("Connected with master DB credentials"))
        target_db.nuke()

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
            temp_local_db = AlchemyLocal.H3AlchemyLocalDB(path)
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
                        self.current_user = self.local_db.get_user(username)
                        if self.current_user:
                            return True

    def setup_databases(self, local, remote):
        """
        Creates the local and remote DB instances and saves their location to the config file.
        Called from the setup wizard.
        """
        self.local_db = AlchemyLocal.H3AlchemyLocalDB(local)
        self.local_db.init_public_tables()
        self.remote_db = AlchemyRemote.H3AlchemyRemoteDB(remote)
        self.download_public_tables()
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
        self.current_user = None
        self.current_user = self.local_db.get_user(username)
        if self.current_user:
            self.user_state = "local"
        else:
            self.remote_db.login('reader', 'weak')
            self.current_user = self.remote_db.get_user(username)
            if self.current_user:
                if self.remote_db.login(username, username + 'YOUPIE'):
                    self.user_state = "new"
                else:
                    self.user_state = "remote"
        if self.current_user:
            self.wizard_user_details()

    def download_current_user_job_contract(self):
        """
        Called by wizard on finding a user which isn't in the local DB but IS in the remote.
        Downloads the user's personal and current job info.
        """
        user = self.current_user
        self.remote_db.login('reader', 'weak')
        contract = self.remote_db.get_current_job_contract(user)
        if contract:
            self.local_db.put([user, ])
            logger.debug(_("User {login} written into local DB")
                         .format(login=user.login))
            self.local_db.put([contract, ])
            logger.debug(_("User {login}'s current job contract '{contract}' written into local DB")
                         .format(login=user.login, contract=contract.job_title + ", " + contract.base))
        else:
            logger.warning(_("User {login} doesn't have any jobs !")
                           .format(login=user.login))

    # Wizard initial data download (not sync)

    def download_public_tables(self):
        """
        First table to be populated entirely from remote as clients need to know the worldwide structure
        (For users who have had a worldwide career !). Uses reader credentials from first setup.
        """
        # TODO: supplement that with a proper sync (OK for first setup)
        self.remote_db.login('reader', 'weak')
        org_table_data = self.remote_db.read_table(Acd.WorkBase)
        all_jobs = self.remote_db.read_table(Acd.Job)
        all_actions = self.remote_db.read_table(Acd.Action)
        self.local_db.put(org_table_data)
        self.local_db.put(all_jobs)
        self.local_db.put(all_actions)

    def download_base_tables(self):
        pass

    def download_user_tables(self):
        """
        We should have left the wizard just before, or logged in.
        From here on, the reading is done by the actual user account.
        """
        my_actions = self.remote_db.get_contract_actions(self.current_job_contract)
        my_delegations = self.remote_db.get_delegations(self.current_job_contract)
        self.local_db.put(my_actions)
        self.local_db.put(my_delegations)

    def wizard_user_details(self):
        """
        Update the current user's personal and career details in the live core and in the config file.
        Used by the wizard (which will use the reader credentials on remote)
        :return:
        """
        if not self.options.has_section('H3 Options'):
            self.options.add_section('H3 Options')

        self.options.set('H3 Options', 'current user', self.current_user.login)

        if self.user_state == "local":
            self.current_job_contract = self.local_db.get_current_job_contract(self.current_user)
        elif self.user_state == "remote":
            self.remote_db.login('reader', 'weak')
            self.current_job_contract = self.remote_db.get_current_job_contract(self.current_user)
        if self.current_job_contract:
            self.update_base_visibility(self.current_job_contract.base)
            self.options.set('H3 Options', 'Root Base', self.current_job_contract.base)

            local_bases_list = self.local_db.get_local_bases()

            if self.current_job_contract.base not in local_bases_list:
                logger.info(_("User {name} is currently affected to {base}, which isn't part of the local DB.")
                            .format(name=self.current_user.login, base=self.current_job_contract.base))
                self.user_state = "new_base"
        else:
            logger.info(_("User {name} doesn't currently have a contract")
                        .format(name=self.current_user.login))
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
        then sets the core's current user.
        :return: True if login succeeded, False if failed
        """
        logged_user = self.local_db.login(username, password)
        if logged_user:
            self.current_user = logged_user
            self.update_user_status()
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

    def update_user_status(self):
        """
        Update the current user's personal and career status in the live core and in the config file.
        Used on local login.
        :return:
        """
        self.options.set('H3 Options', 'current user', self.current_user.login)

        self.current_job_contract = self.local_db.get_current_job_contract(self.current_user)

        if self.current_job_contract:
            self.update_base_visibility(self.current_job_contract.base)
            self.options.set('H3 Options', 'Root Base', self.current_job_contract.base)

            local_bases_list = self.local_db.get_local_bases()

            if self.current_job_contract.base not in local_bases_list:
                logger.info(_("User {name} is currently affected to {base}, which isn't part of the local DB.")
                            .format(name=self.current_user.login, base=self.current_job_contract.base))
                self.user_state = "new_base"
            else:
                self.user_state = "ok"
        else:
            logger.info(_("User {name} doesn't currently have a contract")
                        .format(name=self.current_user.login))
            self.user_state = "no_job"

        self.options.write(open('config.txt', 'w'))

    def get_actions(self):
        self.contract_actions = self.local_db.get_contract_actions(self.current_job_contract)
        self.delegations = self.local_db.get_current_delegations(self.current_job_contract)

    def base_full_name(self, base):
        return self.local_db.get_base_full_name(base)

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
