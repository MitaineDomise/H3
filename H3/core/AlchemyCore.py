__author__ = 'Man'

import configparser
import logging
import datetime

import sqlalchemy.orm

from . import AlchemyLocal, AlchemyRemote, AlchemyGeneric
from . import AlchemyClassDefs as Acd
from .AlchemyTemporal import versioned_session

SessionRemote = sqlalchemy.orm.sessionmaker()
SessionLocal = sqlalchemy.orm.sessionmaker()

logger = logging.getLogger(__name__)

# TODO : Local + Remote Session management from core ?

class H3AlchemyCore:
    """
    This is the central module for data manipulation. Now relies on SQLAlchemy's ORM.
    """
    def __init__(self):
        """
        Creates the values and objects used throughout a user session.
        """

        self.local_db = AlchemyLocal.H3AlchemyLocalDB(None)
        self.remote_db = AlchemyRemote.H3AlchemyRemoteDB(None)

        self.user_state = ""

        self.current_job_contract = None
        self.base_visibility = []
        self.contract_actions = list()
        self.delegations = list()

        self.serials = dict()
        self.queue_cursor = 0

        self.language = "EN_UK"

        self.options = configparser.ConfigParser()

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
                if ping_local(temp_local_db_location) == 1:
                    self.local_db = AlchemyLocal.H3AlchemyLocalDB(temp_local_db_location)
                    SessionLocal.configure(bind=self.local_db.engine)
                    if self.options.has_option('H3 Options', 'current user'):
                        username = self.options.get('H3 Options', 'current user')
                        local_session = SessionLocal()
                        user = AlchemyGeneric.get_user_from_login(local_session, username)
                        self.current_job_contract = AlchemyGeneric.get_current_job_contract(local_session, user)
                        local_session.close()
                        if self.current_job_contract:
                            return True

    def wizard_setup_databases(self, local, remote):
        """
        Creates the local and remote DB instances and saves their location to the config file.
        Called from the setup wizard.
        """
        self.local_db = AlchemyLocal.H3AlchemyLocalDB(local)
        SessionLocal.configure(bind=self.local_db.engine)
        self.local_db.create_all_tables()

        self.remote_db = AlchemyRemote.H3AlchemyRemoteDB(remote)
        self.remote_db.login('reader', 'weak')
        SessionRemote.configure(bind=self.remote_db.engine)

        if not self.options.has_section('DB Locations'):
            self.options.add_section('DB Locations')
        self.options.set('DB Locations', 'local', local)
        self.options.set('DB Locations', 'remote', remote)
        self.options.write(open('config.txt', 'w'))

    def wizard_find_user(self, username):
        """
        Called from the wizard to find out the status of the user credentials provided. Can be :
         - local (user is already set up in the local file)
         - remote (user is set up in remote but needs to be re-downloaded)
         - new (user has been freshly created and will have to set up a password)
         - new_base means the local DB doesn't hold the data for this user's base
         - no_job means the user is not currently employed and should not be allowed to log in
         - invalid, found nowhere
        :param username: the username to set up.
        """
        local_session = SessionLocal()
        user = AlchemyGeneric.get_user_from_login(local_session, username)
        local_bases_list = AlchemyLocal.get_local_bases(local_session)
        if user:
            self.user_state = "local"
            logger.info(_("User {name} found in local")
                        .format(name=user.login))
            self.current_job_contract = AlchemyGeneric.get_current_job_contract(local_session, user)
        else:
            remote_session = SessionRemote()
            user = AlchemyGeneric.get_user_from_login(remote_session, username)
            self.current_job_contract = AlchemyGeneric.get_current_job_contract(remote_session, user)
            remote_session.close()
            if user:
                if self.remote_db.login(username, username + 'YOUPIE'):
                    # TODO : Find a better way than this to make/check a new user's pw
                    logger.info(_("User {name} found in remote with temporary password")
                                .format(name=user.login))
                    self.user_state = "new"
                else:
                    logger.info(_("User {name} found in remote with an activated account")
                                .format(name=user.login))
                    self.user_state = "remote"
        local_session.close()

        if self.current_job_contract:
            if self.current_job_contract.work_base not in local_bases_list:
                logger.info(_("User {name} is currently affected to {base}, which isn't part of the local DB.")
                            .format(name=user.login, base=self.current_job_contract.base))
                self.user_state = "new_base"
        else:
            logger.info(_("User {name} doesn't currently have a contract")
                        .format(name=user.login))
            self.user_state = "no_job"

        if not user:
            logger.info(_("User {name} not found in any DB")
                        .format(name=user.login))
            self.user_state = "invalid"
        self.options.write(open('config.txt', 'w'))

    # Login functions

    def local_login(self, username, password):
        """
        Logs in at app-level, in the local DB.
        """
        local_session = SessionLocal()
        login_ok = AlchemyLocal.login(local_session, username, password)
        local_session.close()
        if login_ok:
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
        self.remote_db.login(username, password)

    # Application functions

    def update_user_status(self, username):
        """
        Update the current user's personal and career status in the live core and in the config file.
        Used on local login.
        :return:
        """
        if not self.options.has_section('H3 Options'):
            self.options.add_section('H3 Options')
        self.options.set('H3 Options', 'current user', username)

        local_session = SessionLocal()
        user = AlchemyGeneric.get_user_from_login(local_session, username)
        self.current_job_contract = AlchemyGeneric.get_current_job_contract(local_session, user)

        if self.current_job_contract:
            self.update_base_visibility(self.current_job_contract.work_base)
            local_bases_list = AlchemyLocal.get_local_bases(local_session)
            if self.current_job_contract.work_base not in local_bases_list:
                logger.error(_("User {name} is currently affected to {base}, which isn't part of the local DB.")
                             .format(name=username, base=self.current_job_contract.work_base))
                self.user_state = "new_base"
            else:
                self.user_state = "ok"
        else:
            logger.info(_("User {name} doesn't currently have a contract")
                        .format(name=username))
            self.user_state = "no_job"
        local_session.close()

        self.options.write(open('config.txt', 'w'))

    def update_base_visibility(self, root_base_pkey):
        """
        Queries local database for the organisational tree, then walks it to extract a list of sub-bases
        :param root_base_pkey: root of the extracted subtree
        """
        local_session = SessionLocal()
        org_table = AlchemyGeneric.read_table(local_session, Acd.WorkBase)
        local_session.close()
        self.base_visibility = []
        self.base_visibility.append(root_base_pkey)
        tree_row = [root_base_pkey]
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
        self.base_visibility.append('BASE-1')

    def get_actions(self):
        local_session = SessionLocal()
        self.contract_actions = AlchemyLocal.get_contract_actions(local_session, self.current_job_contract)
        self.delegations = AlchemyLocal.get_current_delegations(local_session, self.current_job_contract)
        local_session.close()

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
        local_session = SessionLocal()
        status1, = AlchemyGeneric.merge(local_session, base)
        status2, = AlchemyGeneric.merge(local_session, sync_entry)
        if status1 == status2 == "ok":
            local_session.commit()
        else:
            local_session.rollback()
        local_session.close()

    def sync_up(self):
        """
        Sends unsubmitted (negative) sync entries to remote DB.
        Should work first time on most cases; if there is a conflict, calls a rebase to solve it and resubmits.
        :return:
        """
        local_session = SessionLocal()
        updates = AlchemyLocal.get_sync_queue(local_session)
        local_session.close()
        result = submit_updates_for_upload(updates)
        if result == "conflict":
            self.sync_down()
            self.rebase_queued_updates()
            self.sync_up()
        elif result == "success":
            self.sync_down()

    def rebase_queued_updates(self):
        """
        Will update temp numbers to follow the canonical ones downloaded from the central DB
        Updates failed sync entries with a pointer to the new TMP entry and queues a new one
        :return:
        """
        local_session = SessionLocal()
        updates = AlchemyLocal.get_sync_queue(local_session)

        if updates:
            self.extract_current_serials()
            serials = self.serials.copy()

            for update in updates:
                mapped_class = get_class_by_table_name(update.table)
                record = AlchemyGeneric.get_from_primary_key(local_session, mapped_class, update.key)
                serials[update.table][record.base] += 1
                new_serial = serials[update.table][record.base]
                if new_serial != record.serial:
                    record.serial = new_serial
                    update.status = "MODIFIED"
                    new_code = build_key(record, mapped_class)
                    record.code = "TMP-".join(new_code)
                if update.status == "MODIFIED":
                    new_update = update.copy()
                    self.queue_cursor -= 1
                    new_update.serial = self.queue_cursor

                    new_update.key = record.code
                    new_update.status = "UNSUBMITTED"

                    new_update.local_timestamp = datetime.datetime.utcnow()

                    update.status = "MODIFIED-".join(record.code)

                    local_session.merge(record)
                    local_session.merge(update)
                    local_session.merge(new_update)
            local_session.commit()
        local_session.close()

    def extract_current_serials(self):
        """
        At login, populates the dict of dicts keeping track of the current highest serial for all transactions
        :return:
        """
        self.serials = dict()
        self.queue_cursor = 0

        local_session = SessionLocal()
        self.queue_cursor = AlchemyLocal.get_lowest_queued_sync_entry(local_session)
        for table in Acd.Base.metadata.tables:
            if table != "journal_entries":
                self.serials.update({table: dict()})
                mapped_class = get_class_by_table_name(table)
                for base in self.base_visibility:
                    highest = AlchemyLocal.get_highest_serial(local_session, mapped_class, base)
                    self.serials[table].update({base: highest})
        local_session.close()

    def sync_down(self):
        """
        Syncing the latest data from remote as available / at set intervals.
        Then positions the queue cursor to negative(latest synced entry)-1 for the next entry to queue
        :return:
        """
        local_session = SessionLocal()
        current_cursor = AlchemyLocal.get_highest_synced_sync_entry(local_session)
        local_session.close()

        remote_session = SessionRemote()
        updates = AlchemyRemote.get_updates(remote_session, current_cursor, self.base_visibility)
        remote_session.close()

        if updates:
            process_downloaded_updates(updates)

        self.rebase_queued_updates()

    def remote_pw_change(self, username, old_pass, new_pass):
        self.remote_db.login(username, old_pass)
        SessionRemote.configure(bind=self.remote_db.engine)
        remote_session = SessionRemote()
        result = self.remote_db.update_pass(remote_session, username, old_pass, new_pass)
        if result:
            remote_session.commit()
        else:
            remote_session.rollback()
        remote_session.close()
        if result:
            if self.remote_db.login(username, new_pass):
                SessionRemote.configure(bind=self.remote_db.engine)
                logger.debug(_("New password is now in effect for user {user}")
                             .format(user=username))
                return True
            else:
                logger.error(_("Failed to log into remote after a password change"))
        else:
            logger.error(_("Couldn't change password in remote for user {login}")
                         .format(login=username))
            return False

    def get_action_description(self, action_id):
        local_session = SessionLocal()
        action_desc = AlchemyLocal.get_action_description(local_session, action_id, self.language)
        local_session.close()
        return action_desc


