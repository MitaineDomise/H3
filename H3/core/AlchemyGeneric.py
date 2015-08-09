__author__ = 'Emmanuel'

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
        return record
    except sqlalchemy.orm.exc.NoResultFound:
        logger.info(_("No object of type {cls} with primary key {key}")
                    .format(cls=class_to_query, key=p_key))
        return None
    except sqlalchemy.exc.SQLAlchemyError:
        logger.error(_("Failed to get object of type {cls} with primary key {key}")
                     .format(cls=class_to_query, key=p_key))


def add(session, record):
    """
    Adds (inserts) a record into the target db.
    Should be used for new records.
    :param session: the session targeted by the insert
    :param record: the record to insert
    :return:
    """
    try:
        timestamp = sqlalchemy.select(sqlalchemy.func.current_time())
    except sqlalchemy.exc.SQLAlchemyError:
        timestamp = datetime.datetime.utcnow()

    try:
        session.add(record)
        session.commit()
        logger.debug(_("Successfully inserted record {record}")
                     .format(record=record))
        return "ok", timestamp
    except sqlalchemy.exc.IntegrityError:
        logger.debug(_("Primary key already exists"))
        return "dupe", timestamp
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Failed to insert record {record}")
                         .format(record=record))
        return "err", timestamp


def merge(session, record):
    """
    Merges (updates) a record into the local db.
    Shouldn't be used for new records.
    :param record:
    :return:
    """
    try:
        timestamp = sqlalchemy.select(sqlalchemy.func.current_time())
    except sqlalchemy.exc.SQLAlchemyError:
        timestamp = datetime.datetime.utcnow()
    try:
        session.merge(record)
        session.commit()
        logger.debug(_("Successfully merged record {record}")
                     .format(record=record))
        return "ok", timestamp
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Failed to merge record {record}")
                         .format(record=record))
        return "err", timestamp
    finally:
        session.close()


def delete(session, record):
    """
    deletes a record from the local db
    :param record:
    :return:
    """
    try:
        timestamp = sqlalchemy.select(sqlalchemy.func.current_time())
    except sqlalchemy.exc.SQLAlchemyError:
        timestamp = datetime.datetime.utcnow()

    try:
        session.delete(record)
        session.commit()
        logger.debug(_("Successfully deleted record {record}")
                     .format(record=record))
        return "ok", timestamp
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception(_("Failed to delete record {record}")
                         .format(record=record))
        return "err", timestamp
    finally:
        session.close()


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
