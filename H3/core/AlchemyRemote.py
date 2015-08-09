__author__ = 'Man'

import datetime
import logging
import hashlib

import sqlalchemy
import sqlalchemy.exc
import sqlalchemy.orm
import sqlalchemy.engine
import sqlalchemy.engine.url

from . import AlchemyClassDefs as Acd


# from .AlchemyTemporal import versioned_session

logger = logging.getLogger(__name__)


class H3AlchemyRemoteDB:
    """
    Handles the interaction with the local DB, here PostGreSQL but could be swapped out for any other backend.
    """

    def __init__(self, location):
        """
        Builds the remote DB engine on PostGreSQL; the remote engine is only running when needed.
        The credentials used depend on the current use, on a per-function basis.
        :param location: the DB server holding the main database (needs to be called H3A)
        :return:
        """
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
            hashed_login = hashlib.md5(('H3' + username).encode(encoding='ascii')).hexdigest()
            self.engine = sqlalchemy.create_engine(sqlalchemy.engine.url.URL(drivername='postgresql+pg8000',
                                                                             username=hashed_login,
                                                                             password=password,
                                                                             host=self.location,
                                                                             port=5432,
                                                                             database='h3a'))
            self.engine.connect()
            return True
        except (sqlalchemy.exc.SQLAlchemyError, UnicodeError):
            logger.info(_("Remote DB login has failed for credentials {login} / {password}")
                        .format(login=username, password=password))
            return False

    def master_login(self, username, password):
        """
        Connects to the top-level PGSQL database with admin rights; very dangerous and used only for init / nuke
        :param username:
        :param password:
        :return:
        """
        try:
            self.engine = sqlalchemy.create_engine(sqlalchemy.engine.url.URL(drivername='postgresql+pg8000',
                                                                             username=username,
                                                                             password=password,
                                                                             host=self.location,
                                                                             port=5432,
                                                                             database='postgres'))
            self.engine.connect()
            return True
        except (sqlalchemy.exc.SQLAlchemyError, UnicodeError):
            logger.info(_("Remote DB login has failed for credentials {login} / {password}")
                        .format(login=username, password=password))
            return False

    def update_pass(self, session, username, old_pass, new_pass):
        """
        Changes the actual password for DB access as well as the hashed copy for download by clients.
        :param username: user to be updated on the server
        :param old_pass: old plain password to ALTER ROLE.
        :param new_pass: new plain password
        :return:
        """
        hashed_old = 'md5' + hashlib.md5((old_pass + username).encode(encoding='ascii')).hexdigest()
        hashed_new = 'md5' + hashlib.md5((new_pass + username).encode(encoding='ascii')).hexdigest()
        try:
            # App-level
            user = session.query(Acd.User)\
                .filter(Acd.User.login == username,
                        Acd.User.pw_hash == hashed_old)\
                .one()
            if user:
                user.pw_hash = hashed_new
                session.merge(user)

            logger.debug(_("App-level password change success for user {user}")
                         .format(user=username))

            # SQL-level, will fail if not for self
            query = sqlalchemy.text('ALTER ROLE "{name}" WITH PASSWORD \'{password}\';'
                                    .format(name=username, password=new_pass))

            conn = self.engine.connect()
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query)
            conn.close()
            logger.debug(_("SQL-level password change success for user {user}")
                         .format(user=username))
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info(_("Password change failed for {name}; current user / password pair provided doesn't match")
                        .format(name=username))
            return False
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to update password for {name}")
                             .format(name=username))
            return False

    def create_user(self, session, user):
        """
        Creates a new user slot to be later setup, at app- and SQL levels.
        SQL-level is salted a bit and hashed, to obfuscate the raw connection to remote
        :param user: User object with the pw_hash field actually storing the password PLAIN.
        :return:
        """
        hashed_login = hashlib.md5(('H3' + user.login).encode(encoding='ascii')).hexdigest()
        hashed_pass = hashlib.md5((user.pw_hash + user.login).encode(encoding='ascii')).hexdigest()
        try:
            # App-level
            user.pw_hash = hashed_pass
            session.add(user)
            logger.debug(_("App credentials for {login} created")
                         .format(login=user.login))

            # SQL-level
            query = sqlalchemy.text('CREATE USER "{h_login}" WITH PASSWORD \'{password}\';'
                                    .format(h_login=hashed_login, password=hashed_pass))
            conn = self.engine.connect()
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query)
            conn.close()
            logger.debug(_("SQL role {h_login} ({login}) created")
                         .format(h_login=hashed_login, login=user.login))
            return True
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Creation of user {login} failed")
                             .format(login=user.login))
            query = sqlalchemy.text('DROP USER IF EXISTS "{login}";'
                                    .format(login=hashed_login))

            conn = self.engine.connect()
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query)
            conn.close()
            return False

    def create_base(self, session, base):
        """
        Creates a new base, followed by the SQL creation of a group role for users thereof.
        :param base:
        :return:
        """
        try:

            # App-level
            session.add(base)
            logger.debug(_("Base {name} added to the table")
                         .format(name=base.full_name))

            # SQL-level
            query1 = sqlalchemy.text('CREATE ROLE {base}_users;'
                                     .format(base=base.identifier.lower()))
            query2 = sqlalchemy.text('GRANT h3_users TO {base}_users;'
                                     .format(base=base.identifier.lower()))

            conn = self.engine.connect()
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query1)
            conn.execute(query2)
            conn.close()

            logger.debug(_("Group role for base {name} has been created and added to H3 users")
                         .format(name=base.full_name))

            return True

        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to create base {name}")
                             .format(name=base.full_name))

            query = sqlalchemy.text('DROP ROLE IF EXISTS {base}_users;'
                                    .format(base=base.identifier.lower()))

            conn = self.engine.connect()
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query)
            conn.close()
            return False

    def init_db(self, password):
        query1 = sqlalchemy.text("CREATE DATABASE h3a WITH TEMPLATE template0 LC_CTYPE 'C' LC_COLLATE 'C';")
        query2 = sqlalchemy.text('ALTER DATABASE h3a SET lc_messages = "C";')
        cnx = self.engine.connect()
        cnx.execution_options(isolation_level="AUTOCOMMIT")
        cnx.execute(query1)
        cnx.execute(query2)
        logger.debug(_("Created DB with name h3a"))
        cnx.close()
        self.engine = sqlalchemy.create_engine(sqlalchemy.engine.url.URL(drivername='postgresql+pg8000',
                                                                         username='postgres',
                                                                         password=password,
                                                                         host=self.location,
                                                                         port=5432,
                                                                         database='h3a'))
        meta = Acd.Base.metadata
        meta.create_all(bind=self.engine)
        logger.debug(_("All tables created in remote"))

    # noinspection PyArgumentList
    def populate(self, session):
        """
        Logs in with master PG password (warning !)
        Formats the main database on initial setup and gives read access to all tables to h3_users
        Creates the root base, reader user, root user, and gives that role global FP rights.
        :return:
        """

        # Definition of root objects follows

        reader_user = Acd.User(code='USER-1',
                               serial=1,
                               login='reader',
                               pw_hash='weak',
                               first_name='Reader',
                               last_name='H3',
                               created_date=datetime.date.today(),
                               banned_date=datetime.date(3000, 6, 6))

        root_user = Acd.User(code='USER-2',
                             serial=2,
                             login='root',
                             pw_hash='secret',
                             first_name='Administrator',
                             last_name='H3',
                             created_date=datetime.date.today(),
                             banned_date=datetime.date(3000, 6, 6))

        global_base = Acd.WorkBase(code='BASE-1',
                                   serial=1,
                                   identifier='GLOBAL',
                                   parent='BASE-1',
                                   full_name='Global node',
                                   opened_date=datetime.date(1900, 1, 1),
                                   closed_date=datetime.date(3000, 6, 6),
                                   country='XX',
                                   time_zone='UTC')

        root_base = Acd.WorkBase(code='BASE-2',
                                 serial=1,
                                 identifier='ROOT',
                                 parent='BASE-1',
                                 full_name='Hierarchy root',
                                 opened_date=datetime.date.today(),
                                 closed_date=datetime.date(3000, 6, 6),
                                 country='XX',
                                 time_zone='UTC')

        root_job = Acd.Job(code='JOB-1',
                           serial=1,
                           category='FP')

        root_contract = Acd.JobContract(code='ROOT-JOBCONTRACT-1900-1',
                                        serial=1,
                                        base='ROOT',
                                        work_base='BASE-2',
                                        user='USER-2',
                                        start_date=datetime.date(1900, 1, 1),
                                        end_date=datetime.date(3000, 6, 6),
                                        job_code='JOB-1',
                                        job_title='Global FP')

        global_contract = Acd.JobContract(code='JOBCONTRACT-1',
                                          serial=1,
                                          base='GLOBAL',
                                          work_base='BASE-1',
                                          user='USER-1',
                                          start_date=datetime.date(1900, 1, 1),
                                          end_date=datetime.date(3000, 6, 6),
                                          job_code='JOB-1',
                                          job_title='Global target')

        root_a_1 = Acd.Action(code='ACTION-1',
                              serial=1,
                              title='manage_users',
                              language="EN_UK",
                              category="Administration",
                              description="Manage users")
        root_a_2 = Acd.Action(code='ACTION-2',
                              serial=2,
                              title='manage_bases',
                              language="EN_UK",
                              category="Logistics",
                              description="Manage bases")
        root_a_3 = Acd.Action(code='ACTION-3',
                              serial=3,
                              title='manage_jobs',
                              language="EN_UK",
                              category="FP",
                              description="Manage jobs")
        root_a_4 = Acd.Action(code='ACTION-4',
                              serial=4,
                              title='manage_job_contracts',
                              language="EN_UK",
                              category="Administration",
                              description="Manage job contracts")
        root_a_5 = Acd.Action(code='ACTION-5',
                              serial=5,
                              title='manage_contract_actions',
                              language="EN_UK",
                              category="Logistics",
                              description="Manage contract actions")

        root_c_a_1 = Acd.ContractAction(code='ROOT-CONTRACTACTION-1900-1',
                                        serial=1,
                                        base="ROOT",
                                        contract='ROOT-JOBCONTRACT-1900-1',
                                        action='ACTION-1',
                                        scope='all',
                                        maximum=-1)

        root_c_a_2 = Acd.ContractAction(code='ROOT-CONTRACTACTION-1900-2',
                                        serial=2,
                                        base="ROOT",
                                        contract='ROOT-JOBCONTRACT-1900-1',
                                        action='ACTION-2',
                                        scope='all',
                                        maximum=-1)

        root_c_a_3 = Acd.ContractAction(code='ROOT-CONTRACTACTION-1900-3',
                                        serial=3,
                                        base="ROOT",
                                        contract='ROOT-JOBCONTRACT-1900-1',
                                        action='ACTION-3',
                                        scope='all',
                                        maximum=-1)

        root_c_a_4 = Acd.ContractAction(code='ROOT-CONTRACTACTION-1900-4',
                                        serial=4,
                                        base="ROOT",
                                        contract='ROOT-JOBCONTRACT-1900-1',
                                        action='ACTION-4',
                                        scope='all',
                                        maximum=-1)

        root_delegation = Acd.Delegation(code='ROOT-DELEGATION-1900-1',
                                         serial=1,
                                         base="ROOT",
                                         start_date=datetime.date.today(),
                                         end_date=datetime.date(3000, 6, 6),
                                         action='ACTION-5',
                                         delegated_from='JOBCONTRACT-1',
                                         delegated_to='ROOT-JOBCONTRACT-1900-1',
                                         scope='all',
                                         maximum=-1)

        initial_sync_entry = Acd.SyncJournal(origin_jc='JOBCONTRACT-1',
                                             target_jc='ROOT-JOBCONTRACT-1900-1',
                                             type="INIT",
                                             status="INIT",
                                             local_timestamp=datetime.date(1900, 1, 1))

        try:
            query1 = sqlalchemy.text('CREATE ROLE h3_users '
                                     'NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION;')
            query2 = sqlalchemy.text('CREATE ROLE h3_fps '
                                     'NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION;')
            query3 = sqlalchemy.text('GRANT h3_users TO h3_fps;')

            conn = self.engine.connect()
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query1)
            logger.debug(_("Created users group role"))
            conn.execute(query2)
            logger.debug(_("Created FP group role"))
            conn.execute(query3)
            logger.debug(_("Given users rights to FP group role"))
            conn.close()

            self.create_base(session, global_base)
            self.create_base(session, root_base)
            self.create_user(session, reader_user)
            self.create_user(session, root_user)

            query4 = sqlalchemy.text('GRANT h3_fps TO "4f626e28d5c60212d8d38ed00f1444f2";')
            query5 = sqlalchemy.text('REVOKE CREATE ON DATABASE h3a FROM "f66ce97dfce5d8604edab9a721f3b85b";')
            query6 = sqlalchemy.text('GRANT SELECT ON ALL TABLES IN SCHEMA PUBLIC TO GROUP h3_users WITH GRANT OPTION;')
            query7 = sqlalchemy.text('GRANT INSERT, UPDATE ON TABLE users, bases TO GROUP h3_fps WITH GRANT OPTION;')
            query8 = sqlalchemy.text('GRANT SELECT ON TABLE users, bases, jobs, job_contracts '
                                     'TO "f66ce97dfce5d8604edab9a721f3b85b";')

            conn = self.engine.connect()
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query4)
            logger.debug(_("Given FP group role to root user"))
            conn.execute(query5)
            logger.debug(_("Removed creation rights from reader user"))
            conn.execute(query6)
            logger.debug(_("Users group can now SELECT all tables"))
            conn.execute(query7)
            logger.debug(_("FP group can now change users and bases tables"))
            conn.execute(query8)
            logger.debug(_("Reader role can now see users, bases and job contracts only"))
            conn.close()

            logger.info(_("Basic rights granted to H3 default roles"))

            session.add(root_job)
            logger.debug(_("Root job inserted"))
            session.add(root_contract)
            session.add(global_contract)
            logger.debug(_("Root and global contract inserted"))
            session.add(root_a_1)
            session.add(root_a_2)
            session.add(root_a_3)
            session.add(root_a_4)
            session.add(root_a_5)

            session.add(root_c_a_1)
            session.add(root_c_a_2)
            session.add(root_c_a_3)
            session.add(root_c_a_4)
            session.add(root_delegation)
            session.add(initial_sync_entry)

            logger.debug(_("Root contract actions inserted"))
            logger.debug(_("Root data inserted"))

            return True
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to init root data"))
            return False

    def nuke(self):
        """
        Drops all base roles and the DB itself ! Note: remember to disconnect from the DB in pgadmin.
        :return:
        """
        try:
            query0 = sqlalchemy.text("DROP DATABASE h3a;")
            query1 = sqlalchemy.text('DROP ROLE IF EXISTS h3_fps;')
            query2 = sqlalchemy.text('DROP ROLE IF EXISTS h3_users;')
            query3 = sqlalchemy.text('DROP ROLE IF EXISTS global_users;')
            query4 = sqlalchemy.text('DROP ROLE IF EXISTS root_users;')
            query5 = sqlalchemy.text('DROP ROLE IF EXISTS "4f626e28d5c60212d8d38ed00f1444f2";')
            query6 = sqlalchemy.text('DROP ROLE IF EXISTS "f66ce97dfce5d8604edab9a721f3b85b";')

            conn = self.engine.connect()
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query0)
            conn.execute(query1)
            conn.execute(query2)
            conn.execute(query3)
            conn.execute(query4)
            conn.execute(query5)
            conn.execute(query6)
            conn.close()

            logger.debug(_("Default DB and roles successfully wiped out"))
            return True
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to clean up default DB and roles"))
            return False


