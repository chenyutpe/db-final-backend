from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class BaseModel(db.Model):
    __abstract__ = True

    def __init__(self, *args):
        super().__init__(*args)

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, {
            column: value
            for column, value in self._to_dict().items()
        })

class Belong(BaseModel, db.Model):
    __tablename__ = 'belong'

    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), primary_key=True)
    nickname = db.Column(db.String(50))
    last_read_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    _account_rel = db.relationship('Account', back_populates='db_account_room_rel')
    _room_rel = db.relationship('Room', back_populates='db_room_account_rel')

    def __init__(self, account, room):
        self._account_rel = account
        self._room_rel = room

class Account(BaseModel, db.Model):
    __tablename__ = 'account'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    last_online = db.Column(db.DateTime, onupdate=datetime.utcnow, default=datetime.utcnow, nullable=False)
    
    db_account_message = db.relationship('Message', backref='account')
    db_account_room_rel = db.relationship('Belong', back_populates='_account_rel')
    
    def __init__(self, name, password):
        self.name = name
        self.password = password


class Cookie(BaseModel, db.Model):
    __tablename__ = 'cookie'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), nullable=False)
    cookie = db.Column(db.String(128), nullable=False)
    personal_room = db.Column(db.String(30)) # for socketio

    def __init__(self, username, cookie):
        self.username = username
        self.cookie = cookie

class Room(BaseModel, db.Model):
    __tablename__ = 'room'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    last_active = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    emoji_id = db.Column(db.Integer, default=0, nullable=False)
    theme_id = db.Column(db.Integer, default=2, nullable=False)

    db_room_message = db.relationship('Message', backref='room')
    db_room_account_rel = db.relationship('Belong', back_populates='_room_rel')

    def __init__(self, name):
        self.name = name

class Message(BaseModel, db.Model):
    __tablename__ = 'message'

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    isFile = db.Column(db.Boolean, nullable=False)
    timeSent = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)

    def __init__(self, content, isFile, account_id, room_id):
        self.content = content
        self.isFile = isFile
        self.account_id = account_id
        self.room_id = room_id