__author__ = 'Man'


import sqlalchemy.orm
import sqlalchemy.ext.declarative

Base = sqlalchemy.ext.declarative.declarative_base()


class User(Base):
    __tablename__ = 'users'

    login = sqlalchemy.Column(sqlalchemy.String, primary_key=True)  # i.e ebertolus
    pw_hash = sqlalchemy.Column(sqlalchemy.String)  # hashed app-level password. SQL access will be different.
    first_name = sqlalchemy.Column(sqlalchemy.String)
    last_name = sqlalchemy.Column(sqlalchemy.String)


class Job(Base):
    __tablename__ = 'careers'

    user = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('users.login'))
    start_date = sqlalchemy.Column(sqlalchemy.Date)
    end_date = sqlalchemy.Column(sqlalchemy.Date)
    job_code = sqlalchemy.Column(sqlalchemy.String)
    job_title = sqlalchemy.Column(sqlalchemy.String)
    base = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.id'))

    base_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('careers'),
                                          foreign_keys=base)
    user_fk = sqlalchemy.orm.relationship('User', backref=sqlalchemy.orm.backref('careers'),
                                          foreign_keys=user)


class Action(Base):
    __tablename__ = 'actions'

    id = sqlalchemy.Column(sqlalchemy.String, primary_key=True)  # ie manage_bases


class JobAction(Base):
    __tablename__ = 'job_actions'

    job = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('careers.id'))
    action = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('careers.id'))

    job_fk = sqlalchemy.orm.relationship('Job', backref=sqlalchemy.orm.backref('job_actions'),
                                         foreign_keys=job)
    action_fk = sqlalchemy.orm.relationship('Action', backref=sqlalchemy.orm.backref('job_actions'),
                                            foreign_keys=job)


class Delegation(Base):
    __tablename__ = 'delegations'

    start_date = sqlalchemy.Column(sqlalchemy.Date)
    end_date = sqlalchemy.Column(sqlalchemy.Date)
    role = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('actions.id'))
    delegated_from = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('careers.id'))
    delegated_to = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('careers.id'))

    delegator_fk = sqlalchemy.orm.relationship('Job', backref=sqlalchemy.orm.backref('delegations'),
                                               foreign_keys=delegated_from)
    delegatee_fk = sqlalchemy.orm.relationship('Job', backref=sqlalchemy.orm.backref('delegations'),
                                               foreign_keys=delegated_to)


class WorkBase(Base):
    __tablename__ = 'bases'

    id = sqlalchemy.Column(sqlalchemy.String, primary_key=True)  # ie SHB
    parent = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.id'))
    full_name = sqlalchemy.Column(sqlalchemy.String)

    parent_self_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('bases', remote_side=id))


