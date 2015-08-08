__author__ = 'Man'

import datetime

import sqlalchemy.orm
import sqlalchemy.ext.declarative

from .AlchemyTemporal import Versioned

Base = sqlalchemy.ext.declarative.declarative_base()


class WorkBase(Base, Versioned):
    """
    Class representing a node in the org tree of the organization.
    Typically what you would call a base.
    Keeps a history table for changes.
    Assumed public (global) and permanent.
    """
    __tablename__ = 'bases'

    prefix = 'BASE'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    base = sqlalchemy.Column(sqlalchemy.String, default="GLOBAL")
    period = sqlalchemy.Column(sqlalchemy.String, default='PERMANENT')

    parent = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.code'))
    identifier = sqlalchemy.Column(sqlalchemy.String)  # ie SHB
    full_name = sqlalchemy.Column(sqlalchemy.String)

    opened_date = sqlalchemy.Column(sqlalchemy.Date)
    closed_date = sqlalchemy.Column(sqlalchemy.Date)

    country = sqlalchemy.Column(sqlalchemy.String(2))  # 2-char country code, ISO-3166
    time_zone = sqlalchemy.Column(sqlalchemy.String)

    parent_self_fk = sqlalchemy.orm.relationship('WorkBase',
                                                 backref=sqlalchemy.orm.backref('parent_bases',
                                                                                remote_side=code,
                                                                                single_parent=True,
                                                                                cascade="all, delete-orphan"),
                                                 foreign_keys=parent,
                                                 passive_updates=False)


class User(Base, Versioned):
    """
    Class representing a person's user account, irrespective of any job.
    Keeps a history table for changes.
    Assumed public (global) and permanent.
    """
    __tablename__ = 'users'

    prefix = 'USER'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    base = sqlalchemy.Column(sqlalchemy.String, default="GLOBAL")
    period = sqlalchemy.Column(sqlalchemy.String, default='PERMANENT')

    login = sqlalchemy.Column(sqlalchemy.String)  # i.e ebertolus
    pw_hash = sqlalchemy.Column(sqlalchemy.String)  # hashed app-level password. SQL access will be different.
    first_name = sqlalchemy.Column(sqlalchemy.String)
    last_name = sqlalchemy.Column(sqlalchemy.String)

    created_date = sqlalchemy.Column(sqlalchemy.Date)
    banned_date = sqlalchemy.Column(sqlalchemy.Date)


class JobContract(Base):
    """
    Class linking a person, a job and a base for an employment contract.
    Not versioned as should not be modified. Extensions will be new records.
    Assumed public (global) with a creation year (for later archival).
    """
    __tablename__ = 'job_contracts'

    prefix = 'JOBCONTRACT'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    base = sqlalchemy.Column(sqlalchemy.String, default="GLOBAL")
    period = sqlalchemy.Column(sqlalchemy.String,
                               nullable=False,
                               default=datetime.date.today().year)

    user = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('users.code'))
    work_base = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.code'), nullable=False)
    start_date = sqlalchemy.Column(sqlalchemy.Date)
    end_date = sqlalchemy.Column(sqlalchemy.Date)
    job_code = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('jobs.code'))
    job_title = sqlalchemy.Column(sqlalchemy.String)

    base_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('job_contracts',
                                                                                     cascade="all, delete-orphan"),
                                          foreign_keys=work_base,
                                          passive_updates=False)
    user_fk = sqlalchemy.orm.relationship('User', backref=sqlalchemy.orm.backref('job_contracts',
                                                                                 cascade="all, delete-orphan"),
                                          foreign_keys=user)
    job_fk = sqlalchemy.orm.relationship('Job', backref=sqlalchemy.orm.backref('job_contracts',
                                                                               cascade="all, delete-orphan"),
                                         foreign_keys=job_code,
                                         passive_updates=False)


class Action(Base):
    """
    Class keeping the actions as presented in the action menu.
    Each action is part of a category, and this table holds localized descriptions of each.
    Not versioned, as part of the system, not organization data.
    Assumed public (global) and permanent.
    """
    __tablename__ = 'actions'

    prefix = 'ACTION'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    base = sqlalchemy.Column(sqlalchemy.String, default="GLOBAL")
    period = sqlalchemy.Column(sqlalchemy.String, default='PERMANENT')

    title = sqlalchemy.Column(sqlalchemy.String)  # ie manage_bases
    language = sqlalchemy.Column(sqlalchemy.String)  # For localization !
    category = sqlalchemy.Column(sqlalchemy.String)  # ie "Stocks management"
    description = sqlalchemy.Column(sqlalchemy.String)


class ContractAction(Base):
    """
    Class linking a given contract to the actions they can perform.
    Scope and Maximum hold the limits of this action
    for example project XX with maximum sign-off USD5000
    Not versioned, as part of the job contract, which shouldn't change.
    """
    __tablename__ = 'contract_actions'

    prefix = 'CONTRACTACTION'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    base = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    period = sqlalchemy.Column(sqlalchemy.String,
                               nullable=False,
                               default=datetime.date.today().year)

    contract = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.code'))
    action = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('actions.code'))
    scope = sqlalchemy.Column(sqlalchemy.String)  # ie (list of) contracts, bases, or projects
    maximum = sqlalchemy.Column(sqlalchemy.Integer)  # maximum sign-off value

    contract_fk = sqlalchemy.orm.relationship('JobContract',
                                              backref=sqlalchemy.orm.backref('contract_actions',
                                                                             cascade="all, delete-orphan"),
                                              foreign_keys=contract)
    action_fk = sqlalchemy.orm.relationship('Action',
                                            backref=sqlalchemy.orm.backref('contract_actions',
                                                                           cascade="all, delete-orphan"),
                                            foreign_keys=action)


