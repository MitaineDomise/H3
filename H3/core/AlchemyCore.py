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

        self.internal_state = dict({"user": "", "base": ""})

        self.current_job_contract = Acd.JobContract()
        self.current_job_contract = None

        self.local_bases = list()
        self.local_job_contracts = list()

        self.assigned_actions = list()

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
                        self.local_bases = AlchemyLocal.get_local_bases(local_session)
                        self.local_job_contracts = AlchemyLocal.get_local_users(local_session)
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
        local_session.close()
        if user:
            self.internal_state["user"] = "local"
            self.update_user_status(user)
            logger.info(_("User {name} found in local")
                        .format(name=user.login))
        else:
            remote_session = SessionRemote()
            user = AlchemyGeneric.get_user_from_login(remote_session, username)
            self.current_job_contract = AlchemyGeneric.get_current_job_contract(remote_session, user)
            remote_session.close()
            if user:
                if self.remote_db.login(username, username + 'YOUPIE'):
                    logger.info(_("User {name} found in remote with temporary password")
                                .format(name=user.login))
                    self.internal_state["user"] = "new"
                else:
                    logger.info(_("User {name} found in remote with an activated account")
                                .format(name=user.login))
                    self.internal_state["user"] = "remote"

            if self.current_job_contract:
                if self.current_job_contract.work_base not in local_bases_list:
                    logger.info(_("User {name} is currently affected to {base}, which isn't part of the local DB.")
                                .format(name=user.login, base=self.current_job_contract.base))
                    self.internal_state["base"] = "new"
                else:
                    logger.info(_("User {name} doesn't currently have a contract")
                                .format(name=user.login))
                    self.internal_state["user"] = "no_job"

        local_session.close()

        if not user:
            logger.info(_("User {name} not found in any DB")
                        .format(name=user.login))
            self.internal_state["user"] = "invalid"
        self.options.write(open('config.txt', 'w'))

    def initial_setup(self):
        """

        If this is a new base, download the relevant records from base-specific tables.
        If this is a new user, download the user and job and then their current JC.

        :return:
        """
        remote_session = SessionRemote()
        local_session = SessionLocal()

        records = list()

        if self.internal_state["user"] == "ok":
            pass
        else:
            if self.internal_state["base"] == "new":
                # Just adding the top base. Others can be added in through admin tools.
                records.extend(build_base_pack(remote_session, self.current_job_contract.work_base))

            if self.internal_state["user"] == "remote":
                records.extend(build_user_pack(remote_session, self.current_job_contract.user))

        latest_sync_serial = AlchemyGeneric.get_highest_synced_sync_entry(remote_session)
        latest_sync_entry = AlchemyGeneric.get_from_primary_key(remote_session, Acd.SyncJournal, latest_sync_serial)
        records.append(latest_sync_entry)
        remote_session.close()

        AlchemyGeneric.merge_multiple(local_session, records)
        local_session.commit()

        self.local_bases = AlchemyLocal.get_local_bases(local_session)
        self.local_job_contracts = AlchemyLocal.get_local_users(local_session)

        local_session.close()

    # Login functions

    def local_login(self, username, password):
        """
        Logs in at app-level, in the local DB.
        """
        local_session = SessionLocal()
        logged_user = AlchemyLocal.login(local_session, username, password)
        if logged_user:
            self.update_user_status(logged_user)
            self.queue_cursor = AlchemyLocal.get_lowest_queued_sync_entry(local_session)
            self.extract_current_serials(local_session)
        else:
            self.internal_state["user"] = "nok"
        local_session.close()

    def remote_login(self, username, password):
        """
        Creates the link into the remote DB, with SQL credentials.
        Should be able to survive disconnects.
        :param username:
        :param password:
        :return:
        """
        self.remote_db.login(username, password)
        SessionRemote.configure(bind=self.remote_db.engine)

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

    # Application functions

    def update_user_status(self, user):
        """
        Update the current user's personal and career status in the live core and in the config file.
        Used on local login.
        Can find these statuses :
         - ok (login successful, active job contract found on a locally-recorded base)
         - no_job
         - new base
        :return:
        """
        if not self.options.has_section('H3 Options'):
            self.options.add_section('H3 Options')
        self.options.set('H3 Options', 'current user', user.login)

        local_session = SessionLocal()
        self.current_job_contract = AlchemyGeneric.get_current_job_contract(local_session, user)

        if self.current_job_contract:
            self.local_bases = AlchemyLocal.get_local_bases(local_session)
            current_jc_base = AlchemyGeneric.get_from_primary_key(local_session,
                                                                  Acd.WorkBase,
                                                                  self.current_job_contract.work_base)
            if current_jc_base not in self.local_bases:
                logger.error(_("User {name} is currently affected to {base}, which isn't part of the local DB.")
                             .format(name=user.login, base=current_jc_base.identifier))
                self.internal_state["base"] = "relocated"
            else:
                self.internal_state["user"] = "ok"
        else:
            logger.info(_("User {name} doesn't currently have a contract")
                        .format(name=user.login))
            self.internal_state["user"] = "no_job"
        local_session.close()

        self.options.write(open('config.txt', 'w'))

    def update_assigned_actions(self):
        local_session = SessionLocal()
        action_pairs = AlchemyGeneric.get_assigned_actions(local_session, self.current_job_contract)
        local_session.close()
        for assigned_action, _throwaway in action_pairs:
            self.assigned_actions.append(assigned_action)

    def create_base(self, base):
        """
        Builds the user object and sends it to the remote engine for app- and SQL-level setup.
        :param base:
        :return:
        """
        local_session = SessionLocal()
        self.prepare_record(base)
        self.queue_cursor = AlchemyLocal.get_lowest_queued_sync_entry(local_session)
        self.queue_cursor -= 1
        sync_entry = Acd.SyncJournal(serial=self.queue_cursor,
                                     origin=self.current_job_contract.code,
                                     type="CREATE",
                                     table="bases",
                                     key=base.code,
                                     status="UNSUBMITTED",
                                     local_timestamp=datetime.datetime.utcnow())
        status1 = AlchemyGeneric.merge(local_session, base)[0]
        status2 = AlchemyGeneric.merge(local_session, sync_entry)[0]
        if status1 == status2 == "ok":
            local_session.commit()
        else:
            local_session.rollback()
        local_session.close()

    def prepare_record(self, record):
        table = sqlalchemy.inspect(record).mapper.local_table.name
        local_session = SessionLocal()
        self.extract_current_serials(local_session)
        record.serial = self.serials[table][record.base] + 1
        record.code = "TMP-" + build_key(record)

    def sync_up(self):
        """
        Sends unsubmitted (negative) sync entries to remote DB.
        Should work first time on most cases; if there is a conflict, calls a rebase to solve it and resubmits.
        :return:
        """
        local_session = SessionLocal()
        entries = AlchemyLocal.get_sync_queue(local_session)
        local_session.close()
        result = submit_updates_for_upload(entries)
        if result == "conflict":
            self.sync_down()
            self.rebase_queued_updates()
            self.sync_up()
        elif result == "success":
            self.sync_down()

    def rebase_queued_updates(self):
        """After a failed upward sync, updates the upload queue with valid serials and codes

        Will update temp numbers to follow the canonical ones downloaded from the central DB
        Updates failed sync entries with a pointer to the new TMP entry and queues a new one
        :return:
        """
        local_session = SessionLocal()
        remote_session = SessionRemote()
        self.extract_current_serials(remote_session)
        remote_session.close()
        entries = AlchemyLocal.get_sync_queue(local_session)

        if entries:
            serials = self.serials.copy()

            for entry in entries:
                # Every entry in the queue gets checked, "modified" or not. Grab the referenced record
                mapped_class = get_class_by_table_name(entry.table)
                record = AlchemyGeneric.get_from_primary_key(local_session, mapped_class, entry.key)

                # Increment the current serial for this table / base pair
                serials[entry.table][record.base] += 1
                new_serial = serials[entry.table][record.base]

                # Check that the serial of the candidate for upload follows the sequence.
                # If not, set the entry as modified and update the record with a valid serial and code
                # This will push up all subsequent records, keeping chronology.
                if new_serial != record.serial:
                    entry.status = "MODIFIED"
                    record.serial = new_serial
                    record.code = "TMP-" + build_key(record)
                # post a new "unsubmitted" entry with the corrected serial and code.
                # the old entry's status gets updated, pointing to the new TMP-key for that record.
                if entry.status == "MODIFIED":
                    new_entry = entry.copy()
                    self.queue_cursor = AlchemyLocal.get_lowest_queued_sync_entry(local_session)
                    self.queue_cursor -= 1
                    new_entry.serial = self.queue_cursor
                    new_entry.key = record.code
                    new_entry.status = "UNSUBMITTED"
                    new_entry.local_timestamp = datetime.datetime.utcnow()

                    entry.status = "MODIFIED-".join(record.code)

                    local_session.merge(record)
                    local_session.merge(entry)
                    local_session.merge(new_entry)
            local_session.commit()
        local_session.close()

    def extract_current_serials(self, session):
        """
        At login, populates the dict of dicts keeping track of the current highest serial for all transactions
        :return:
        """
        self.serials = dict()

        for table in Acd.Base.metadata.tables:
            if table != "journal_entries" and not table.endswith("_history"):
                self.serials.update({table: dict()})
                mapped_class = get_class_by_table_name(table)
                for base in self.local_bases:
                    highest = AlchemyGeneric.get_highest_serial(session, mapped_class, base.code)
                    self.serials[table].update({base.code: highest})

    def sync_down(self):
        """
        Syncing the latest data from remote as available / at set intervals.
        :return:
        """
        local_session = SessionLocal()
        current_cursor = AlchemyGeneric.get_highest_synced_sync_entry(local_session)
        local_session.close()

        remote_session = SessionRemote()
        entries, records = AlchemyRemote.get_updates(remote_session,
                                                     current_cursor,
                                                     self.local_bases,
                                                     self.local_job_contracts)
        remote_session.close()

        if entries and records:
            process_downloaded_updates(entries, records)

            # self.rebase_queued_updates()