# TODO : actually use this
def get_career(session, username):
    """
    Get the list of jobs for a user.
    :param username: user login to query
    :return:
    """
    try:
        jobs = session.query(Acd.JobContract) \
            .filter(Acd.JobContract.user == username) \
            .order_by(Acd.JobContract.start_date) \
            .all()
        if jobs:
            return jobs
        else:
            logger.info(_("No current contract."))
            return None
    except sqlalchemy.exc.SQLAlchemyError:
        logger.error(_("Error querying DB for user {user}'s career")
                     .format(user=username))


def user_count(session, base_code):
    try:
        return session.query(Acd.JobContract) \
            .filter(Acd.JobContract.work_base == base_code) \
            .count()
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Querying the DB for user count failed"))
        return False


def get_updates(session, first_serial, bases_list):
    """
    Extract sync journal entries targeted to any of the bases the user sees.
    Actions / Delegations will be caught by this.
    :param first_serial: the last update we don't need (excluded floor value)
    :param bases_list: the base visibility, for which we request updates
    :return:
    """
    try:
        updates = session.query(Acd.SyncJournal) \
            .filter(Acd.SyncJournal.serial > first_serial) \
            .filter(Acd.SyncJournal.target_jc.in_(session.query(Acd.JobContract.code)
                                                  .filter(Acd.JobContract.work_base.in_(bases_list)))) \
            .all()
        return updates
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Failed to download updates"))
