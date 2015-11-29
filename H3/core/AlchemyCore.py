__author__ = 'Man'

import configparser
import logging
import datetime
import os
import json

import sqlalchemy.orm
import sqlalchemy.exc

from . import AlchemyLocal, AlchemyRemote, AlchemyGeneric
from . import AlchemyClassDefs as Acd
from .AlchemyTemporal import versioned_session
from ..XLLent import export

logger = logging.getLogger(__name__)

class H3AlchemyCore:
    """
    This is the central module for data manipulation. Now relies on SQLAlchemy's ORM.
    """
    def __init__(self):
        """
        Creates the values and objects used throughout a user session.
        """

        self.SessionRemote = sqlalchemy.orm.sessionmaker()
        self.SessionLocal = sqlalchemy.orm.sessionmaker()
        
        self.local_db = AlchemyLocal.H3AlchemyLocalDB(None)
        self.remote_db = AlchemyRemote.H3AlchemyRemoteDB(None)

        self.internal_state = dict({"user": "", "base": ""})

        self.current_job_contract = Acd.JobContract()
        self.current_job_contract = None

        self.local_bases = list()
        self.local_job_contracts = list()

        self.assigned_actions = list()

        self.language = "en_UK"

        self.options = configparser.ConfigParser()

    def clear_variables(self):
        self.internal_state = dict({"user": "", "base": ""})

        self.local_bases = list()
        self.local_job_contracts = list()

        self.assigned_actions = list()

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
                if ping_local(temp_local_db_location) == "H3DB":
                    self.local_db = AlchemyLocal.H3AlchemyLocalDB(temp_local_db_location)
                    self.SessionLocal.configure(bind=self.local_db.engine)
                    if self.options.has_option('H3 Options', 'current user'):
                        username = self.options.get('H3 Options', 'current user')
                        local_session = self.SessionLocal()
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
        self.SessionLocal.configure(bind=self.local_db.engine)
        self.local_db.create_all_tables()

        self.remote_db = AlchemyRemote.H3AlchemyRemoteDB(remote)
        self.remote_db.login('reader', 'weak')
        self.SessionRemote.configure(bind=self.remote_db.engine)

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
        local_session = self.SessionLocal()
        user = AlchemyGeneric.get_user_from_login(local_session, username)
        local_bases_list = AlchemyLocal.get_local_bases(local_session)
        local_session.close()
        if user:
            self.internal_state["user"] = "local"
            self.update_user_status(user)
            logger.info(_("User {name} found in local")
                        .format(name=user.login))
        else:
            remote_session = self.SessionRemote()
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
        remote_session = self.SessionRemote()
        local_session = self.SessionLocal()

        records = list()

        if self.internal_state["user"] == "ok":
            pass
        else:
            if self.internal_state["base"] == "new":
                # TODO: adding all sub-bases, no archives. Use admin tools to download updates for those.
                records.extend(build_base_pack(remote_session, self.current_job_contract.work_base))

            if self.internal_state["user"] == "remote":
                records.extend(build_user_pack(remote_session, self.current_job_contract.user))

        latest_sync_serial = AlchemyGeneric.get_highest_synced_sync_serial(remote_session)
        latest_sync_entry = AlchemyGeneric.get_from_primary_key(remote_session, Acd.SyncJournal, latest_sync_serial)
        records.append(latest_sync_entry)
        remote_session.close()

        AlchemyGeneric.merge_multiple(local_session, records)
        local_session.commit()

        self.local_bases = AlchemyLocal.get_local_bases(local_session)
        self.local_job_contracts = AlchemyLocal.get_local_users(local_session)

        local_session.close()

    # Login functions

    def log_off(self):
        """
        Kills the remote DB engine
        :return:
        """
        if self.remote_db.engine:
            self.remote_db.engine.dispose()

    def login(self, username, password):
        self.local_login(username, password)
        self.remote_login(username, password)

    def local_login(self, username, password):
        """
        Logs in at app-level, in the local DB.
        """
        local_session = self.SessionLocal()
        logged_user = AlchemyLocal.login(local_session, username, password)
        if logged_user:
            self.update_user_status(logged_user)
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
        self.SessionRemote.configure(bind=self.remote_db.engine)

    def remote_pw_change(self, username, old_pass, new_pass):
        self.remote_db.login(username, old_pass)
        self.SessionRemote.configure(bind=self.remote_db.engine)
        remote_session = self.SessionRemote()
        result = self.remote_db.update_pass(remote_session, username, old_pass, new_pass)
        if result:
            remote_session.commit()
        else:
            remote_session.rollback()
        remote_session.close()
        if result:
            if self.remote_db.login(username, new_pass):
                self.SessionRemote.configure(bind=self.remote_db.engine)
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

        local_session = self.SessionLocal()
        self.current_job_contract = AlchemyGeneric.get_current_job_contract(local_session, user)

        if self.current_job_contract:
            self.local_bases = AlchemyLocal.get_local_bases(local_session)
            if self.current_job_contract.base not in self.local_bases:
                logger.error(_("User {name} is currently affected to a base which isn't part of the local DB.")
                             .format(name=user.login))
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
        local_session = self.SessionLocal()
        action_pairs = AlchemyGeneric.get_assigned_actions(local_session, self.current_job_contract)
        local_session.close()
        for assigned_action, _throwaway in action_pairs:
            self.assigned_actions.append(assigned_action)

    def create_base(self, base):
        """
        Prepares the record and sync entry to submit to local DB
        :param base:
        :return:
        """
        local_session = self.SessionLocal()
        # self.get_authorizations('create_base', local_session)
        record_incrementer(base, local_session)
        code_builder(base)

        sync_entry = self.prepare_sync_entry(base, local_session, "CREATE")

        try:
            local_session.add(base)
            local_session.add(sync_entry)
            local_session.commit()
            return "OK"
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to create base"))
            local_session.rollback()
            return "ERR"
        finally:
            local_session.close()

    def update_base(self, base):
        """
        Prepares the record and sync entry to submit to local DB
        :param base:
        :return:
        """
        local_session = self.SessionLocal()
        # Check for cycles (can't make base child of its own child)
        for child in AlchemyGeneric.subtree(local_session, base.code):
            if base.parent == child:
                return "ERR"

        sync_entry = self.prepare_sync_entry(base, local_session, "UPDATE")

        try:
            local_session.merge(base)
            local_session.add(sync_entry)
            local_session.commit()
            return "OK"
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to update base"))
            local_session.rollback()
            return "ERR"
        finally:
            local_session.close()

    def prepare_sync_entry(self, record, session, entry_type):
        sync_entry = Acd.SyncJournal(serial=AlchemyLocal.get_lowest_queued_sync_entry(session) - 1,
                                     origin=self.current_job_contract.code,
                                     type=entry_type,
                                     table=sqlalchemy.inspect(record).class_.__tablename__,
                                     key=record.code,
                                     status="UNSUBMITTED",
                                     local_timestamp=datetime.datetime.utcnow())
        return sync_entry

    def sync_up(self):
        """
        Sends unsubmitted (negative) sync entries to remote DB.
        Should work first time on most cases; if there is a conflict, calls a rebase to solve it and resubmits.
        :return:
        """
        logger.debug(_("Sync up start"))

        local_session = self.SessionLocal()
        remote_session = self.SessionRemote()
        versioned_session(remote_session)
        result = attempt_upload(local_session, remote_session)

        if result == "error":
            local_session.rollback()
            remote_session.rollback()
            logger.critical(_("Upward sync failed, inspect queue"))
        elif result == "dupe":
            local_session.rollback()
            remote_session.rollback()
            if self.rebase_sync_down(local_session, remote_session, conflict=True) == "success":
                local_session.commit()
                remote_session.commit()
                local_session.close()
                remote_session.close()
                self.sync_up()
            else:
                logger.critical(_("Upload and rebase both fail, inspect queue"))
        elif result == "success":
            local_session.commit()
            remote_session.commit()
            if self.rebase_sync_down(local_session, remote_session) == "success":
                local_session.commit()
                remote_session.commit()
            else:
                logger.error(_("Sync up succeeded but error downloading updates"))
        local_session.close()
        remote_session.close()
        logger.debug(_("Sync end"))

    def rebase_sync_down(self, local_session, remote_session, conflict=False):
        """
        :return:
        """
        logger.debug(_("Sync down start"))
        remote_entries, remote_records = AlchemyRemote \
            .get_updates(remote_session,
                         AlchemyGeneric.get_highest_synced_sync_serial(local_session),
                         self.local_bases,
                         self.local_job_contracts)

        if remote_entries and remote_records:
            pass
        else:
            return "no_new_updates"

        result = "success"
        if conflict:
            logger.debug(_("Starting rebase"))
            # Build a dict (of dicts) of the maximum serial created in the pending downloaded updates
            # it's of the form {table1: {base1: x, base2: y...}, ...}
            top_serials = dict()
            for r_entry, r_record in zip(remote_entries, remote_records):
                if r_entry.type == "CREATE":
                    if r_entry.table not in top_serials.keys():
                        top_serials.update({r_entry.table: dict()})
                    if r_record.base not in top_serials[r_entry.table].keys():
                        top_serials[r_entry.table].update({r_record.base: 0})
                    if r_record.serial > top_serials[r_entry.table][r_record.base]:
                        top_serials[r_entry.table][r_record.base] = r_record.serial

            # shift CREATE queue entries forward, to make space for the pending downloaded ones
            # note : they're all unsubmitted
            queue = AlchemyLocal.get_sync_queue(local_session)
            records_to_rebase = list()
            with local_session.no_autoflush:
                try:
                    for queue_entry in queue:
                        # if this journal entry is part of the tables affected by remote creation
                        if queue_entry.table in top_serials.keys():
                            mapped_class = Acd.get_class_by_table_name(queue_entry.table)
                            record = AlchemyGeneric.get_from_primary_key(local_session, mapped_class, queue_entry.key)
                            top_serials[queue_entry.table][record.base] += 1

                            # defer the actual rebasing because multiple simultaneous updates have a way of colliding
                            unit = list()
                            unit.append(top_serials[queue_entry.table][record.base])
                            unit.append(queue_entry)
                            unit.append(record)
                            records_to_rebase.append(unit)

                    records_to_rebase.reverse()
                    for record_to_rebase in records_to_rebase:
                        # 0 = serial to apply, 1 = entry, 2 = record
                        record_to_rebase[2].serial = record_to_rebase[0]
                        code_builder(record_to_rebase[2])
                        record_to_rebase[1].key = record_to_rebase[2].code
                        local_session.merge(record_to_rebase[2])
                        local_session.flush()
                except sqlalchemy.exc.SQLAlchemyError:
                    logger.exception(_("Error rebasing updates"))
                    result = "rebase_error"
        if result == "success":
            result = process_downloaded_updates(remote_entries, remote_records, local_session)

        return result

    def export_bases(self):
        local_session = self.SessionLocal()
        bases = AlchemyGeneric.read_table(local_session, Acd.WorkBase)
        local_session.close()
        filename = export.bases_writer(bases)
        return filename

    def get_queue(self):
        local_session = self.SessionLocal()
        return AlchemyLocal.get_sync_queue(local_session)

    def read_table(self, class_of_table, location="local"):
        session = self.SessionLocal()
        if location == "remote":
            session = self.SessionRemote()
        table = AlchemyGeneric.read_table(session, class_of_table)
        session.close()
        return table

    def get_user_count(self, base_code, location="local"):
        session = self.SessionLocal()
        if location == "remote":
            session = self.SessionRemote()
        count = AlchemyGeneric.user_count(session, base_code)
        session.close()
        return count

    def get_from_primary_key(self, mapped_class, pkey, location="local"):
        session = self.SessionLocal()
        if location == "remote":
            session = self.SessionRemote()
        record = AlchemyGeneric.get_from_primary_key(session, mapped_class, pkey)
        session.close()
        return record


