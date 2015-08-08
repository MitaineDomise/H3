__author__ = 'Man'

import configparser
import logging
import datetime

from . import AlchemyLocal, AlchemyRemote
from . import AlchemyClassDefs as Acd

logger = logging.getLogger(__name__)

# TODO : Local + Remote Session management from core ?

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

        self.current_job_contract = None
        self.base_visibility = []

        self.contract_actions = list()
        self.delegations = list()

        self.serials = dict()

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

    def wizard_system_ready(self):
        """
        Checks that the system is ready to go without further configuration :
         - local and remote DB locations are saved in the config file
         - local DB file is a proper H3 DB (remote is initialized but not pinged at this point)
         - current user option is set in the config file
         - user exists in the local DB
         - user has a current job in the local DB
        If any criteria are not met, wizard is run.
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
                        user = self.local_db.get_user_from_login(username)
                        self.current_job_contract = self.local_db.get_current_job_contract(user)
                        if self.current_job_contract:
                            return True

    def wizard_setup_databases(self, local, remote):
        """
        Creates the local and remote DB instances and saves their location to the config file.
        Called from the setup wizard.
        """
        self.local_db = AlchemyLocal.H3AlchemyLocalDB(local)
        self.local_db.create_all_tables()
        self.remote_db = AlchemyRemote.H3AlchemyRemoteDB(remote)
        if not self.options.has_section('DB Locations'):
            self.options.add_section('DB Locations')
        self.options.set('DB Locations', 'local', local)
        self.options.set('DB Locations', 'remote', remote)
        self.options.write(open('config.txt', 'w'))

    def wizard_find_user(self, username):
        """
        Called from the wizard to find out the status of the user credentials provided. Can be :
         - local (user is already set up in the local file)
         - remote (user is set up in remote but needs to be redownloaded)
         - new (user has been freshly created and will have to set up a password)
        Then calls user details for finer inspection
        :param username: the username to set up.
        """
        user = self.local_db.get_user_from_login(username)
        if user:
            self.user_state = "local"
        else:
            self.remote_db.login('reader', 'weak')
            user = self.remote_db.get_user_from_login(username)
            if user:
                if self.remote_db.login(username, username + 'YOUPIE'):
                    # TODO : Find a better way than this to make/check a new user's pw
                    self.user_state = "new"
                else:
                    self.user_state = "remote"
        if user:
            self.wizard_user_details(user)

    def wizard_user_details(self, user):
        """
        Update the current user's personal and career details in the live core and in the config file.
        Used by the wizard (which will use the reader credentials on remote).
        Upon inspection of the user's details two new states can be detected:
         - new_base means the local DB doesn't hold the data for this user's base
         - no_job means the user is not currently employed and should not be allowed to log in
        :param user: A user object to process
        """
        if not self.options.has_section('H3 Options'):
            self.options.add_section('H3 Options')

        self.options.set('H3 Options', 'current user', user.login)

        if self.user_state == "local":
            self.current_job_contract = self.local_db.get_current_job_contract(user)
        elif self.user_state == "remote":
            self.remote_db.login('reader', 'weak')
            self.current_job_contract = self.remote_db.get_current_job_contract(user)
        if self.current_job_contract:
            self.update_base_visibility(self.current_job_contract.base)
            self.options.set('H3 Options', 'Root Base', self.current_job_contract.base)

            local_bases_list = self.local_db.get_local_bases()

            if self.current_job_contract.base not in local_bases_list:
                logger.info(_("User {name} is currently affected to {base}, which isn't part of the local DB.")
                            .format(name=user.login, base=self.current_job_contract.base))
                self.user_state = "new_base"
        else:
            logger.info(_("User {name} doesn't currently have a contract")
                        .format(name=user.login))
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
        self.base_visibility.append('GLOBAL')

    # Login functions

    def local_login(self, username, password):
        """
        Logs in at app-level, in the local DB.
        """
        if self.local_db.login(username, password):
            self.update_user_status(username)
            self.extract_current_serials()
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
        user = self.local_db.get_user_from_login(username)
        self.current_job_contract = self.local_db.get_current_job_contract(user)

        if self.current_job_contract:
            self.options.set('H3 Options', 'Root Base', self.current_job_contract.work_base)
            self.update_base_visibility(self.current_job_contract.work_base)
            local_bases_list = self.local_db.get_local_bases()
            if self.current_job_contract.work_base not in local_bases_list:
                logger.info(_("User {name} is currently affected to {base}, which isn't part of the local DB.")
                            .format(name=username, base=self.current_job_contract.work_base))
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

    def get_user(self, username):
        return self.local_db.get_user_from_login(username)

    def get_from_primary_key(self, mapped_class, pkey, location):
        if location == "local":
            return self.local_db.get_from_primary_key(mapped_class, pkey)
        elif location == "remote":
            return self.remote_db.get_from_primary_key(mapped_class, pkey)

    def read_table(self, class_of_table, location):
        if location == "local":
            return self.local_db.read_table(class_of_table)
        elif location == "remote":
            return self.remote_db.read_table(class_of_table)

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
                                     local_timestamp=datetime.datetime.utcnow())
        self.local_db.merge(base)
        self.local_db.merge(sync_entry)

    def sync_up(self):
        """
        Sends unsubmitted (negative) sync entries to remote DB.
        Should work first time on most cases; if there is a conflict, calls a rebase to solve it and resubmits.
        :return:
        """
        updates = self.local_db.get_update_queue()
        result = self.submit_updates_for_upload(updates)
        if result == "conflict":
            self.sync_down()
            self.rebase_unsubmitted_updates()
            self.sync_up()
        elif result == "success":
            self.sync_down()
            return True

    def submit_updates_for_upload(self, updates):
        """
        Tries an optimistic upload of unsubmitted updates.
        :param updates:
        :return: synchronization result : success, error or conflict (needs to rebase)
        """
        upward_sync_status = "success"
        for update in updates:

            if update.status == "UNSUBMITTED":
                record_class = self.get_class_by_table_name(update.table)
                record = self.local_db.get_from_primary_key(record_class, update.key) \
                    .copy()
                record.code = record.code.lstrip("TMP-")

                if update.type == "create":
                    result, timestamp = self.remote_db.add(record)
                elif update.type == "update":
                    result, timestamp = self.remote_db.merge(record)
                elif update.type == "delete":
                    result, timestamp = self.remote_db.delete(record)

            if result == "ok":
                update.status = "ACCEPTED"
                update.processed_timestamp = timestamp
            elif result == "dupe":
                upward_sync_status = "conflict"
                update.status = "MODIFIED"
                update.processed_timestamp = timestamp
            elif result == "err":
                upward_sync_status = "error"
                update.status = "REJECTED"
                update.processed_timestamp = timestamp

        if upward_sync_status == "success":
            for update in updates:
                self.local_db.delete(update)
                update.serial = None
                self.remote_db.merge(update)

        return upward_sync_status

    def rebase_unsubmitted_updates(self):
        """
        Will update temp numbers to follow the canonical ones downloaded from the central DB
        Will also raise errors when stocks or budgets go negative !
        :return:
        """
        updates = self.local_db.get_update_queue()
        self.extract_current_serials()
        serials = self.serials.copy()

        for update in updates:
            mapped_class = self.get_class_by_table_name(update.table)
            record = self.local_db.get_from_primary_key(mapped_class, update.key)
            serials[update.table][record.base] += 1
            new_serial = serials[update.table][record.base]
            record.serial = new_serial
            record.code = self.build_key(record, mapped_class)

    @staticmethod
    def build_key(record, mapped_class):
        base = record.base.join("-") if record.base != 'GLOBAL' else ''
        period = record.period.join("-") if record.period != 'PERMANENT' else ''
        code = "{base}{prefix}-{period}{serial}".format(base=base,
                                                        prefix=mapped_class.prefix,
                                                        period=period,
                                                        serial=record.serial)
        return code

    def extract_current_serials(self):
        """
        At login, populates the dict keeping track of the current highest serial for all transactions
        :return:
        """
        for table in Acd.Base.metadata.tables:
            mapped_class = self.get_class_by_table_name(table)
            for base in self.base_visibility:
                self.serials[table][base] = self.local_db.get_highest_serial(mapped_class, base)

    def repost(self, update):
        record_class = self.get_class_by_table_name(update.table)
        record = self.local_db.get_from_primary_key(record_class, update.key)
        # record.code = self.next_(record_class)

        new_update = update.copy()
        new_update.status = "UNSUBMITTED"
        new_update.local_timestamp = datetime.datetime.utcnow()
        new_update.key = record.code
        self.local_db.add(new_update)

    def sync_down(self):
        """
        Syncing the latest data from remote as available / at set intervals.
        :return:
        """
        current_cursor = self.local_db.get_last_synced_entry()
        updates = self.remote_db.get_updates(current_cursor, self.base_visibility)
        if updates:
            self.process_downloaded_updates(updates)
        self.rebase_unsubmitted_updates()

    def process_downloaded_updates(self, updates):
        """
        Records updates from the main DB as-is.
        The generic record parser means each record gets downloaded separately.
        :param updates:
        :return:
        """
        # hundred_percent = len(updates)  # Preparing for progress bar...
        for update in updates:
            self.local_db.add(update)
            class_to_update = self.get_class_by_table_name(update.table)
            record = self.remote_db.get_from_primary_key(class_to_update, update.key)
            if update.type == "create":
                self.local_db.add(record)
            if update.type == "update":
                self.local_db.merge(record)
            elif update.type == "delete":
                self.local_db.delete(record)

    @staticmethod
    def get_class_by_table_name(tablename):
        # noinspection PyProtectedMember
        for c in Acd.Base._decl_class_registry.values():
            if hasattr(c, '__tablename__') and c.__tablename__ == tablename:
                return c

    def remote_pw_change(self, username, old_pass, new_pass):
        self.remote_db.login(username, old_pass)
        if self.remote_db.update_pass(username, old_pass, new_pass):
            logger.debug(_("Password change successful for user {login}")
                         .format(login=username))
        else:
            logger.error(_("Couldn't change password in remote for user {login}")
                         .format(login=username))

    def get_action_descriptions(self, action_id):
        return self.local_db.get_action_descriptions(action_id, self.language)

    def get_user_count(self, base_code):
        return self.remote_db.user_count(base_code)
