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

import AlchemyClassDefs as Acd


SessionLocal = sqlalchemy.orm.sessionmaker()
logger = logging.getLogger(__name__)


class H3AlchemyLocalDB():
    """
    Handles the interaction with the local DB, here SQLite but could be swapped out for any other backend.
    """
    def __init__(self, core, location):
        """
        Builds the local DB engine on SQLite. The local engine is always running and connected.
        Additional checks when accessing data ensure the current user is still authorized.
        :param core: the core that built this engine
        :param location: the path to the SQLite database file
        :return:
        """
        self.core = core
        self.location = location
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

    def login(self, username, password):
        """
        App-level, local login.
        If a user object matches credentials it's returned.
        :param username:
        :param password:
        :return:
        """
        self.engine = sqlalchemy.create_engine('sqlite+pysqlite:///{address}'
                                               .format(address=self.location))
        SessionLocal.configure(bind=self.engine)
        session = SessionLocal()
        hashed_pass = 'md5' + hashlib.md5(password + username).hexdigest()
        try:
            user = session.query(Acd.User) \
                          .filter(Acd.User.login == username,
                                  Acd.User.pw_hash == hashed_pass) \
                          .one()
            logger.debug(_("Successfully logged in with the pair {user} / {password}")
                         .format(user=username, password=hashed_pass))
            return user
        except sqlalchemy.orm.exc.NoResultFound:
            logger.debug(_("Impossible to login with the pair {user} / {password}")
                         .format(user=username, password=hashed_pass))
        except sqlalchemy.orm.exc.MultipleResultsFound:
            logger.error(_("Multiple matches found for pair {user} / {password} !")
                         .format(user=username, password=hashed_pass))

    def get_user(self, username):
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
        except sqlalchemy.orm.exc.NoResultFound:
            logger.debug(_("User {user} not found in local DB.")
                         .format(user=username))
            return False
        except sqlalchemy.orm.exc.MultipleResultsFound:
            logger.error(_("Multiple user records for username {user} found in local DB !")
                         .format(user=username))
            return False

    def get_current_job(self, user):
        """
        Finds the user's current job.
        :param user: A User object to get details from
        :return:
        """
        try:
            session = SessionLocal()
            current_job = session.query(Acd.Job) \
                .filter(Acd.JobContract.user == user.login) \
                .filter(Acd.JobContract.start_date <= datetime.date.today(),
                        Acd.JobContract.end_date >= datetime.date.today()) \
                .one()
            logger.debug(_("Active job found in local for user {name} : {job} - {title}")
                         .format(name=user.login, job=current_job.job_code, title=current_job.job_title))
            return current_job
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info(_("No active jobs found in local for user {name}")
                        .format(name=user.login))
            return None
        except sqlalchemy.orm.exc.MultipleResultsFound:
            logger.error(_("Multiple active jobs found in local for user {name} !")
                         .format(name=user.login))

    def get_base_fullname(self, base_code):
        try:
            session = SessionLocal()
            base = session.query(Acd.WorkBase) \
                          .filter(Acd.WorkBase.id == base_code) \
                          .one()
            logger.debug(_("Base {code} found in local table, with name {name}")
                         .format(code=base_code, name=base.full_name))
            return base.full_name
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info(_("Base {code} not found")
                        .format(code=base_code))
        except sqlalchemy.orm.exc.MultipleResultsFound:
            logger.error(_("Multiple bases found with code {code} !")
                         .format(code=base_code))

    def read_table(self, class_of_table):
        """
        Reads a whole table, returning a list of its objects (records)
        :param class_of_table:
        :return:
        """
        try:
            session = SessionLocal()
            logger.debug(_("Successfully read table {table}")
                         .format(table=class_of_table))
            return session.query(class_of_table).all()
        except sqlalchemy.exc.SQLAlchemyError:
            logger.error(_("Failed to read table {table}")
                         .format(table=class_of_table))
            return False

    def put(self, records):
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
            print exc
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
        Queries the local DB for bases stored
        :return: list of bases
        """
        # TODO: this doesn't actually show the downloaded bases but the full hierarchy
        try:
            session = SessionLocal()
            bases = session.query(Acd.WorkBase.id).all()
            logger.debug(_("List of bases in local DB : {list}")
                         .format(list=str(bases)))
            return bases
        except sqlalchemy.exc.SQLAlchemyError:
            logger.warning(_("Unable to query local DB at location {location}")
                           .format(location=self.location))
            return False