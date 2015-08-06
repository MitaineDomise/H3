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
        App-level login.
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
        finally:
            session.close()

    @staticmethod
    def get_from_primary_key(mapped_class, p_key):
        mapper = sqlalchemy.inspect(mapped_class)
        assert len(mapper.primary_key) == 1
        primary = mapper.primary_key[0]
        session = SessionLocal()
        try:
            record = session.query(mapped_class).filter(primary == p_key).one()
            return record
        except sqlalchemy.exc.SQLAlchemyError:
            logger.error(_("Failed to get object of type {cls} with primary key {key}")
                         .format(cls=mapped_class, key=p_key))
        finally:
            session.close()

    @staticmethod
    def get_current_job_contract(username):
        """
        Finds the user's current job.
        :param username: A User object to get details from
        :return:
        """
        session = SessionLocal()
        try:
            current_job = session.query(Acd.JobContract) \
                .filter(Acd.JobContract.user == username) \
                .filter(Acd.JobContract.start_date <= datetime.date.today(),
                        Acd.JobContract.end_date >= datetime.date.today()) \
                .one()
            logger.debug(_("Active joor user {name} : {job} - {title}")
                         .format(name=username, job=current_job.job_code, title=current_job.job_title))
            return current_job
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info(_("No active jobor user {name}")
                        .format(name=username))
            return None
        except sqlalchemy.orm.exc.MultipleResultsFound:
            logger.error(_("Multiple active jobs found for user {name} !")
                         .format(name=username))
        finally:
            session.close()

    @staticmethod
    def read_table(class_of_table):
        """
        Reads a whole table, returning a list of its objects (records)
        :param class_of_table:
        :return:
        """
        session = SessionLocal()
        try:
            table = session.query(class_of_table).all()
            logger.debug(_("Successfully read table {table}")
                         .format(table=class_of_table))
            return table
        except sqlalchemy.exc.SQLAlchemyError:
            logger.error(_("Failed to read table {table}")
                         .format(table=class_of_table))
            return False
        finally:
            session.close()

    @staticmethod
    def add(record):
        """
        Adds (inserts) a record into the db.
        Should be used for new records.
        :param record:
        :return:
        """
        session = SessionLocal()
        try:
            session.add(record)
            session.commit()
            logger.debug(_("Successfully inserted record {record}")
                         .format(record=record))
            return True
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to insert record {record}")
                             .format(record=record))
            return False
        finally:
            session.close()

    @staticmethod
    def merge(record):
        """
        Merges (updates) a record into the db.
        Shouldn't be used for new records.
        :param record:
        :return:
        """
        session = SessionLocal()
        try:
            session.merge(record)
            session.commit()
            logger.debug(_("Successfully merged record {record}")
                         .format(record=record))
            return True
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to merge record {record}")
                             .format(record=record))
            return False
        finally:
            session.close()

    @staticmethod
    def delete(record):
        """
        deletes a record from the db
        :param record:
        :return:
        """
        session = SessionLocal()
        try:
            for record in record:
                session.delete(record)
            session.commit()
            logger.debug(_("Successfully deleted record {record}")
                         .format(record=record))
            return True
        except sqlalchemy.exc.SQLAlchemyError as exc:
            print(exc)
            logger.error(_("Failed to delete record {record}")
                         .format(record=record))
            return False
        finally:
            session.close()

    def create_all_tables(self):
        """
        Formats the database with the public tables.
        :return:
        """
        try:
            meta = Acd.Base.metadata
            meta.create_all(bind=self.engine)
            logger.info(_('all tables created'))
            return True
        except sqlalchemy.exc.SQLAlchemyError:
            logger.error(_('failed to create all tables'))
            return False

    def has_a_base(self):
        """
        If there's at least one base in this DB (ie this is a valid H3 DB) will return True.
        :return:
        """
        session = SessionLocal()
        try:
            if session.query(Acd.WorkBase).count() > 0:
                logger.debug(_("DB at location {location} has at least one base")
                             .format(location=self.location))
                return True
            else:
                logger.debug(_("DB at location {location} has no bases")
                             .format(location=self.location))
                return False
        except sqlalchemy.exc.SQLAlchemyError:
            logger.debug(_("Unable to query DB at location {location}")
                         .format(location=self.location))
            return False
        finally:
            session.close()

    def get_local_bases(self):
        """
        Queries the DB for job contracts, extracting the current bases
        :return: list of bases
        """
        session = SessionLocal()
        try:
            job_contracts = session.query(Acd.JobContract) \
                .group_by(Acd.JobContract.base) \
                .all()
            unique_bases = list()
            for job_contract in job_contracts:
                unique_bases.append(job_contract.base)
            logger.debug(_("List of bases in DB : {list}")
                         .format(list=str(unique_bases)))
            return unique_bases
        except sqlalchemy.exc.SQLAlchemyError:
            logger.warning(_("Unable to query DB at location {location} for bases")
                           .format(location=self.location))
            return False
        finally:
            session.close()

    @staticmethod
    def get_contract_actions(job_contract):
        session = SessionLocal()
        try:
            actions = session.query(Acd.ContractAction) \
                .filter(Acd.ContractAction.contract == job_contract.code) \
                .all()
            return actions
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Unable to query DB for actions linked to contract {id}")
                             .format(id=job_contract.code))
            return False
        finally:
            session.close()

    @staticmethod
    def get_current_delegations(job_contract):
        session = SessionLocal()
        try:
            delegations = session.query(Acd.Delegation) \
                .filter(Acd.Delegation.delegated_to == job_contract.code) \
                .filter(Acd.Delegation.start_date <= datetime.date.today(),
                        Acd.Delegation.end_date >= datetime.date.today()) \
                .all()
            return delegations
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Unable to query DB for delegations given to contract {id}")
                             .format(id=job_contract.code))
            return False
        finally:
            session.close()

    @staticmethod
    def get_action_descriptions(action_id, lang):
        session = SessionLocal()
        try:
            description = session.query(Acd.Action) \
                .filter(Acd.Action.code == action_id, Acd.Action.language == lang) \
                .one()
            return description
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Error while trying to fetch {lang} description for Action {action_id}")
                             .format(lang=lang, action_id=action_id))
        finally:
            session.close()

    @staticmethod
    def get_last_synced_entry():
        session = SessionLocal()
        try:
            latest = session.query(Acd.SyncJournal) \
                .filter(Acd.SyncJournal.serial > 0) \
                .filter(Acd.SyncJournal.serial == sqlalchemy.func.max(Acd.SyncJournal.serial)) \
                .one()
            return latest.code
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info(_("No sync entries in local, returning 0 to query all updates"))
            return 0
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Error while getting the newest sync entry"))
        finally:
            session.close()

    @staticmethod
    def get_highest_serial(mapped_class, work_base=None):
        session = SessionLocal()
        try:
            if work_base:
                latest = session.query(mapped_class) \
                    .filter(mapped_class.serial > 0) \
                    .filter(mapped_class.base == work_base,
                            mapped_class.serial == sqlalchemy.func.max(mapped_class.serial)) \
                    .one()
            else:
                latest = session.query(mapped_class) \
                    .filter(Acd.SyncJournal.serial > 0) \
                    .filter(Acd.SyncJournal.serial == sqlalchemy.func.max(Acd.SyncJournal.serial)) \
                    .one()
            return latest.serial
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info(_("No entries for this class, serial defaulted to 0"))
            return 0
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Error getting the highest serial for class {cls}")
                             .format(cls=mapped_class))
        finally:
            session.close()

    @staticmethod
    def get_update_queue():
        session = SessionLocal()
        try:
            updates = session.query(Acd.SyncJournal) \
                .filter(Acd.SyncJournal.serial < 0) \
                .order_by(Acd.SyncJournal.serial.desc()) \
                .all()
            return updates
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception((_("Error while getting the unsubmitted sync entries")))
        finally:
            session.close()
