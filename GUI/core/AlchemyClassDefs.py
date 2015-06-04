__author__ = 'Man'


import sqlalchemy.orm
import sqlalchemy.ext.declarative

Base = sqlalchemy.ext.declarative.declarative_base()


class WorkBase(Base):
    __tablename__ = 'bases'

    id = sqlalchemy.Column(sqlalchemy.String, primary_key=True)  # ie SHB
    parent = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.id'))
    full_name = sqlalchemy.Column(sqlalchemy.String)

    opened_date = sqlalchemy.Column(sqlalchemy.Date)
    closed_date = sqlalchemy.Column(sqlalchemy.Date)

    country = sqlalchemy.Column(sqlalchemy.String(2))  # 2-char country code, ISO-3166
    time_zone = sqlalchemy.Column(sqlalchemy.String)

    parent_self_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('bases', remote_side=id))


class User(Base):
    __tablename__ = 'users'

    login = sqlalchemy.Column(sqlalchemy.String, primary_key=True)  # i.e ebertolus
    pw_hash = sqlalchemy.Column(sqlalchemy.String)  # hashed app-level password. SQL access will be different.
    first_name = sqlalchemy.Column(sqlalchemy.String)
    last_name = sqlalchemy.Column(sqlalchemy.String)

    created_date = sqlalchemy.Column(sqlalchemy.Date)
    banned_date = sqlalchemy.Column(sqlalchemy.Date)


class JobContract(Base):
    __tablename__ = 'job_contracts'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)

    user = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('users.login'))
    start_date = sqlalchemy.Column(sqlalchemy.Date)
    end_date = sqlalchemy.Column(sqlalchemy.Date)
    job_code = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('jobs.id'))
    job_title = sqlalchemy.Column(sqlalchemy.String)
    base = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.id'))

    base_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('job_contracts'),
                                          foreign_keys=base)
    user_fk = sqlalchemy.orm.relationship('User', backref=sqlalchemy.orm.backref('job_contracts'),
                                          foreign_keys=user)
    job_fk = sqlalchemy.orm.relationship('Job', backref=sqlalchemy.orm.backref('job_contracts'),
                                         foreign_keys=job_code)


class Action(Base):
    __tablename__ = 'actions'

    id = sqlalchemy.Column(sqlalchemy.String, primary_key=True)  # ie manage_bases


class ContractAction(Base):
    __tablename__ = 'contract_actions'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)

    contract = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('job_contracts.id'))
    action = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('actions.id'))
    scope = sqlalchemy.Column(sqlalchemy.String)  # ie list of contracts, bases, or projects
    maximum = sqlalchemy.Column(sqlalchemy.Integer)  # maximum sign-off value


class Job(Base):
    __tablename__ = 'jobs'

    id = sqlalchemy.Column(sqlalchemy.String, primary_key=True)  # ie FP


class Delegation(Base):
    __tablename__ = 'delegations'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)

    start_date = sqlalchemy.Column(sqlalchemy.Date)
    end_date = sqlalchemy.Column(sqlalchemy.Date)
    role = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('actions.id'))
    delegated_from = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('job_contracts.id'))
    delegated_to = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('job_contracts.id'))
    scope = sqlalchemy.Column(sqlalchemy.String)  # ie list of contracts, bases, or projects
    maximum = sqlalchemy.Column(sqlalchemy.Integer)  # maximum sign-off value

    delegator_fk = sqlalchemy.orm.relationship('JobContract', backref=sqlalchemy.orm.backref('delegations_out'),
                                               foreign_keys=delegated_from)
    delegatee_fk = sqlalchemy.orm.relationship('JobContract', backref=sqlalchemy.orm.backref('delegations_in'),
                                               foreign_keys=delegated_to)


class SyncJournal(Base):
    __tablename__ = 'sync_journal'

    # Inserts only. Get all inserts, from the "versioning rows" SQL Alchemy example...?
    # Or get both inserts and updates ?
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)

    origin_base = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.id'))
    origin_user = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('users.login'))
    status = sqlalchemy.Column(sqlalchemy.String)  # Unsubmitted / Accepted / Modified / Rejected
    local_timestamp = sqlalchemy.Column(sqlalchemy.Date)
    local_code = sqlalchemy.Column(sqlalchemy.String)
    submitted_timestamp = sqlalchemy.Column(sqlalchemy.Date)

    origin_base_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('journal'))
    origin_user_fk = sqlalchemy.orm.relationship('User', backref=sqlalchemy.orm.backref('journal'))


class Message(Base):
    __tablename__ = 'messages'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)

    sender = sqlalchemy.Column(sqlalchemy.String)
    addressee = sqlalchemy.Column(sqlalchemy.String)
    sent = sqlalchemy.Column(sqlalchemy.Date)
    received = sqlalchemy.Column(sqlalchemy.Date)
    transaction_ref = sqlalchemy.Column(sqlalchemy.String)
    body = sqlalchemy.Column(sqlalchemy.String)


    # Project - DonorBudgetLine - InternalBudgetLine - Activities - Donors

    # PSR - SR - GRN - Stock - Asset - Procurement (single or group / full SP)

    # Group of items moving (internal) - incoming goods (proper admin format like waybill etc).