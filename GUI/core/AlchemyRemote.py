__author__ = 'Man'

import datetime
import logging
import hashlib

import AlchemyClassDefs as Acd

import sqlalchemy
import sqlalchemy.exc
import sqlalchemy.orm
import sqlalchemy.engine
import sqlalchemy.engine.url

SessionRemote = sqlalchemy.orm.sessionmaker()
logger = logging.getLogger(__name__)


class H3AlchemyRemoteDB():
    """
    Handles the interaction with the local DB, here PostGreSQL but could be swapped out for any other backend.
    """
    def __init__(self, core, location):
        """
        Builds the remote DB engine on PostGreSQL; the remote engine is only running when needed.
        The credentials used depend on the current use, on a per-function basis.
        :param core: the core that built this engine
        :param location: the DB server holding the main database (needs to be called H3A)
        :return:
        """
        self.core = core
        self.location = location
        self.engine = None

    def login(self, username, password):
        """
        Actually logs in to PGSQL with the supplied credentials.
        Access levels can be monitored and adjusted through PGAdmin.
        They are set up at the same time as app credentials
        :param username:
        :param password:
        :return:
        """
        try:
            self.engine = sqlalchemy.create_engine(sqlalchemy.engine.url.URL(drivername='postgresql+pg8000',
                                                                             username=username,
                                                                             password=password,
                                                                             host=self.location,
                                                                             port=5002,
                                                                             database='H3A'))
            SessionRemote.configure(bind=self.engine)
            self.engine.connect()
            return True
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Remote DB login has failed for credentials {login} / {password}")
                             .format(login=username, password=password))
            return False

    def update_pass(self, username, old_pass, new_pass):
        """
        Changes the actual password for DB access as well as the hashed copy for download by clients.
        :param username: user to be updated on the server
        :param old_pass: old plain password to ALTER ROLE.
        :param new_pass: new plain password
        :return:
        """
        # TODO : normal users can't write in the users table. Put a trigger on pg_auth ?
        # Trigger on users : can UPDATE self only.
        # OR have this sent as a ticket to root.

        self.login(username, old_pass)
        session = SessionRemote()
        hashed_old = 'md5' + hashlib.md5(old_pass + username).hexdigest()
        hashed_new = 'md5' + hashlib.md5(new_pass + username).hexdigest()
        try:
            conn = self.engine.connect()
            # App-level
            user = session.query(Acd.User)\
                .filter(Acd.User.login == username,
                        Acd.User.pw_hash == hashed_old)\
                .one()
            if user:
                print user.pw_hash
                user.pw_hash = hashed_new
                print user.pw_hash
                session.merge(user)
                print 'merged'


            # SQL-level
            query = sqlalchemy.text('ALTER ROLE {name} WITH PASSWORD \'{password}\';'
                                    .format(name=username, password=new_pass))

            conn.execute("COMMIT;")  # have to clear the transaction before ALTER
            print 'commit sent'
            conn.execute(query)
            print 'raw SQL sent'
            session.commit()
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info(_("Password change failed for {name}; current user / password pair provided doesn't match")
                        .format(name=username))
            return False
        except sqlalchemy.orm.exc.MultipleResultsFound:
            logger.warning(_("Password change failed for {name}; current user / password pair has multiple matches !")
                           .format(name=username))
            return False
        except sqlalchemy.exc.SQLAlchemyError:
            session.rollback()
            logger.exception(_("Failed to update password for {name}. Rollback has been issued.")
                             .format(name=username))
            return False
        try:
            # SQLAlchemy level

            self.engine = sqlalchemy.create_engine(sqlalchemy.engine.url.URL(drivername='postgresql+pg8000',
                                                                             username=user,
                                                                             password=new_pass,
                                                                             host=self.location,
                                                                             port=5002,
                                                                             database='H3A'))
            self.engine.connect()
            return True
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Password change has failed for {name}; login has been denied with the new password.")
                             .format(name=username))
            return False

    def create_user(self, user):
        """
        Creates a new user slot to be later setup, at app- and SQL levels
        :param user:
        :return:
        """
        # TODO: Revamp that - Focal Points should have role creation rights. Then contracts are per-base.
        # Trigger on users : only FPs can INSERT

        # Maybe should be raw SQL to be absolutely sure of clean rollback ?
        session = None
        conn = None
        try:
            session = SessionRemote()

            # App-level
            session.add(user)

            # SQL-level
            conn = self.engine.connect()
            query = sqlalchemy.text('CREATE USER {login} WITH PASSWORD \'YOUPIE\';'
                                    .format(login=user.login))

            conn.execute("COMMIT;")  # have to clear the transaction before CREATE
            conn.execute(query)
            session.commit()

            return True

            # query = sqlalchemy.text('GRANT ' + user.base.lower() + '_users TO ' + user.login + ';')
            # conn.execute(query)
            # conn.execute("COMMIT;")
        except sqlalchemy.exc.SQLAlchemyError:
            session.rollback()
            query = sqlalchemy.text('DROP USER IF EXISTS {login};'
                                    .format(login=user.login))
            conn.execute("COMMIT;")  # have to clear the transaction before DROP
            conn.execute(query)
            return False

    def create_base(self, base):
        """
        Creates a new base, followed by the SQL creation of a group role for users thereof.
        :param base:
        :return:
        """
        # TODO : FPs can write in "bases" ?
        session = None
        conn = None
        try:
            session = SessionRemote()
            conn = self.engine.connect()

            # App-level
            session.add(base)

            # SQL-level
            query1 = sqlalchemy.text('CREATE ROLE {base}_users;'
                                     .format(base=base.id.lower()))
            query2 = sqlalchemy.text('GRANT h3_users TO {base}_users;'
                                     .format(base=base.id.lower()))

            conn.execute("COMMIT;")
            conn.execute(query1)
            conn.execute("COMMIT;")
            conn.execute(query2)
            session.commit()

            return True

        except sqlalchemy.exc.SQLAlchemyError:
            query = sqlalchemy.text('DROP ROLE IF EXISTS {base}_users;'
                                    .format(base=base.id.lower()))
            conn.execute("COMMIT;")
            conn.execute(query)
            session.rollback()

            return False

    def get_user(self, username):
        """
        Pull a specific user from the list.
        :param username:
        :return:
        """
        self.login("reader", "weak")
        session = SessionRemote()
        try:
            user = session.query(Acd.User) \
                          .filter(Acd.User.login == username) \
                          .one()
            logger.debug(_("User {name} found in remote DB.")
                         .format(name=username))
            return user
        except sqlalchemy.orm.exc.NoResultFound:
            logger.debug(_("User {name} not found in remote DB.")
                         .format(name=username))
            return False
        except sqlalchemy.orm.exc.MultipleResultsFound:
            logger.error(_("Multiple results for username {name} found in remote DB.")
                         .format(name=username))
            return False

    def get_jobs(self, username):
        """
        Get the list of jobs for a user.
        :param username:
        :return:
        """
        session = SessionRemote()
        jobs = session.query(Acd.Job) \
                      .filter(Acd.Job.user == username) \
                      .order_by(Acd.Job.start_date) \
                      .all()
        if jobs:
            return jobs
        else:
            logger.info(_("No current contract."))
            return None

    def init_public_tables(self):
        """
        Format the main database on initial setup and gives read access to all tables to h3_users
        :return:
        """
        # TODO: Initial setup invoked through CLI; public tables only. also create the initial roles root and h3_users
        # self.login('rolemaker', 'secret')
        # No rolemaker here; using PG root access.
        meta = Acd.Base.metadata
        conn = self.engine.connect()
        try:
            meta.create_all(bind=self.engine)
            for table in meta.tables.values():
                conn.execute("COMMIT;")  # have to clear the transaction before CREATE
                query = sqlalchemy.text('GRANT SELECT ON TABLE {table_name} TO h3_users WITH GRANT OPTION;'
                                        .format(table_name=table.key))
                conn.execute(query)
            return True
        except sqlalchemy.exc.SQLAlchemyError:
            meta.drop_all()
            return False

    def read_table(self, class_of_table):
        """
        Reads a whole table, returning a list of its objects (records)
        :param class_of_table:
        :return:
        """
        self.login('reader', 'weak')
        session = SessionRemote()
        return session.query(class_of_table).all()

    def get_visible_users(self, bases_list):
        """
        Get the users from a given list of bases, for display by GUI.
        :param bases_list:
        :return:
        """
        self.login('reader', 'weak')
        session = SessionRemote()
        ret = session.query(Acd.User.login,
                            Acd.User.first_name,
                            Acd.User.last_name,
                            Acd.Job.job_title,
                            Acd.Job.base)\
            .filter(Acd.User.login == Acd.Job.user)\
            .filter(Acd.Job.base.in_(bases_list))\
            .order_by(Acd.Job.base).all()
        return ret

    def has_a_base(self):
        """
        If there's at least one base in this DB (ie this is a valid H3 DB) will return True.
        :return:
        """
        try:
            self.login("reader", "weak")
            session = SessionRemote()
            if session.query(Acd.WorkBase).count() > 0:
                return True
            else:
                return False
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Unable to query the remote DB at {address}")
                             .format(address=self.location))
            return False

    def get_current_job(self, user):
        """
        Finds the user's current job.
        :param user: A User object to get details from
        :return:
        """
        try:
            session = SessionRemote()
            current_job = session.query(Acd.Job) \
                                 .filter(Acd.Job.user == user.login) \
                                 .filter(Acd.Job.start_date <= datetime.date.today(),
                                         Acd.Job.end_date >= datetime.date.today()) \
                                 .one()
            logger.debug(_("Active job found in remote for user {name} : {job} - {title}")
                         .format(name=user.login, job=current_job.job_code, title=current_job.job_title))
            return current_job
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info(_("No active jobs found in remote for user {name}")
                        .format(name=user.login))
            return None
        except sqlalchemy.orm.exc.MultipleResultsFound:
            logger.error(_("Multiple active jobs found in remote for user {name} !")
                         .format(name=user.login))
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Querying the remote DB for {user}'s current job failed")
                             .format(user=user.login))
