__author__ = 'Man'

import datetime
import logging
import hashlib

import sqlalchemy
import sqlalchemy.exc
import sqlalchemy.orm
import sqlalchemy.engine
import sqlalchemy.engine.url
from sqlalchemy.event import listen

from . import AlchemyClassDefs as Acd

SessionLocal = sqlalchemy.orm.sessionmaker()
logger = logging.getLogger(__name__)


class H3AlchemyLocalDB:
    """
    Handles the interaction with the local DB, here SQLite but could be swapped out for any other backend.
    """

    def __init__(self, location):
        """
        Builds the local DB engine on SQLite. The local engine is always running and connected.
        Additional checks when accessing data ensure the current user is still authorized.
        :param location: the path to the SQLite database file
        :return:
        """
        self.location = location
        if self.location:
            self.engine = sqlalchemy.create_engine('sqlite+pysqlite:///{address}'
                                                   .format(address=self.location))
            SessionLocal.configure(bind=self.engine)
            listen(self.engine, 'connect', self.activate_foreign_keys)

    @staticmethod
    def activate_foreign_keys(db_api_connection, connection_record):
        """
        A recipe to make SQLite honor foreign key constraints, called on each connection.
        :param db_api_connection: passed by the listen() call
        :param connection_record: necessary for the dialect to accept.
        :return:
        """
        cursor = db_api_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @staticmethod
    def login(username, password):
        """
        App-level, local login.
        :param username:
        :param password:
        :return:
        """
        session = SessionLocal()
        hashed_pass = hashlib.md5((password + username).encode(encoding='ascii')).hexdigest()
        try:
            user = session.query(Acd.User) \
                          .filter(Acd.User.login == username,
                                  Acd.User.pw_hash == hashed_pass) \
                          .one()
            logger.debug(_("Successfully logged in with the pair {user} / {password}")
                         .format(user=username, password=hashed_pass))
            return True
        except sqlalchemy.exc.SQLAlchemyError:
            logger.debug(_("Impossible to login with the pair {user} / {password}")
                         .format(user=username, password=hashed_pass))
            return False

    @staticmethod
    def get_user(username):
        """
        Pull a specific user from the list.
        :param username:
        :return:
        """
        session = SessionLocal()
        try:
            user = session.query(Acd.User) \
                          .filter(Acd.User.login == username) \
                          .one()
            logger.debug(_("User {user} found in local DB.")
                         .format(user=username))
            return user
        except sqlalchemy.exc.SQLAlchemyError:
            logger.debug(_("User {user} not found in local DB.")
                         .format(user=username))
            return False

    @staticmethod
    def get_base(base_code):
        """
        Pull a specific user from the list.
        :return:
        """
        session = SessionLocal()
        try:
            base = session.query(Acd.WorkBase) \
                .filter(Acd.WorkBase.code == base_code) \
                .one()
            logger.debug(_("Base {base} found in local DB.")
                         .format(base=base_code))
            return base
        except sqlalchemy.exc.SQLAlchemyError:
            logger.debug(_("Base {base} not found in local DB.")
                         .format(base=base_code))
            return False

    @staticmethod
    def get_current_job_contract(username):
        """
        Finds the user's current job.
        :param username: A User object to get details from
        :return:
        """
        try:
            session = SessionLocal()
            current_job = session.query(Acd.JobContract) \
                .filter(Acd.JobContract.user == username) \
                .filter(Acd.JobContract.start_date <= datetime.date.today(),
                        Acd.JobContract.end_date >= datetime.date.today()) \
                .one()
            logger.debug(_("Active job found in local for user {name} : {job} - {title}")
                         .format(name=username, job=current_job.job_code, title=current_job.job_title))
            return current_job
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info(_("No active jobs found in local for user {name}")
                        .format(name=username))
            return None
        except sqlalchemy.orm.exc.MultipleResultsFound:
            logger.error(_("Multiple active jobs found in local for user {name} !")
                         .format(name=username))

    @staticmethod
    def read_table(class_of_table):
        """
        Reads a whole table, returning a list of its objects (records)
        :param class_of_table:
        :return:
        """
        try:
            session = SessionLocal()
            table = session.query(class_of_table).all()
            logger.debug(_("Successfully read table {table} from local")
                         .format(table=class_of_table))
            return table
        except sqlalchemy.exc.SQLAlchemyError:
            logger.error(_("Failed to read table {table} from local")
                         .format(table=class_of_table))
            return False

    @staticmethod
    def put(records):
        """
        Merges (insert or updates) a record or records into the local db
        :param records:
        :return:
        """
        try:
            session = SessionLocal()
            for row in records:
                session.merge(row)
            session.commit()
            logger.debug(ngettext("Successfully inserted record {records}",
                                  "Successfully inserted records in {records}",
                                  len(records))
                         .format(records=records))
            return True
        except sqlalchemy.exc.SQLAlchemyError as exc:
            print(exc)
            logger.error(ngettext("Failed to insert record {records}",
                                  "Failed to insert records in {records}",
                                  len(records))
                         .format(records=records))
            return False

    def init_public_tables(self):
        """
        Formats the local database with the public tables.
        :return:
        """
        try:
            meta = Acd.Base.metadata
            meta.create_all(bind=self.engine)
            logger.info(_('all tables created in local'))
            return True
        except sqlalchemy.exc.SQLAlchemyError:
            logger.error(_('failed to create local public tables'))
            return False

    def has_a_base(self):
        """
        If there's at least one base in this DB (ie this is a valid H3 DB) will return True.
        :return:
        """
        try:
            session = SessionLocal()
            if session.query(Acd.WorkBase).count() > 0:
                logger.debug(_("Local DB at location {location} has at least one base")
                             .format(location=self.location))
                return True
            else:
                logger.debug(_("Local DB at location {location} has no bases")
                             .format(location=self.location))
                return False
        except sqlalchemy.exc.SQLAlchemyError:
            logger.debug(_("Unable to query local DB at location {location}")
                         .format(location=self.location))
            return False

    def get_local_bases(self):
        """
        Queries the local DB for job contracts stored in local DB, extracting the current bases
        :return: list of bases
        """
        try:
            session = SessionLocal()
            job_contracts = session.query(Acd.JobContract) \
                .group_by(Acd.JobContract.base) \
                .all()
            unique_bases = list()
            for job_contract in job_contracts:
                unique_bases.append(job_contract.base)
            logger.debug(_("List of bases in local DB : {list}")
                         .format(list=str(unique_bases)))
            return unique_bases
        except sqlalchemy.exc.SQLAlchemyError:
            logger.warning(_("Unable to query local DB at location {location} for local bases")
                           .format(location=self.location))
            return False

    @staticmethod
    def get_contract_actions(job_contract):
        try:
            session = SessionLocal()
            actions = session.query(Acd.ContractAction) \
                .filter(Acd.ContractAction.contract == job_contract.auto_id) \
                .all()
            return actions
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Unable to query local DB for actions linked to contract {id}")
                             .format(id=job_contract.auto_id))
            return False

    @staticmethod
    def get_current_delegations(job_contract):
        try:
            session = SessionLocal()
            delegations = session.query(Acd.Delegation) \
                .filter(Acd.Delegation.delegated_to == job_contract.auto_id) \
                .filter(Acd.Delegation.start_date <= datetime.date.today(),
                        Acd.Delegation.end_date >= datetime.date.today()) \
                .all()
            return delegations
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Unable to query local DB for delegations given to contract {id}")
                             .format(id=job_contract.auto_id))
            return False

    @staticmethod
    def get_action_descriptions(action_id, lang):
        try:
            session = SessionLocal()
            description = session.query(Acd.Action) \
                .filter(Acd.Action.code == action_id, Acd.Action.language == lang) \
                .one()
            return description
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Error while trying to fetch {lang} description for Action {action_id}")
                             .format(lang=lang, action_id=action_id))

    @staticmethod
    def get_last_synced_entry(public=False):
        try:
            session = SessionLocal()
            if public:
                latest = session.query(Acd.SyncJournal) \
                    .filter(Acd.SyncJournal.auto_id == sqlalchemy.func.max(Acd.SyncJournal.auto_id)) \
                    .filter(Acd.SyncJournal.table.in_(["bases", "jobs", "actions"])) \
                    .one()
            else:
                latest = session.query(Acd.SyncJournal) \
                    .filter(Acd.SyncJournal.auto_id == sqlalchemy.func.max(Acd.SyncJournal.auto_id)) \
                    .one()
            return latest.auto_id
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info(_("No sync entries in local, returning 1 to query all updates"))
            return 1
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception((_("Error while getting the newest sync entry")))