class Job(Base):
    """
    Placeholder class that JobContract links to.
    Mainly keeps the distinction between job categories irrespective of exact job title.
    Might get a localized description at least.
    Not versioned as part of the system, not org data.
    """
    __tablename__ = 'jobs'

    prefix = 'JOB'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    base = sqlalchemy.Column(sqlalchemy.String, default="GLOBAL")
    period = sqlalchemy.Column(sqlalchemy.String, default='PERMANENT')

    category = sqlalchemy.Column(sqlalchemy.String)  # ie FP


class Delegation(Base):
    """
    Class holding the actions that have been granted from one contract to another.
    Scope and Maximum hold the limits of this action
    for example project XX with maximum sign-off USD5000
    Not versioned, as further delegations can be granted as needed.
    """
    __tablename__ = 'delegations'

    prefix = 'DELEGATION'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    base = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    period = sqlalchemy.Column(sqlalchemy.String,
                               nullable=False,
                               default=datetime.date.today().year)

    start_date = sqlalchemy.Column(sqlalchemy.Date)
    end_date = sqlalchemy.Column(sqlalchemy.Date)
    action = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('actions.code'))
    delegated_from = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.code'))
    delegated_to = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.code'))
    scope = sqlalchemy.Column(sqlalchemy.String)  # ie list of contracts, bases, or projects
    maximum = sqlalchemy.Column(sqlalchemy.Integer)  # maximum sign-off value

    delegator_fk = sqlalchemy.orm.relationship('JobContract',
                                               backref=sqlalchemy.orm.backref('delegations_out',
                                                                              cascade="all, delete-orphan"),
                                               foreign_keys=delegated_from)
    delegatee_fk = sqlalchemy.orm.relationship('JobContract',
                                               backref=sqlalchemy.orm.backref('delegations_in',
                                                                              cascade="all, delete-orphan"),
                                               foreign_keys=delegated_to)


class SyncJournal(Base):
    """
    Class keeping the updates to the master and satellite (local) DBs
    keeps track of who changed what (job contracts).
    unlike other classes has only a serial which:
     - Starts negative and decremented in the local DBs
     - gets cleared, and autoincremented upon insertion to master
     - then gets copied back into the local databases.
    """
    __tablename__ = 'journal_entries'

    serial = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)  # negative for local entries

    origin_jc = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.code'))
    target_jc = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.code'))

    type = sqlalchemy.Column(sqlalchemy.String)  # Create / Update / Delete
    table = sqlalchemy.Column(sqlalchemy.String)  # ie "bases"
    key = sqlalchemy.Column(sqlalchemy.String)  # PK of the sync entry
    status = sqlalchemy.Column(sqlalchemy.String)  # Unsubmitted / Accepted / Rejected

    local_timestamp = sqlalchemy.Column(sqlalchemy.DateTime)
    processed_timestamp = sqlalchemy.Column(sqlalchemy.DateTime)

    sync_origin_jc_fk = sqlalchemy.orm.relationship('JobContract',
                                                    backref=sqlalchemy.orm.backref('journal_entries_out',
                                                                                   cascade="all, delete-orphan"),
                                                    foreign_keys=origin_jc)
    sync_target_jc_fk = sqlalchemy.orm.relationship('JobContract',
                                                    backref=sqlalchemy.orm.backref('journal_entries_in',
                                                                                   cascade="all, delete-orphan"),
                                                    foreign_keys=target_jc)


class Message(Base):
    """
    Represents a message passed from an employee to another.
    Can carry specific meaning and a reference to a transaction for action within H3,
    or a simple communication tool.
    """
    __tablename__ = 'messages'

    prefix = 'MESSAGE'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    base = sqlalchemy.Column(sqlalchemy.String, default="GLOBAL")
    period = sqlalchemy.Column(sqlalchemy.String, default='PERMANENT')

    origin_jc = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.code'))
    target_jc = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.code'))

    sent = sqlalchemy.Column(sqlalchemy.DateTime)
    received = sqlalchemy.Column(sqlalchemy.DateTime)
    transaction_ref = sqlalchemy.Column(sqlalchemy.String)
    requested_action = sqlalchemy.Column(sqlalchemy.String)  # "validate", "authorize", "comment", "generic"
    body = sqlalchemy.Column(sqlalchemy.String)

    message_origin_fk = sqlalchemy.orm.relationship('JobContract',
                                                    backref=sqlalchemy.orm.backref('messages_out',
                                                                                   cascade="all, delete-orphan"),
                                                    foreign_keys=origin_jc)
    message_target_fk = sqlalchemy.orm.relationship('JobContract',
                                                    backref=sqlalchemy.orm.backref('messages_in',
                                                                                   cascade="all, delete-orphan"),
                                                    foreign_keys=target_jc)

    # Project - DonorBudgetLine - InternalBudgetLine - Activities - Donors

    # PSR - SR - GRN - Stock - Asset - Procurement (single or group / full SP)

    # Group of items moving (internal) - incoming goods (proper admin format like waybill etc).

    #  Global tables will have base = GLOBAL for codes of the form GLOBAL-USER-1.
