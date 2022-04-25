from data.db_session import *
import sqlalchemy


class User(SqlAlchemyBase):
    __tablename__ = 'users'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    user_id = sqlalchemy.Column(sqlalchemy.BigInteger, unique=True)
    username = sqlalchemy.Column(sqlalchemy.VARCHAR(128), unique=True)
    name = sqlalchemy.Column(sqlalchemy.VARCHAR(128))
    email = sqlalchemy.Column(sqlalchemy.VARCHAR(100))
