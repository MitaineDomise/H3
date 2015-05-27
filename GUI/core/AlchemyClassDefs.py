__author__ = 'Man'


import sqlalchemy.orm
import sqlalchemy.ext.declarative

Base = sqlalchemy.ext.declarative.declarative_base()


class User(Base):
    __tablename__ = 'users'

    login = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    pw_hash = sqlalchemy.Column(sqlalchemy.String)
    first_name = sqlalchemy.Column(sqlalchemy.String)
    last_name = sqlalchemy.Column(sqlalchemy.String)


class Job(Base):
    __tablename__ = 'careers'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    user = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('users.login'))
    start_date = sqlalchemy.Column(sqlalchemy.Date)
    end_date = sqlalchemy.Column(sqlalchemy.Date)
    job_code = sqlalchemy.Column(sqlalchemy.String)
    job_title = sqlalchemy.Column(sqlalchemy.String)
    base = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.id'))

    base_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('careers'))
    user_fk = sqlalchemy.orm.relationship('User', backref=sqlalchemy.orm.backref('careers'),
                                          foreign_keys=user)


class WorkBase(Base):
    __tablename__ = 'bases'

    id = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    parent = sqlalchemy.Column(sqlalchemy.String, sqlalchemy.ForeignKey('bases.id'))
    full_name = sqlalchemy.Column(sqlalchemy.String)

    parent_self_fk = sqlalchemy.orm.relationship('WorkBase', backref=sqlalchemy.orm.backref('bases', remote_side=[id]))