def open_exported(filename):
    """
    This is windows-only at the moment
    :param filename:
    :return:
    """
    try:
        os.startfile(filename)
    except OSError:
        logger.exception(_("Operation is not supported in this system"))

def code_builder(record):
    """
    Builds a human-readable primary key out of the serial and meta fields of the record.
    Global records have base = GLOBAL and will not have this prefix
    Permanent records (never archived) have period = PERMANENT and the year / quarter etc will not appear
    Examples : SHB-REQUISITION-2015-172 , USER-324
    """
    mapper = sqlalchemy.inspect(record).mapper
    base = record.base.join("-") if record.base != 'BASE-1' else ''
    period = record.period.join("-") if record.period != 'PERMANENT' else ''
    record.code = "{base}{prefix}-{period}{serial}".format(base=base,
                                                           prefix=mapper.class_.prefix,
                                                           period=period,
                                                           serial=record.serial)


def process_downloaded_updates(entries, records, local_session):
    """Records updates from the main DB as-is.

    :param entries: the Acd.SyncJournal objects pointing to records to process
    :param records: the records themselves; various types depending on AlchemyClassDefs object
    :return:
    :rtype : object
    """
    down_sync_status = "success"
    final_entry = None

    if entries and records:
        for entry, record in zip(entries, records):
            try:
                Acd.detach(record)
                if entry.type == "CREATE":
                    local_session.add(record)
                elif entry.type == "UPDATE":
                    local_session.merge(record)
                elif entry.type == "DELETE":
                    local_session.delete(record)
                local_session.flush()
            except sqlalchemy.exc.SQLAlchemyError:
                logger.exception(_("Failed to process downloaded update {type} {code}")
                                 .format(type=entry.type, code=record.code))
                down_sync_status = "error"
            final_entry = entry
            Acd.detach(final_entry)
        local_session.add(final_entry)
        local_session.query(Acd.SyncJournal) \
            .filter(Acd.SyncJournal.serial > 0,
                    Acd.SyncJournal.serial < final_entry.serial,
                    Acd.SyncJournal.local_timestamp < datetime.datetime.utcnow() - datetime.timedelta(days=1)) \
            .delete()
        local_session.flush()
    return down_sync_status


