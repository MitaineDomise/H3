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
            listen(self.engine, 'connect', activate_foreign_keys)

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


def get_local_bases(session):
    """
    Queries the DB for job contracts, extracting the current bases
    :return: list of bases
    """
    try:
        job_contracts = session.query(Acd.JobContract) \
            .group_by(Acd.JobContract.work_base) \
            .all()
        unique_bases = list()
        for job_contract in job_contracts:
            unique_bases.append(job_contract.work_base)
        logger.debug(_("List of bases in DB : {list}")
                     .format(list=str(unique_bases)))
        return unique_bases
    except sqlalchemy.exc.SQLAlchemyError:
        logger.warning(_("Unable to query Local DB for bases"))
        return False


def has_a_base(session):
    """
    If there's at least one base in this DB (ie this is a valid H3 DB) will return True.
    :return:
    """
    try:
        if session.query(Acd.WorkBase).count() > 0:
            logger.debug(_("Local DB has at least one base"))
            return True
        else:
            logger.debug(_("Local DB has no bases"))
            return False
    except sqlalchemy.exc.SQLAlchemyError:
        logger.debug(_("Unable to query Local DB "))
        return False


def get_sync_queue(session):
    try:
        updates = session.query(Acd.SyncJournal) \
            .filter(Acd.SyncJournal.serial < 0) \
            .order_by(Acd.SyncJournal.serial.desc()) \
            .all()
        return updates
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception((_("Error while getting the unsubmitted sync entries")))


def get_highest_serial(session, mapped_class, work_base='GLOBAL'):
    try:
        max_num = session.query(sqlalchemy.func.max(mapped_class.serial).label('max')) \
            .filter(mapped_class.base == work_base) \
            .one()
        logger.debug(_("Highest serial for class {mapped} in local is {no}")
                     .format(mapped=mapped_class, no=max_num.max))
        return max_num.max if max_num.max else 0
    except sqlalchemy.orm.exc.NoResultFound:
        logger.info(_("No entries for this class, serial defaulted to 0"))
        return 0
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Error getting the highest serial for class {cls}")
                         .format(cls=mapped_class))


def get_lowest_queued_sync_entry(session):
    try:
        min_num = session.query(sqlalchemy.func.min(Acd.SyncJournal.serial).label('min')) \
            .filter(Acd.SyncJournal.serial < 0) \
            .one()
        logger.debug(_("Lowest (latest) sync entry serial is {no}")
                     .format(no=min_num.min))
        return min_num.min if min_num else 0
    except sqlalchemy.orm.exc.NoResultFound:
        logger.info(_("No queued sync entries, defaulting to 0"))
        return 0
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Error getting the Lowest (latest) sync entry serial"))


def get_action_description(session, action_id, lang):
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


def get_current_delegations(session, job_contract):
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


def get_contract_actions(session, job_contract):
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


def login(session, username, password):
    """
    App-level login.
    :param username:
    :param password:
    :return:
    """
    hashed_pass = hashlib.md5((password + username).encode(encoding='ascii')).hexdigest()
    try:
        session.query(Acd.User) \
            .filter(Acd.User.login == username,
                    Acd.User.pw_hash == hashed_pass) \
            .one()
        logger.debug(_("Successfully logged in with the pair {user} / {password}")
                     .format(user=username, password=hashed_pass))
        return True
    except sqlalchemy.orm.exc.NoResultFound:
        logger.debug(_("No matching pair for {user} / {password}")
                     .format(user=username, password=hashed_pass))
        return False
    except sqlalchemy.exc.SQLAlchemyError:
        logger.debug(_("Impossible to login with the pair {user} / {password}")
                     .format(user=username, password=hashed_pass))
        return False


# noinspection PyUnusedLocal
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