def process_downloaded_updates(updates):
    """
    Records updates from the main DB as-is.
    The generic record parser means each record gets downloaded separately.
    :param updates:
    :return:
    """
    # hundred_percent = len(updates)  # Preparing for progress bar...
    down_sync_status = "success"
    result = ""
    local_session = SessionLocal()
    for update in updates:
        class_to_process = get_class_by_table_name(update.table)
        remote_session = SessionRemote()
        record_to_process = AlchemyGeneric.get_from_primary_key(remote_session, class_to_process, update.key)
        remote_session.close()
        if update.type == "create":
            result, = AlchemyGeneric.add(local_session, record_to_process)
        if update.type == "update":
            result, = AlchemyGeneric.merge(local_session, record_to_process)
        elif update.type == "delete":
            result, = AlchemyGeneric.delete(local_session, record_to_process)
        AlchemyGeneric.add(local_session, update)
        if result != "ok":
            down_sync_status = "error"
    return down_sync_status


def get_user_count(base_code):
    remote_session = SessionRemote()
    count = AlchemyRemote.user_count(remote_session, base_code)
    remote_session.close()
    return count


def submit_updates_for_upload(updates):
    """
    Tries an optimistic upload of unsubmitted updates.
    :param updates:
    :return: synchronization result : success, error or conflict (needs to rebase)
    """
    # TODO: detect when stocks go negative ?
    upward_sync_status = "success"
    local_session = SessionLocal()
    remote_session = SessionRemote()
    versioned_session(remote_session)
    for update in updates:
        timestamp = datetime.datetime.utcnow()
        if update.status == "UNSUBMITTED":
            record_class = get_class_by_table_name(update.table)
            record = AlchemyGeneric.get_from_primary_key(local_session, record_class, update.key)
            record.code = record.code.lstrip("TMP-")

            if update.type == "create":
                result, timestamp = AlchemyGeneric.add(remote_session, record)
            elif update.type == "update":
                result, timestamp = AlchemyGeneric.merge(remote_session, record)
            elif update.type == "delete":
                result, timestamp = AlchemyGeneric.delete(remote_session, record)

            if result == "ok":
                update.status = "ACCEPTED"
                AlchemyGeneric.delete(local_session, update)
                update.serial = None
                AlchemyGeneric.merge(local_session, update)
            elif result == "dupe":
                upward_sync_status = "conflict"
                update.status = "MODIFIED"
            elif result == "err":
                upward_sync_status = "error"
                update.status = "REJECTED"
            update.processed_timestamp = timestamp

        update.serial = None
        result1, = AlchemyGeneric.add(remote_session, update)
        result2, = AlchemyGeneric.delete(local_session, update)
        if result1 == result2 == "ok":
            pass
        else:
            upward_sync_status = "error"

    if upward_sync_status == "success":
        remote_session.commit()
        local_session.commit()
    else:
        remote_session.rollback()
        local_session.rollback()

    local_session.close()
    remote_session.close()

    return upward_sync_status


