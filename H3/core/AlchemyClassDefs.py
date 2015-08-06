__author__ = 'Man'

import sqlalchemy.orm
import sqlalchemy.ext.declarative

from .AlchemyTemporal import Versioned

Base = sqlalchemy.ext.declarative.declarative_base()


class WorkBase(Base, Versioned):
    __tablename__ = 'bases'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer)

    parent = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.code'))
    identifier = sqlalchemy.Column(sqlalchemy.String)  # ie SHB
    full_name = sqlalchemy.Column(sqlalchemy.String)

    opened_date = sqlalchemy.Column(sqlalchemy.Date)
    closed_date = sqlalchemy.Column(sqlalchemy.Date)

    country = sqlalchemy.Column(sqlalchemy.String(2))  # 2-char country code, ISO-3166
    time_zone = sqlalchemy.Column(sqlalchemy.String)

    parent_self_fk = sqlalchemy.orm.relationship('WorkBase',
                                                 backref=sqlalchemy.orm.backref('bases', remote_side=code),
                                                 cascade="all, delete-orphan",
                                                 passive_updates=False)


class User(Base, Versioned):
    __tablename__ = 'users'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer)

    login = sqlalchemy.Column(sqlalchemy.String)  # i.e ebertolus
    pw_hash = sqlalchemy.Column(sqlalchemy.String)  # hashed app-level password. SQL access will be different.
    first_name = sqlalchemy.Column(sqlalchemy.String)
    last_name = sqlalchemy.Column(sqlalchemy.String)

    created_date = sqlalchemy.Column(sqlalchemy.Date)
    banned_date = sqlalchemy.Column(sqlalchemy.Date)


class JobContract(Base):
    __tablename__ = 'job_contracts'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer)

    user = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('users.code'))
    start_date = sqlalchemy.Column(sqlalchemy.Date)
    end_date = sqlalchemy.Column(sqlalchemy.Date)
    job_code = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('jobs.code'))
    job_title = sqlalchemy.Column(sqlalchemy.String)
    base = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.code'))

    base_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('job_contracts'),
                                          foreign_keys=base,
                                          cascade="all, delete-orphan",
                                          passive_updates=False)
    user_fk = sqlalchemy.orm.relationship('User', backref=sqlalchemy.orm.backref('job_contracts'),
                                          foreign_keys=user)
    job_fk = sqlalchemy.orm.relationship('Job', backref=sqlalchemy.orm.backref('job_contracts'),
                                         foreign_keys=job_code,
                                         cascade="all, delete-orphan",
                                         passive_updates=False)


class Action(Base):
    __tablename__ = 'actions'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer)

    title = sqlalchemy.Column(sqlalchemy.String)  # ie manage_bases
    language = sqlalchemy.Column(sqlalchemy.String)  # For localization !
    category = sqlalchemy.Column(sqlalchemy.String)  # ie "Stocks management"
    description = sqlalchemy.Column(sqlalchemy.String)


class ContractAction(Base):
    __tablename__ = 'contract_actions'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer)

    contract = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('job_contracts.code'))
    action = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('actions.code'))
    scope = sqlalchemy.Column(sqlalchemy.String)  # ie (list of) contracts, bases, or projects
    maximum = sqlalchemy.Column(sqlalchemy.Integer)  # maximum sign-off value

    contract_fk = sqlalchemy.orm.relationship('JobContract', backref=sqlalchemy.orm.backref('contract_actions'),
                                              foreign_keys=contract)
    action_fk = sqlalchemy.orm.relationship('Action', backref=sqlalchemy.orm.backref('contract_actions'),
                                            foreign_keys=action)


class Job(Base):
    __tablename__ = 'jobs'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer)

    category_title = sqlalchemy.Column(sqlalchemy.String)  # ie FP


class Delegation(Base):
    __tablename__ = 'delegations'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer)

    start_date = sqlalchemy.Column(sqlalchemy.Date)
    end_date = sqlalchemy.Column(sqlalchemy.Date)
    action = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('actions.code'))
    delegated_from = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('job_contracts.code'))
    delegated_to = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey('job_contracts.code'))
    scope = sqlalchemy.Column(sqlalchemy.String)  # ie list of contracts, bases, or projects
    maximum = sqlalchemy.Column(sqlalchemy.Integer)  # maximum sign-off value

    delegator_fk = sqlalchemy.orm.relationship('JobContract', backref=sqlalchemy.orm.backref('delegations_out'),
                                               foreign_keys=delegated_from)
    delegatee_fk = sqlalchemy.orm.relationship('JobContract', backref=sqlalchemy.orm.backref('delegations_in'),
                                               foreign_keys=delegated_to)


class SyncJournal(Base):
    __tablename__ = 'journal_entries'

    code = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)  # negative for local entries
    serial = sqlalchemy.Column(sqlalchemy.Integer)

    origin_jc = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.auto_id'))
    target_jc = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.auto_id'))

    type = sqlalchemy.Column(sqlalchemy.String)  # Create / Update / Delete
    table = sqlalchemy.Column(sqlalchemy.String)  # ie "bases"
    key = sqlalchemy.Column(sqlalchemy.String)  # PK of the sync entry
    status = sqlalchemy.Column(sqlalchemy.String)  # Unsubmitted / Accepted / Rejected

    local_timestamp = sqlalchemy.Column(sqlalchemy.DateTime)
    processed_timestamp = sqlalchemy.Column(sqlalchemy.DateTime)

    sync_origin_jc_fk = sqlalchemy.orm.relationship('JobContract',
                                                    backref=sqlalchemy.orm.backref('journal_entries_out'),
                                                    foreign_keys=origin_jc)
    sync_target_jc_fk = sqlalchemy.orm.relationship('JobContract', backref=sqlalchemy.orm.backref('journal_entries_in'),
                                                    foreign_keys=target_jc)


class Message(Base):
    __tablename__ = 'messages'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer)

    origin_jc = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.auto_id'))
    target_jc = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.auto_id'))

    sent = sqlalchemy.Column(sqlalchemy.DateTime)
    received = sqlalchemy.Column(sqlalchemy.DateTime)
    transaction_ref = sqlalchemy.Column(sqlalchemy.String)
    requested_action = sqlalchemy.Column(sqlalchemy.String)  # "validate", "authorize", "comment", "generic"
    body = sqlalchemy.Column(sqlalchemy.String)

    message_origin_fk = sqlalchemy.orm.relationship('JobContract', backref=sqlalchemy.orm.backref('messages_out'),
                                                    foreign_keys=origin_jc)
    message_target_fk = sqlalchemy.orm.relationship('JobContract', backref=sqlalchemy.orm.backref('messages_in'),
                                                    foreign_keys=target_jc)


    # Project - DonorBudgetLine - InternalBudgetLine - Activities - Donors

    # PSR - SR - GRN - Stock - Asset - Procurement (single or group / full SP)

    # Group of items moving (internal) - incoming goods (proper admin format like waybill etc).

    #  Base tables will have islocal = True to have local codes.
