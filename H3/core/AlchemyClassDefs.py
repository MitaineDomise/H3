__author__ = 'Man'


import sqlalchemy.orm
import sqlalchemy.ext.declarative

Base = sqlalchemy.ext.declarative.declarative_base()


class WorkBase(Base):
    __tablename__ = 'bases'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)  # ie SHB
    parent = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.code'))
    full_name = sqlalchemy.Column(sqlalchemy.String)

    opened_date = sqlalchemy.Column(sqlalchemy.Date)
    closed_date = sqlalchemy.Column(sqlalchemy.Date)

    country = sqlalchemy.Column(sqlalchemy.String(2))  # 2-char country code, ISO-3166
    time_zone = sqlalchemy.Column(sqlalchemy.String)

    parent_self_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('bases', remote_side=code))


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

    auto_id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)

    user = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('users.login'))
    start_date = sqlalchemy.Column(sqlalchemy.Date)
    end_date = sqlalchemy.Column(sqlalchemy.Date)
    job_code = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('jobs.code'))
    job_title = sqlalchemy.Column(sqlalchemy.String)
    base = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.code'))

    base_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('job_contracts'),
                                          foreign_keys=base)
    user_fk = sqlalchemy.orm.relationship('User', backref=sqlalchemy.orm.backref('job_contracts'),
                                          foreign_keys=user)
    job_fk = sqlalchemy.orm.relationship('Job', backref=sqlalchemy.orm.backref('job_contracts'),
                                         foreign_keys=job_code)


class Action(Base):
    __tablename__ = 'actions'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)  # ie manage_bases
    language = sqlalchemy.Column(sqlalchemy.String)  # For localization !
    category = sqlalchemy.Column(sqlalchemy.String)  # ie "Stocks management"
    description = sqlalchemy.Column(sqlalchemy.String)


class ContractAction(Base):
    __tablename__ = 'contract_actions'

    auto_id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)

    contract = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('job_contracts.auto_id'))
    action = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('actions.code'))
    scope = sqlalchemy.Column(sqlalchemy.String)  # ie list of contracts, bases, or projects
    maximum = sqlalchemy.Column(sqlalchemy.Integer)  # maximum sign-off value

    contract_fk = sqlalchemy.orm.relationship('JobContract', backref=sqlalchemy.orm.backref('contract_actions'),
                                              foreign_keys=contract)
    action_fk = sqlalchemy.orm.relationship('Action', backref=sqlalchemy.orm.backref('contract_actions'),
                                            foreign_keys=action)

class Job(Base):
    __tablename__ = 'jobs'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)  # ie FP


class Delegation(Base):
    __tablename__ = 'delegations'

    auto_id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)

    start_date = sqlalchemy.Column(sqlalchemy.Date)
    end_date = sqlalchemy.Column(sqlalchemy.Date)
    action = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('actions.code'))
    delegated_from = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('job_contracts.auto_id'))
    delegated_to = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('job_contracts.auto_id'))
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
    auto_id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)

    origin_base = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.code'))
    origin_user = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('users.login'))
    status = sqlalchemy.Column(sqlalchemy.String)  # Unsubmitted / Accepted / Modified / Rejected
    local_timestamp = sqlalchemy.Column(sqlalchemy.Date)
    local_code = sqlalchemy.Column(sqlalchemy.String)
    submitted_timestamp = sqlalchemy.Column(sqlalchemy.Date)

    origin_base_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('journal'))
    origin_user_fk = sqlalchemy.orm.relationship('User', backref=sqlalchemy.orm.backref('journal'))


class SyncCursor(Base):  # Shouldn't the cursor be in a config file ?
    __tablename__ = 'sync_cursors'

    auto_id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)

    user = sqlalchemy.Column(sqlalchemy.String)
    base = sqlalchemy.Column(sqlalchemy.String)
    last_synced = sqlalchemy.Column(sqlalchemy.DateTime)
    last_transaction_synced = sqlalchemy.Column(sqlalchemy.Integer)  # From SyncJournal


class Message(Base):
    __tablename__ = 'messages'

    auto_id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)

    sender = sqlalchemy.Column(sqlalchemy.String)
    addressee = sqlalchemy.Column(sqlalchemy.String)
    sent = sqlalchemy.Column(sqlalchemy.Date)
    received = sqlalchemy.Column(sqlalchemy.Date)
    transaction_ref = sqlalchemy.Column(sqlalchemy.String)
    body = sqlalchemy.Column(sqlalchemy.String)


    # Project - DonorBudgetLine - InternalBudgetLine - Activities - Donors

    # PSR - SR - GRN - Stock - Asset - Procurement (single or group / full SP)

    # Group of items moving (internal) - incoming goods (proper admin format like waybill etc).