def ping_local(location):
    """
    Checks if the local DB path points to a H3 database
    :param location:
    :return:
    """
    # TODO: check that file creation works / change detection of absent file through IOError
    if location == "":
        return 0  # open() doesn't error out on an empty filename
    try:
        open(location)  # fails with IOError if file doesn't exist
        temp_local_db = AlchemyLocal.H3AlchemyLocalDB(location)
        SessionLocal.configure(bind=temp_local_db.engine)
        local_session = SessionLocal()
        result = AlchemyLocal.has_a_base(local_session)
        local_session.close()
        if result:
            return 1  # This is a H3 DB
        else:
            return 0  # This is NOT a H3 DB, file will not be written to
    except IOError:
        return -1  # No file here, OK to create


def ping_remote(address):
    temp_remote_db = AlchemyRemote.H3AlchemyRemoteDB(address)
    if temp_remote_db.login('reader', 'weak'):
        return 1
    else:
        return 0


# TODO: check the init/nuke for session management
def init_remote(location, password):
    new_db = AlchemyRemote.H3AlchemyRemoteDB(location)
    new_db.master_login('postgres', password)
    logger.debug(_("Connected with master DB credentials"))
    new_db.init_db(password)
    logger.debug(_("Created and switched to H3 DB"))
    SessionRemote.configure(bind=new_db.engine)
    remote_session = SessionRemote()

    if new_db.populate(remote_session):
        remote_session.commit()
        print(_("DB Init successful"))
    else:
        remote_session.rollback()
        print(_("DB Init failed"))
    remote_session.close()