def attempt_upload(local_session, remote_session):
    """
    Tries an optimistic upload of unsubmitted updates.
    :return: synchronization result : success, error or conflict (needs to rebase)
    """
    upward_sync_status = "success"

    entries = AlchemyLocal.get_sync_queue(local_session)

    records = list()
    # load all records that need to be processed. Keep them attached to maintain integrity.
    if entries:
        for entry in entries:
            mapped_class = Acd.get_class_by_table_name(entry.table)
            record = AlchemyGeneric.get_from_primary_key(local_session, mapped_class, entry.key)
            records.append(record)

    if records:
        # Detach records so their dependants don't get processed at the same time when pasted to the remote session
        # This is a consequence of the default cascade behaviour
        for record in records:
            Acd.detach(record)

        to_be_deleted = list()

        try:
            for entry, record in zip(entries, records):
                timestamp = None
                journal_serial = AlchemyGeneric.get_highest_synced_sync_serial(remote_session)

                if entry.status == "UNSUBMITTED":
                    # Get a timestamp from the server and actually try and make the changes to remote
                    if entry.type == "CREATE":
                        # This needs an extra step to avoid collisions : deleting the local version, deferred
                        timestamp = remote_session.execute(sqlalchemy.func.current_timestamp()).scalar()
                        remote_session.add(record)
                        remote_session.flush()
                        to_be_deleted.append(entry)
                    elif entry.type == "UPDATE":
                        timestamp = remote_session.execute(sqlalchemy.func.current_timestamp()).scalar()
                        remote_session.merge(record)
                    elif entry.type == "DELETE":
                        timestamp = remote_session.execute(sqlalchemy.func.current_timestamp()).scalar()
                        remote_session.delete(record)

                # Manual increment of the global journal serial
                journal_serial += 1
                entry.serial = journal_serial
                entry.processed_timestamp = timestamp
                entry.status = "ACCEPTED"
                local_session.delete(entry)
                local_session.flush()
                Acd.detach(entry)
                remote_session.add(entry)
        except sqlalchemy.exc.ProgrammingError:
            # pg8000 throws a programming error upon PK conflict :(
            logger.exception(_("Encountered a conflict; rebase and try again"))
            upward_sync_status = "dupe"
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("couldn't process queued update"))
            upward_sync_status = "error"

        if upward_sync_status == "success":
            to_be_deleted.reverse()
            for entry in to_be_deleted:
                # Processed backwards to avoid foreign key errors
                mapped_class = Acd.get_class_by_table_name(entry.table)
                try:
                    local_session.query(mapped_class).filter(mapped_class.code == entry.key).delete()
                except sqlalchemy.exc.SQLAlchemyError:
                    logger.exception(_("Couldn't delete the local version of record"))

    return upward_sync_status