def process_downloaded_updates(entries, records):
    """Records updates from the main DB as-is.

    :param entries: the Acd.SyncJournal objects pointing to records to process
    :param records: the records themselves; various types depending on AlchemyClassDefs object
    :return:
    :rtype : object
    """
    # hundred_percent = len(updates)  # Preparing for progress bar...
    down_sync_status = "success"
    result = ""
    local_session = SessionLocal()
    remote_session = SessionRemote()
    for entry in entries:
        record_to_process = None
        for record in records:
            if record.code == entry.key:
                record_to_process = records.pop(record)
        if entry.type == "create":
            result, = AlchemyGeneric.add(local_session, record_to_process)
        elif entry.type == "update":
            result, = AlchemyGeneric.merge(local_session, record_to_process)
        elif entry.type == "delete":
            result, = AlchemyGeneric.delete(local_session, record_to_process)
        AlchemyGeneric.add(local_session, entry)
        if result != "ok":

            down_sync_status = "error"
    remote_session.close()
    return down_sync_status


def submit_updates_for_upload(entries):
    """
    Tries an optimistic upload of unsubmitted updates.
    :param entries:
    :return: synchronization result : success, error or conflict (needs to rebase)
    """
    upward_sync_status = "success"
    local_session = SessionLocal()
    deletion_session = SessionLocal()
    remote_session = SessionRemote()
    versioned_session(remote_session)
    for entry in entries:
        timestamp = datetime.datetime.utcnow()

        # The process only tries to upload "unsubmitted" updates.
        # If it fails, the entry stays in the queue for rebasing.
        # During rebase the entry's status will be set to "modified" to avoid double-upload
        if entry.status == "UNSUBMITTED":

            # Fetch the record to process and make the candidate for upload
            record_class = get_class_by_table_name(entry.table)
            record = AlchemyGeneric.get_from_primary_key(local_session, record_class, entry.key)
            record_copy = record.copy()
            record_copy.code = record_copy.code.lstrip("TMP-")

            # Actually try and make the changes to remote
            if entry.type == "create":
                result, timestamp = AlchemyGeneric.add(remote_session, record_copy)
            elif entry.type == "update":
                result, timestamp = AlchemyGeneric.merge(remote_session, record_copy)
            elif entry.type == "delete":
                result, timestamp = AlchemyGeneric.delete(remote_session, record_copy)

            # If everything went OK mark the local RECORD for deletion.
            #  It will be copied into remote and the final version will be downloaded at sync_down
            if result == "ok":
                entry.status = "ACCEPTED"
                AlchemyGeneric.delete(deletion_session, record)
            elif result == "dupe":
                upward_sync_status = "conflict"
            elif result == "err":
                upward_sync_status = "error"

            entry.processed_timestamp = timestamp
            local_session.merge(entry)

        # This part is for entries of any status.
        # Queue up sync entries for remote record and delete the local version.
        entry_copy = entry.copy()
        entry_copy.serial = None
        result1, = AlchemyGeneric.add(remote_session, entry_copy)
        result2, = AlchemyGeneric.delete(deletion_session, entry)
        if result1 == result2 == "ok":
            pass
        else:
            upward_sync_status = "error"

    # commit changes to local entries (for the ones that did not upload directly)
    local_session.commit()

    # If everything uploaded correctly, delete local queue and temp records and commit remote changes.
    if upward_sync_status == "success":
        deletion_session.commit()
        remote_session.commit()
    else:
        logger.critical(_("An error occured while trying to upload current sync queue"))
        deletion_session.commit()
        remote_session.rollback()

    deletion_session.close()
    local_session.close()
    remote_session.close()

    return upward_sync_status


