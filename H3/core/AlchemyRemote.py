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
from .AlchemyTemporal import versioned_session

SessionRemote = sqlalchemy.orm.sessionmaker()
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
            SessionRemote.configure(bind=self.engine)
            versioned_session(SessionRemote)
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
            SessionRemote.configure(bind=self.engine)
            self.engine.connect()
            return True
        except (sqlalchemy.exc.SQLAlchemyError, UnicodeError):
            logger.info(_("Remote DB login has failed for credentials {login} / {password}")
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
        # Trigger on users : can UPDATE self only.
        # OR have this sent as a ticket to root.

        self.login(username, old_pass)
        session = SessionRemote()
        hashed_old = 'md5' + hashlib.md5((old_pass + username).encode(encoding='ascii')).hexdigest()
        hashed_new = 'md5' + hashlib.md5((new_pass + username).encode(encoding='ascii')).hexdigest()
        try:
            conn = self.engine.connect()
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

            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query)
            session.commit()
            logger.debug(_("SQL-level password change success for user {user}")
                         .format(user=username))
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

            self.login(user, new_pass)
            self.engine.connect()

            logger.debug(_("New password is now in effect for user {user}")
                         .format(user=username))

            return True
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Password change has failed for {name}; login has been denied with the new password.")
                             .format(name=username))
            return False

    def create_user(self, user):
        """
        Creates a new user slot to be later setup, at app- and SQL levels.
        SQL-level is salted a bit and hashed, to obfuscate the raw connection to remote
        :param user: User object with the pw_hash field actually storing the password PLAIN.
        :return:
        """
        session = None
        conn = None
        hashed_login = hashlib.md5(('H3' + user.login).encode(encoding='ascii')).hexdigest()
        try:
            session = SessionRemote()

            # SQL-level
            conn = self.engine.connect()
            query = sqlalchemy.text('CREATE USER "{h_login}" WITH PASSWORD \'{password}\';'
                                    .format(h_login=hashed_login, password=user.pw_hash))

            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query)

            logger.debug(_("SQL role {h_login} ({plain}) created")
                         .format(h_login=hashed_login, plain=user.login))

            # App-level
            hashed_pass = hashlib.md5((user.pw_hash + user.login).encode(encoding='ascii')).hexdigest()
            user.pw_hash = hashed_pass
            session.add(user)

            session.commit()

            logger.debug(_("App credentials for {plain} created")
                         .format(plain=user.login))

            return True
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Creation of user {plain} failed")
                             .format(plain=user.login))
            session.rollback()
            query = sqlalchemy.text('DROP USER IF EXISTS "{login}";'
                                    .format(login=hashed_login))

            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query)
            return False

    def create_base(self, base):
        """
        Creates a new base, followed by the SQL creation of a group role for users thereof.
        :param base:
        :return:
        """
        session = None
        conn = None
        try:
            session = SessionRemote()
            conn = self.engine.connect()

            # App-level
            session.add(base)

            session.commit()

            logger.debug(_("Base {name} added to the table")
                         .format(name=base.full_name))

            # SQL-level
            query1 = sqlalchemy.text('CREATE ROLE {base}_users;'
                                     .format(base=base.code.lower()))
            query2 = sqlalchemy.text('GRANT h3_users TO {base}_users;'
                                     .format(base=base.code.lower()))

            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query1)
            conn.execute(query2)

            logger.debug(_("Group role for base {name} has been created and added to H3 users")
                         .format(name=base.full_name))

            return True

        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to create base {name}")
                             .format(name=base.full_name))

            session.rollback()

            query = sqlalchemy.text('DROP ROLE IF EXISTS {base}_users;'
                                    .format(base=base.code.lower()))

            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(query)

            return False

    @staticmethod
    def get_user(username):
        """
        Pull a specific user from the list.
        :param username:
        :return:
        """
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

    @staticmethod
    def get_career(user):
        """
        Get the list of jobs for a user.
        :param user: user object to find jobs
        :return:
        """
        session = SessionRemote()
        jobs = session.query(Acd.JobContract) \
            .filter(Acd.JobContract.user == user.login) \
            .order_by(Acd.JobContract.start_date) \
            .all()
        if jobs:
            return jobs
        else:
            logger.info(_("No current contract."))
            return None

    def initialize(self, password):
        """
        Logs in with master PG password (warning !)
        Formats the main database on initial setup and gives read access to all tables to h3_users
        Creates the root base, reader user, root user, and gives that role global FP rights.
        :return:
        """
        session = SessionRemote()
        cnx = self.engine.connect()
        cnx.execution_options(isolation_level="AUTOCOMMIT")
        meta = Acd.Base.metadata

        try:
            query1 = sqlalchemy.text("CREATE DATABASE h3a WITH TEMPLATE template0 LC_CTYPE 'C' LC_COLLATE 'C';")
            query2 = sqlalchemy.text('ALTER DATABASE h3a SET lc_messages = "C";')
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
            SessionRemote.configure(bind=self.engine)
            session = SessionRemote()
            cnx = self.engine.connect()
            meta.create_all(bind=self.engine)
            logger.debug(_("All tables created in remote"))
            cnx.close()
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to init default H3 DB; dropping."))
            cnx.close()

            # Definition of root objects follows

        reader_user = Acd.User(login='reader',
                               pw_hash='weak',
                               first_name='Reader',
                               last_name='H3',
                               created_date=datetime.date.today(),
                               banned_date=datetime.date(3000, 6, 6))

        root_user = Acd.User(login='root',
                             pw_hash='secret',
                             first_name='Administrator',
                             last_name='H3',
                             created_date=datetime.date.today(),
                             banned_date=datetime.date(3000, 6, 6))

        root_base = Acd.WorkBase(code='root',
                                 parent='root',
                                 full_name='Hierarchy root',
                                 opened_date=datetime.date.today(),
                                 closed_date=datetime.date(3000, 6, 6),
                                 country='XX',
                                 time_zone='UTC')

        root_job = Acd.Job(code='FP')

        root_contract = Acd.JobContract(auto_id=1,
                                        user='root',
                                        start_date=datetime.date.today(),
                                        end_date=datetime.date(3000, 6, 6),
                                        job_code='FP',
                                        job_title='Global FP',
                                        base='root')

        root_a_1 = Acd.Action(code='manage_users',
                              language="EN_UK",
                              category="Administration",
                              description="Manage users")
        root_a_2 = Acd.Action(code='manage_bases',
                              language="EN_UK",
                              category="Logistics",
                              description="Manage bases")
        root_a_3 = Acd.Action(code='manage_jobs',
                              language="EN_UK",
                              category="FP",
                              description="Manage jobs")
        root_a_4 = Acd.Action(code='manage_job_contracts',
                              language="EN_UK",
                              category="Administration",
                              description="Manage job contracts")
        root_a_5 = Acd.Action(code='manage_contract_actions',
                              language="EN_UK",
                              category="Logistics",
                              description="Manage contract actions")

        root_c_a_1 = Acd.ContractAction(contract=1,
                                        action='manage_users',
                                        scope='all',
                                        maximum=-1)

        root_c_a_2 = Acd.ContractAction(contract=1,
                                        action='manage_bases',
                                        scope='all',
                                        maximum=-1)

        root_c_a_3 = Acd.ContractAction(contract=1,
                                        action='manage_jobs',
                                        scope='all',
                                        maximum=-1)

        root_c_a_4 = Acd.ContractAction(contract=1,
                                        action='manage_job_contracts',
                                        scope='all',
                                        maximum=-1)

        # root_c_a_5 = Acd.ContractAction(contract=1,
        #                                 action='manage_contract_actions',
        #                                 scope='all',
        #                                 maximum=-1)

        root_delegation = Acd.Delegation(start_date=datetime.date.today(),
                                         end_date=datetime.date(3000, 6, 6),
                                         action='manage_contract_actions',
                                         delegated_from=1,
                                         delegated_to=1,
                                         scope='all',
                                         maximum=-1)

        initial_sync_entry = Acd.SyncJournal(origin_base="root",
                                             origin_user="root",
                                             type="INIT",
                                             status="INIT",
                                             local_timestamp=datetime.datetime.now())
        try:
            cnx = self.engine.connect()
            cnx.execution_options(isolation_level="AUTOCOMMIT")
            query1 = sqlalchemy.text('CREATE ROLE h3_users '
                                     'NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION;')
            query2 = sqlalchemy.text('CREATE ROLE h3_fps '
                                     'NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION;')
            query3 = sqlalchemy.text('GRANT h3_users TO h3_fps;')

            cnx.execute(query1)
            logger.debug(_("Created users group role"))
            cnx.execute(query2)
            logger.debug(_("Created FP group role"))
            cnx.execute(query3)

            self.create_base(root_base)
            self.create_user(root_user)
            self.create_user(reader_user)

            query4 = sqlalchemy.text('GRANT h3_fps TO "4f626e28d5c60212d8d38ed00f1444f2";')
            query5 = sqlalchemy.text('REVOKE CREATE ON DATABASE h3a FROM "f66ce97dfce5d8604edab9a721f3b85b";')
            query6 = sqlalchemy.text('GRANT SELECT ON ALL TABLES IN SCHEMA PUBLIC TO GROUP h3_users WITH GRANT OPTION;')
            query7 = sqlalchemy.text('GRANT INSERT, UPDATE ON TABLE users, bases TO GROUP h3_fps WITH GRANT OPTION;')
            query8 = sqlalchemy.text('GRANT SELECT ON TABLE users, bases, jobs, actions, job_contracts, sync_journal '
                                     'TO "f66ce97dfce5d8604edab9a721f3b85b";')

            logger.debug(_("Given users rights to FP group role"))
            cnx.execute(query4)
            logger.debug(_("Given FP group role to root user"))
            cnx.execute(query5)
            logger.debug(_("Removed creation rights from reader user"))
            cnx.execute(query6)
            logger.debug(_("Users group can now SELECT all tables"))
            cnx.execute(query7)
            logger.debug(_("FP group can now change users and bases tables"))
            cnx.execute(query8)
            logger.debug(_("Reader role can now see users and bases (only)"))

            cnx.close()

            logger.info(_("Basic rights granted to H3 default roles"))

            session.add(root_job)
            logger.debug(_("Root job inserted"))
            session.add(root_contract)
            logger.debug(_("Root contract inserted"))
            session.add(root_a_1)
            session.add(root_a_2)
            session.add(root_a_3)
            session.add(root_a_4)
            session.add(root_a_5)

            session.commit()

            session.add(root_c_a_1)
            session.add(root_c_a_2)
            session.add(root_c_a_3)
            session.add(root_c_a_4)
            # session.add(root_c_a_5)
            session.add(root_delegation)
            session.add(initial_sync_entry)

            session.commit()

            logger.debug(_("Root contract actions inserted"))

            logger.debug(_("Root data inserted"))
            print(_("DB init successful"))

        except sqlalchemy.exc.SQLAlchemyError:
            print(_("DB init failed, see log.txt for details"))
            logger.exception(_("Failed to init root data"))
            session.rollback()
            cnx.close()

    def nuke(self):
        """
        Drops all base roles and the DB itself ! Note: remember to disconnect from the DB in pgadmin.
        :return:
        """

        conn = self.engine.connect()
        conn.execution_options(isolation_level="AUTOCOMMIT")

        try:
            query0 = sqlalchemy.text("DROP DATABASE h3a;")
            query1 = sqlalchemy.text('DROP ROLE IF EXISTS h3_fps;')
            query2 = sqlalchemy.text('DROP ROLE IF EXISTS h3_users;')
            query3 = sqlalchemy.text('DROP ROLE IF EXISTS root_users;')
            query4 = sqlalchemy.text('DROP ROLE IF EXISTS "4f626e28d5c60212d8d38ed00f1444f2";')
            query5 = sqlalchemy.text('DROP ROLE IF EXISTS "f66ce97dfce5d8604edab9a721f3b85b";')
            conn.execute(query0)
            conn.execute(query1)
            conn.execute(query2)
            conn.execute(query3)
            conn.execute(query4)
            conn.execute(query5)

            logger.debug(_("Default DB and roles successfully wiped out"))
            print(_("DB Wipe successful"))
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to clean up default DB and roles"))
            print(_("DB Wipe failed, see log.txt for details"))

    @staticmethod
    def read_table(class_of_table):
        """
        Reads a whole table, returning a list of its objects (records)
        :param class_of_table:
        :return:
        """
        try:
            session = SessionRemote()
            table = session.query(class_of_table).all()
            logger.debug(_("Successfully read table {table} from remote")
                         .format(table=class_of_table))
            return table
        except sqlalchemy.exc.SQLAlchemyError:
            logger.error(_("Failed to read table {table} from remote")
                         .format(table=class_of_table))
            return False

    @staticmethod
    def get_visible_users(bases_list):
        """
        Get the users from a given list of bases, for display by H3.
        :param bases_list:
        :return:
        """
        session = SessionRemote()
        ret = session.query(Acd.User.login,
                            Acd.User.first_name,
                            Acd.User.last_name,
                            Acd.JobContract.job_title,
                            Acd.JobContract.base) \
            .filter(Acd.User.login == Acd.JobContract.user) \
            .filter(Acd.JobContract.base.in_(bases_list)) \
            .order_by(Acd.JobContract.base).all()
        return ret

    @staticmethod
    def get_current_job_contract(user):
        """
        Finds the user's current job.
        :param user: A User object to get details from
        :return:
        """
        try:
            session = SessionRemote()
            current_job = session.query(Acd.JobContract) \
                .filter(Acd.JobContract.user == user.login) \
                .filter(Acd.JobContract.start_date <= datetime.date.today(),
                        Acd.JobContract.end_date >= datetime.date.today()) \
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

    @staticmethod
    def get_contract_actions(job_contract):
        """
        Finds the actions linked with a given contract.
        :return:
        """
        try:
            session = SessionRemote()
            actions_list = session.query(Acd.ContractAction) \
                .filter(Acd.ContractAction.contract == job_contract.auto_id) \
                .all()
            logger.debug(_("Actions in remote for contract {job}, {base} : {list}")
                         .format(job=job_contract.job_title, base=job_contract.base, list=actions_list))
            return actions_list
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info(_("No actions found in remote for contract {job}, {base}")
                        .format(job=job_contract.job_title, base=job_contract.base))
            return None
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Querying the remote DB for actions failed"))

    @staticmethod
    def get_delegations(job_contract):
        """
        Finds the actions delegated *to* a given contract.
        :return:
        """
        try:
            session = SessionRemote()
            delegations_list = session.query(Acd.Delegation) \
                .filter(Acd.Delegation.delegated_to == job_contract.auto_id) \
                .all()
            logger.debug(_("Delegations in remote to contract {job}, {base} : {list}")
                         .format(job=job_contract.job_title, base=job_contract.base, list=delegations_list))
            return delegations_list
        except sqlalchemy.orm.exc.NoResultFound:
            logger.info(_("No delegations found in remote for contract {job}, {base}")
                        .format(job=job_contract.job_title, base=job_contract.base))
            return None
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Querying the remote DB for delegations failed"))

    def user_count(self, base_code):
        try:
            session = SessionRemote()
            return session.query(Acd.JobContract) \
                .filter(Acd.JobContract.base == base_code) \
                .count()
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Querying the remote DB for user count failed"))
            return False

    def post(self, sync_entry):
        try:
            session = SessionRemote()
            session.add(sync_entry)
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to post the journal entry to remote !"))

    def get_last_synced_entry(self):
        try:
            session = SessionRemote()
            latest = session.query(Acd.SyncJournal) \
                .filter(Acd.SyncJournal.auto_id == sqlalchemy.func.max(Acd.SyncJournal.auto_id)) \
                .one()
            return latest
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to identify the latest synced transaction in remote"))

    def get_public_updates(self, first_update):
        try:
            session = SessionRemote()
            latest = session.query(Acd.SyncJournal) \
                .filter(Acd.SyncJournal.auto_id > first_update) \
                .filter(Acd.SyncJournal.table.in_(["users", "bases", "jobs", "actions"])) \
                .all()
            return latest
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to download the public updates remote"))

    def get_base_updates(self, first_update, base):
        try:
            session = SessionRemote()
            latest = session.query(Acd.SyncJournal) \
                .filter(Acd.SyncJournal.auto_id > first_update) \
                .filter(Acd.SyncJournal.target_base == base.code) \
                .all()
            return latest
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to download the base updates from remote"))

    def get_user_updates(self, first_update, user):
        # TODO : any point to that ? Maybe look at contract instead, to get new actions ?
        try:
            session = SessionRemote()
            latest = session.query(Acd.SyncJournal) \
                .filter(Acd.SyncJournal.auto_id > first_update) \
                .filter(Acd.SyncJournal.target_user == user.login) \
                .all()
            return latest
        except sqlalchemy.exc.SQLAlchemyError:
            logger.exception(_("Failed to download the base updates from remote"))
