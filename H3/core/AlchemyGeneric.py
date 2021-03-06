__author__ = 'Man'

import logging
import datetime

import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.exc

from . import AlchemyClassDefs as Acd

logger = logging.getLogger(__name__)


def get_user_from_login(session, username):
    try:
        user = session.query(Acd.User) \
            .filter(Acd.User.login == username) \
            .one()
        logger.debug(_("User {name} found with primary key {key}")
                     .format(name=username, key=user.code))
        return user
    except sqlalchemy.orm.exc.NoResultFound:
        logger.info(_("No user found with name {name}")
                    .format(name=username))
        return None
    except sqlalchemy.orm.exc.MultipleResultsFound:
        logger.error(_("Multiple records found for name {name} !")
                     .format(name=username))


def get_current_job_contract(session, user):
    """
    Finds the user's current job.
    :param user: The User object to query
    :return:
    """
    try:
        current_job = session.query(Acd.JobContract) \
            .filter(Acd.JobContract.user == user.code) \
            .filter(Acd.JobContract.start_date <= datetime.date.today(),
                    Acd.JobContract.end_date >= datetime.date.today()) \
            .one()
        logger.debug(_("Active job found for user {name} : {job} - {title}")
                     .format(name=user.login, job=current_job.job_code, title=current_job.job_title))
        return current_job
    except sqlalchemy.orm.exc.NoResultFound:
        logger.info(_("No active jobs found for user {name}")
                    .format(name=user.login))
        return None
    except sqlalchemy.orm.exc.MultipleResultsFound:
        logger.error(_("Multiple active jobs found for user {name} !")
                     .format(name=user.login))
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Querying the DB for {user}'s current job failed")
                         .format(user=user.login))


def get_from_primary_key(session, class_to_query, p_key):
    if class_to_query:
        mapper = sqlalchemy.inspect(class_to_query)
        assert len(mapper.primary_key) == 1
        primary = mapper.primary_key[0]
    else:
        return None
    try:
        record = session.query(class_to_query).filter(primary == p_key).one()
        logger.debug(_("Found object of type {cls} with primary key {key}")
                     .format(cls=class_to_query, key=p_key))
        return record
    except sqlalchemy.orm.exc.NoResultFound:
        logger.info(_("No object of type {cls} with primary key {key}")
                    .format(cls=class_to_query, key=p_key))
        return None
    except sqlalchemy.exc.SQLAlchemyError:
        logger.error(_("Failed to get object of type {cls} with primary key {key}")
                     .format(cls=class_to_query, key=p_key))


def merge_multiple(session, records):
    try:
        for record in records:
            session.merge(record)
        return True
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Bulk merge failed on this record list : {list}")
                         .format(list=records))


def read_table(session, class_of_table):
    """
    Reads a whole table, returning a list of its objects (records)
    :param class_of_table:
    :return:
    """
    try:
        table = session.query(class_of_table).all()
        logger.debug(_("Successfully read table {table}")
                     .format(table=class_of_table))
        return table
    except sqlalchemy.exc.SQLAlchemyError:
        logger.error(_("Failed to read table {table}")
                     .format(table=class_of_table))
        return False


def get_highest_synced_sync_serial(session):
    try:
        max_num = session.query(sqlalchemy.func.max(Acd.SyncJournal.serial).label('max')) \
            .filter(Acd.SyncJournal.serial > 0) \
            .one()
        logger.debug(_("Latest sync entry has serial {no}")
                     .format(no=max_num.max))
        return max_num.max if max_num.max else 0
    except sqlalchemy.orm.exc.NoResultFound:
        logger.info(_("No synced sync entries, defaulting to 0"))
        return 0
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Error while getting the newest synced sync entry"))


def get_assigned_actions(session, job_contract):
    try:
        actions = session.query(Acd.AssignedAction, Acd.Action) \
            .join(Acd.Action) \
            .filter(Acd.AssignedAction.assigned_to == job_contract.code) \
            .all()
        return actions
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Unable to query DB for actions linked to contract {id}")
                         .format(id=job_contract.code))
        return False
    finally:
        session.close()


def get_highest_serial(session, mapped_class, base_code):
    try:
        max_num = session.query(sqlalchemy.func.max(mapped_class.serial).label('max')) \
            .filter(mapped_class.base == base_code) \
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


def user_count(session, base_code):
    try:
        count = session.query(Acd.JobContract) \
            .filter(Acd.JobContract.work_base == base_code) \
            .count()
        return count or 0
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Querying the DB for user count failed"))
        return False


def subtree(session, root_base_pkey):
    """
    Queries local database for the organisational tree, then walks it to extract a list of sub-bases
    :param root_base_pkey: root of the extracted subtree
    """
    org_table = read_table(session, Acd.WorkBase)
    extracted_subtree = list()
    extracted_subtree.append(root_base_pkey)
    tree_row = [root_base_pkey]
    next_row = list()
    while tree_row:
        for base in tree_row:
            for record in org_table:
                if record.parent == base:
                    if record.parent != record.code:
                        next_row.append(record.code)
                        extracted_subtree.append(record.code)
        tree_row = next_row
        next_row = list()
    return extracted_subtree