def json_read(data, lang, field):
    return json.loads(data)[lang][field]

def ping_local(location):
    """
    Checks if the local DB path points to a H3 database
    :param location:
    :return:
    """
    # Tests here are a bit overkill but we're usually accessing this DB file over a LAN so permissions
    # could be set wrongly etc.
    result = ""
    if location == "":
        result = "EMPTY"
    elif os.access(location, os.F_OK):  # if file exists, check it's a H3 DB
        if os.access(location, os.R_OK and os.W_OK):
            temp_local_db = AlchemyLocal.H3AlchemyLocalDB(location)
            SessionPing = sqlalchemy.orm.sessionmaker()
            SessionPing.configure(bind=temp_local_db.engine)
            local_session = SessionPing()
            if AlchemyLocal.has_a_base(local_session):
                result = "H3DB"
            else:
                result = "OTHERFILE"
            local_session.close()
        else:
            if not os.access(location, os.R_OK) and not os.access(location, os.W_OK):
                result = "NO_RW"
            elif os.access(location, os.R_OK):
                result = "NO_R"
            elif os.access(location, os.W_OK):
                result = "NO_W"
    else:  # file doesn't exist, check directory permissions
        dir = os.path.dirname(location)
        if os.access(dir, os.R_OK and os.W_OK):  # user can read and write this location
            result = "OK"
        else:
            if not os.access(dir, os.R_OK) and not os.access(dir, os.W_OK):
                result = "NO_RW"
            elif os.access(dir, os.R_OK):
                result = "NO_R"
            elif os.access(dir, os.W_OK):
                result = "NO_W"
    return result



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
    SessionInit = sqlalchemy.orm.sessionmaker()
    SessionInit.configure(bind=new_db.engine)
    remote_session = SessionInit()

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
    sub_bases = AlchemyGeneric.subtree(session, base_pkey)
    for base in sub_bases:
        work_base = AlchemyGeneric.get_from_primary_key(session, Acd.WorkBase, base)
        records.append(work_base)

    return records


def record_incrementer(record, session):
    """
    generates a new serial, for a brand new record.
    :param record:
    :return:
    """
    mapper = sqlalchemy.inspect(record).mapper
    record.serial = AlchemyGeneric.get_highest_serial(session, mapper.class_, record.base) + 1