def get_action_description(action_id, language):
    local_session = SessionLocal()
    action_desc = AlchemyLocal.get_action_description(local_session, action_id, language)
    local_session.close()
    return action_desc


def get_user_count(base_code):
    remote_session = SessionRemote()
    count = AlchemyRemote.user_count(remote_session, base_code)
    remote_session.close()
    return count


def ping_local(location):
    """
    Checks if the local DB path points to a H3 database
    :param location:
    :return:
    """
    # TODO: check that file creation works / change detection of absent file through IOError. OS.access is the one
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


def build_key(record):
    """
    Builds a human-readable primary key out of the serial and meta fields of the record.
    Global records have base = GLOBAL and will not have this prefix
    Permanent records (never archived) have period = PERMANENT and the year / quarter etc will not appear
    Examples : SHB-REQUISITION-2015-172 , USER-324
    :param record:
    :return:
    """
    mapper = sqlalchemy.inspect(record).mapper
    base = record.base.join("-") if record.base != 'BASE-1' else ''
    period = record.period.join("-") if record.period != 'PERMANENT' else ''
    code = "{base}{prefix}-{period}{serial}".format(base=base,
                                                    prefix=mapper.class_.prefix,
                                                    period=period,
                                                    serial=record.serial)
    return code


def build_user_pack(session, user_code):
    """
    Get everything related to a given job contract, to populate the local DB.
     - bases the user can see, most importantly the top one referenced in the JC
     - job and user which are linked to the JC
     - The Actions that are referenced by the active JC
     - The Assigned Actions linking actions with the JC

    :param session:
    :return:
    """
    records = list()

    # jc_branch = session.Query(Acd.JobContract,
    #                           Acd.WorkBase,
    #                           Acd.User,
    #                           Acd.Job,
    #                           Acd.AssignedAction,
    #                           Acd.Action)\
    #     .filter(Acd.JobContract.code == job_contract)\
    #     .filter(Acd.WorkBase.code == Acd.JobContract.base)\
    #     .filter(Acd.User.code == Acd.JobContract.user)\
    #     .filter(Acd.Job.code == Acd.JobContract.job_code)\
    #     .filter(Acd.AssignedAction.assigned_to == Acd.JobContract.code)\
    #     .filter(Acd.Action.code == Acd.AssignedAction.action)\
    #     .all()

    user = AlchemyGeneric.get_from_primary_key(session, Acd.User, user_code)
    job_contract = AlchemyGeneric.get_current_job_contract(session, user)
    job = AlchemyGeneric.get_from_primary_key(session, Acd.Job, job_contract.job_code)

    records.append(user)
    records.append(job)
    records.append(job_contract)

    action_pairs = AlchemyGeneric.get_assigned_actions(session, job_contract)
    for assigned_action, action in action_pairs:
        records.append(action)
        records.append(assigned_action)
    return records


def build_base_pack(session, base_pkey):
    records = list()

    work_base = AlchemyGeneric.get_from_primary_key(session, Acd.WorkBase, base_pkey)
    records.append(work_base)

    return records
