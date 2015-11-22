__author__ = 'Man'

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
                                                   .format(address=self.location), echo=False)
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


def get_local_users(session):
    """
    Queries the DB for job contracts
    :return: list of bases
    """
    try:
        users = session.query(Acd.JobContract).all()
        logger.debug(_("List of job contracts in DB : {list}")
                     .format(list=str(users)))

        users_list = list()
        for user in users:
            users_list.append(user.code)
        return users_list
    except sqlalchemy.exc.SQLAlchemyError:
        logger.warning(_("Unable to query Local DB for job contracts"))
        return False


def get_local_bases(session):
    """
    Queries the DB for job contracts, extracting the current bases
    :return: list of bases
    """
    try:
        bases = session.query(Acd.WorkBase).all()
        logger.debug(_("List of bases in DB : {list}")
                     .format(list=str(bases)))

        bases_list = list()
        for base in bases:
            bases_list.append(base.code)
        return bases_list
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
        entries = session.query(Acd.SyncJournal) \
            .filter(Acd.SyncJournal.serial < 0) \
            .order_by(Acd.SyncJournal.serial.desc()) \
            .all()

        return entries
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Error while getting the unsubmitted sync entries"))


def get_lowest_queued_sync_entry(session):
    try:
        min_num = session.query(sqlalchemy.func.min(Acd.SyncJournal.serial).label('min')) \
            .filter(Acd.SyncJournal.serial < 0) \
            .one()
        logger.debug(_("Lowest (latest) sync entry serial is {no}")
                     .format(no=min_num.min))
        return min_num.min or 0
    except sqlalchemy.orm.exc.NoResultFound:
        logger.info(_("No queued sync entries, defaulting to 0"))
        return 0
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Error getting the Lowest (latest) sync entry serial"))


def login(session, username, password):
    """
    App-level login.
    :param username:
    :param password:
    :return:
    """
    hashed_pass = hashlib.md5((password + username).encode(encoding='ascii')).hexdigest()
    try:
        user = session.query(Acd.User) \
            .filter(Acd.User.login == username,
                    Acd.User.pw_hash == hashed_pass) \
            .one()
        logger.debug(_("Successfully logged in with the pair {user} / {password}")
                     .format(user=username, password=hashed_pass))
        return user
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