def nuke_remote(location, password):
    target_db = AlchemyRemote.H3AlchemyRemoteDB(location)
    target_db.master_login('postgres', password)
    logger.debug(_("Connected with master DB credentials"))

    if target_db.nuke():
        print(_("DB Wipe successful"))
    else:
        print(_("DB Wipe failed"))


def get_class_by_table_name(tablename):
    # noinspection PyProtectedMember
    for c in Acd.Base._decl_class_registry.values():
        if hasattr(c, '__tablename__') and c.__tablename__ == tablename:
            return c


def read_table(class_of_table, location="local"):
    session = SessionLocal()
    if location == "remote":
        session = SessionRemote()
    table = AlchemyGeneric.read_table(session, class_of_table)
    session.close()
    return table


def get_from_primary_key(mapped_class, pkey, location="local"):
    session = SessionLocal()
    if location == "remote":
        session = SessionRemote()
    record = AlchemyGeneric.get_from_primary_key(session, mapped_class, pkey)
    session.close()
    return record


def build_key(record, mapped_class):
    """
    Builds a human-readable primary key out of the serial and meta fields of the record.
    Global records have base = GLOBAL and will not have this prefix
    Permanent records (never archived) have period = PERMANENT and the year / quarter etc will not appear
    Examples : SHB-REQUISITION-2015-172 , USER-324
    :param record:
    :param mapped_class:
    :return:
    """
    base = record.base.join("-") if record.base != 'GLOBAL' else ''
    period = record.period.join("-") if record.period != 'PERMANENT' else ''
    code = "{base}{prefix}-{period}{serial}".format(base=base,
                                                    prefix=mapped_class.prefix,
                                                    period=period,
                                                    serial=record.serial)
    return code
