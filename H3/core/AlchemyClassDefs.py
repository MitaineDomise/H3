__author__ = 'Man'

import datetime

import sqlalchemy.orm
import sqlalchemy.ext.declarative
import sqlalchemy.orm.session

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
    base = sqlalchemy.Column(sqlalchemy.String, default="BASE-1")
    period = sqlalchemy.Column(sqlalchemy.String, default='PERMANENT')

    parent = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.code', onupdate="cascade"))
    identifier = sqlalchemy.Column(sqlalchemy.String, nullable=False, unique=True)
    full_name = sqlalchemy.Column(sqlalchemy.String)

    opened_date = sqlalchemy.Column(sqlalchemy.Date)
    closed_date = sqlalchemy.Column(sqlalchemy.Date)

    country = sqlalchemy.Column(sqlalchemy.String(2))  # 2-char country code, ISO-3166
    time_zone = sqlalchemy.Column(sqlalchemy.String)

    parent_self_fk = sqlalchemy.orm.relationship('WorkBase',
                                                 foreign_keys=parent,
                                                 post_update=True)

    parent_base = sqlalchemy.orm.relationship('WorkBase',
                                              remote_side=code,
                                              single_parent=True)

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
    base = sqlalchemy.Column(sqlalchemy.String, default="BASE-1")
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
    Starts permanent but will get a year at closing (for later archival).
    Defaults to public but should be set to the base
    """
    __tablename__ = 'job_contracts'

    prefix = 'JOBCONTRACT'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    base = sqlalchemy.Column(sqlalchemy.String, default="BASE-1")
    period = sqlalchemy.Column(sqlalchemy.String, default="PERMANENT")

    user = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('users.code', onupdate="cascade"))
    work_base = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.code', onupdate="cascade"))
    start_date = sqlalchemy.Column(sqlalchemy.Date)
    end_date = sqlalchemy.Column(sqlalchemy.Date)
    job_code = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('jobs.code', onupdate="cascade"))
    job_title = sqlalchemy.Column(sqlalchemy.String)

    base_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('job_contracts'),
                                          foreign_keys=work_base)
    user_fk = sqlalchemy.orm.relationship('User', backref=sqlalchemy.orm.backref('job_contracts'),
                                          foreign_keys=user)
    job_fk = sqlalchemy.orm.relationship('Job', backref=sqlalchemy.orm.backref('job_contracts'),
                                         foreign_keys=job_code)


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
    base = sqlalchemy.Column(sqlalchemy.String, default="BASE-1")
    period = sqlalchemy.Column(sqlalchemy.String, default='PERMANENT')

    identifier = sqlalchemy.Column(sqlalchemy.String)  # ie manage_bases
    category = sqlalchemy.Column(sqlalchemy.String)  # ie FP
    language = sqlalchemy.Column(sqlalchemy.String)  # JSON-encoded dict(locale) of dicts with desc and cat


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
    base = sqlalchemy.Column(sqlalchemy.String, default="BASE-1")
    period = sqlalchemy.Column(sqlalchemy.String, default='PERMANENT')

    category = sqlalchemy.Column(sqlalchemy.String)  # ie FP


class AssignedAction(Base):
    """
    Class holding the actions that have been granted to a contract, delegated or not.
    Scope and Maximum hold the limits of this action
    for example project XX with maximum sign-off USD5000
    Not versioned, as further delegations can be granted as needed.
    """
    __tablename__ = 'assignedactions'

    prefix = 'ASSIGNEDACTION'

    code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    serial = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    base = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    period = sqlalchemy.Column(sqlalchemy.String,
                               nullable=False,
                               default=datetime.date.today().year)

    start_date = sqlalchemy.Column(sqlalchemy.Date, default=None)
    end_date = sqlalchemy.Column(sqlalchemy.Date, default=None)
    # A Job contract. Not a FK because local may not know it.
    delegated_from = sqlalchemy.Column(sqlalchemy.String, default=None)

    action = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('actions.code', onupdate="cascade"))
    assigned_to = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.code', onupdate="cascade"))
    limits = sqlalchemy.Column(sqlalchemy.String)  # JSON limiting sign-off value per-project, base, contract...

    job_contract_fk = sqlalchemy.orm.relationship('JobContract',
                                                  backref=sqlalchemy.orm.backref('assigned_actions'),
                                                  foreign_keys=assigned_to)

    action_fk = sqlalchemy.orm.relationship('Action',
                                            backref=sqlalchemy.orm.backref('assigned_actions'),
                                            foreign_keys=action)


# class RoutingRules(Base, Versioned):
#     """
#     Class holding the rules governing where a given action should send messages and validation / approval requests
#
#     """
#     ___tablename__ = 'routing_rules'
#
#     code = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
#     serial = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
#     base = sqlalchemy.Column(sqlalchemy.String, default="ROOT")
#     period = sqlalchemy.Column(sqlalchemy.String, default='PERMANENT')
#
#     scope = sqlalchemy.Column(sqlalchemy.String)  # "ROOT" for baseline rules, can be base-level or contract-level
#     action = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('actions.code'))
#
#     routing_action_fk = sqlalchemy.orm.relationship('Action',
#                                                     backref=sqlalchemy.orm.backref('routing_rules',
#                                                                                    cascade="all, delete-orphan"),
#                                                     foreign_keys=action)

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

    # A Job contract. Not a FK because local may not know it. For investigation purposes after the fact ! No target.
    origin = sqlalchemy.Column(sqlalchemy.String)

    type = sqlalchemy.Column(sqlalchemy.String)  # Create / Update / Delete
    table = sqlalchemy.Column(sqlalchemy.String)  # ie "bases"
    key = sqlalchemy.Column(sqlalchemy.String)  # PK of the sync entry
    status = sqlalchemy.Column(sqlalchemy.String)  # Unsubmitted / Accepted / Modified

    local_timestamp = sqlalchemy.Column(sqlalchemy.DateTime)
    processed_timestamp = sqlalchemy.Column(sqlalchemy.DateTime)


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
    base = sqlalchemy.Column(sqlalchemy.String, default="BASE-1")
    period = sqlalchemy.Column(sqlalchemy.String, default='PERMANENT')

    origin_jc = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.code', onupdate="cascade"))
    target_jc = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('job_contracts.code', onupdate="cascade"))

    sent = sqlalchemy.Column(sqlalchemy.DateTime)
    received = sqlalchemy.Column(sqlalchemy.DateTime)
    transaction_ref = sqlalchemy.Column(sqlalchemy.String)
    requested_action = sqlalchemy.Column(sqlalchemy.String)  # "validate", "authorize", "comment", "generic"
    body = sqlalchemy.Column(sqlalchemy.String)

    message_origin_fk = sqlalchemy.orm.relationship('JobContract',
                                                    backref=sqlalchemy.orm.backref('messages_out'),
                                                    foreign_keys=origin_jc)
    message_target_fk = sqlalchemy.orm.relationship('JobContract',
                                                    backref=sqlalchemy.orm.backref('messages_in'),
                                                    foreign_keys=target_jc)

    # Project - DonorBudgetLine - InternalBudgetLine - Activities - Donors

    # PSR - SR - GRN - Stock - Asset - Procurement (single or group / full SP)

    # Group of items moving (internal) - incoming goods (proper admin format like waybill etc).

    #  Global tables will have base = BASE-1. Codes will be of the form USER-1. (important for the rebase mechanism)


def get_class_by_table_name(tablename):
    # noinspection PyProtectedMember
    for c in Base._decl_class_registry.values():
        if hasattr(c, '__tablename__') and c.__tablename__ == tablename:
            return c


def detach(acd):
    sqlalchemy.orm.session.make_transient(acd)
