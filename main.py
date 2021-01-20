from flask import Flask, request, url_for, redirect
from flask_sqlalchemy import SQLAlchemy
import hashlib
from datetime import date, datetime, timedelta
from flask_socketio import SocketIO, join_room, leave_room, send, emit
from model import db, Belong, Account, Cookie, Room, Message
import json
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

app.config['SECRET_KEY'] = 'NTU_DB_2020_secret_key'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql://ntu:ntu@127.0.0.1:5432/dvdrental"

db.init_app(app)

with app.app_context():
	db.drop_all()
	db.create_all()

socketio = SocketIO(app, cors_allowed_origins='*')

epoch = datetime.utcfromtimestamp(0)

def unix_time_millis(dt):
    return (dt - epoch).total_seconds() * 1000.0

def generate_cookie(username, password, current_time):
    sha512 = hashlib.sha512()
    sha512.update(username.encode())
    sha512.update(password.encode())
    sha512.update(current_time.encode())
    return sha512.hexdigest()

def authenticate_user(username, cookie):
	db_response = db.session.query(Cookie).filter_by(username=username, cookie=cookie).first()
	return bool(db_response)

class ComplexEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        else:
            return json.JSONEncoder.default(self, obj)

@app.route('/login', methods=['POST'])
def login():
	username = request.form['username']
	password = request.form['password']

	sha512 = hashlib.sha512()
	sha512.update(password.encode())
	hashed_password = sha512.hexdigest()
	response = {}

	user = db.session.query(Account).filter_by(name=username).first()
	current_time = datetime.now().strftime('%m/%d/%Y, %H:%M:%S')
	cookie = generate_cookie(username, hashed_password, current_time)

	if user:
		if user.password == hashed_password:
			response['status'] = 'login successfully'
		else:
			response['status'] = 'failed'
	else:
		response['status'] = 'register successfully'
		new_user = Account(username, hashed_password)
		db.session.add(new_user)
		db.session.commit()
	
	response['cookie'] = '' if response['status'] == 'failed' else cookie
	if response['status'] != 'failed':
		new_cookie = Cookie(username, cookie)
		db.session.add(new_cookie)
		db.session.commit()

	return json.dumps(response)

@app.route('/logout', methods=['POST'])
def logout():
	username = request.form['username']
	cookie = request.form['cookie']

	if not authenticate_user(username, cookie):
		return 'authentication failed'

	cookie_to_delete = db.session.query(Cookie).filter_by(username=username, cookie=cookie).first()
	db.session.delete(cookie_to_delete)
	db.session.commit()

	return 'successful'

@app.route('/chatrooms', methods=['POST'])
def chatrooms():
	username = request.form['username']
	cookie = request.form['cookie']

	if not authenticate_user(username, cookie):
		return 'authentication failed'

	response = []

	user = db.session.query(Account).filter_by(name=username).first()
	user_chatroom = user.db_account_room_rel
	for uc in user_chatroom:
		chatroom = db.session.query(Room).filter_by(id=uc.room_id).first()
		chatroom_info = {
			'name': chatroom.name,
			'id': str(chatroom.id),
			'last_send_date': unix_time_millis(chatroom.last_active),
			'last_read_date': chatroom.last_active
		}

		last_msg = db.session.query(Message).filter_by(room_id=chatroom.id, timeSent=chatroom.last_active).first()
		if last_msg:
			chatroom_info['last_message'] = last_msg.content
			last_sender = db.session.query(Account).filter_by(id=last_msg.account_id).first()
			chatroom_info['last_sender'] = last_sender.name
		else:
			chatroom_info['last_message'] = ''
			chatroom_info['last_sender'] = ''

		response.append(chatroom_info)
	
	return json.dumps({"data": response}, cls=ComplexEncoder)

@app.route('/chat/<id>', methods=['POST'])
def chat(id):
	username = request.form['username']
	cookie = request.form['cookie']
	
	if not authenticate_user(username, cookie):
		return 'authentication failed'

	room = db.session.query(Room).filter_by(id=id).first()
	response = {
		'name': room.name,
		'id': str(id),
		'last_active': unix_time_millis(room.last_active),
		'emoji': room.emoji_id,
		'theme': room.theme_id
	}

	people = []
	room_users = room.db_room_account_rel

	for ru in room_users:
		user = db.session.query(Account).filter_by(id=ru.account_id).first()
		nickname = ru.nickname if ru.nickname else user.name
		people.append({
			'username': user.name,
			'nickname': nickname
		})
	response['people'] = people

	room_messages = db.session.query(Message).filter_by(room_id=room.id).all()
	messages = []
	for message in room_messages:
		sender = db.session.query(Account).filter_by(id=message.account_id).first()
		messages.append({
			'sender': sender.name,
			'body': message.content
		})
	
	response['messages'] = messages

	return json.dumps(response, cls=ComplexEncoder)

@app.route('/create_room', methods=['POST'])
def create_room():
	username = request.form['username']
	cookie = request.form['cookie']
	chatroom_name = request.form['chatroom_name']

	if not authenticate_user(username, cookie):
		return 'authentication failed'

	room_exist = db.session.query(Room).filter_by(name=chatroom_name).first() != None
	if room_exist:
		return 'failed'

	user = db.session.query(Account).filter_by(name=username).first()
	new_room = Room(chatroom_name)
	b = Belong(user, new_room)
	db.session.add_all([new_room, b])
	db.session.commit()
	return 'successful'

@app.route('/change_room_name', methods=['POST'])
def change_room_name():
	username = request.form['username']
	cookie = request.form['cookie']
	room_id = request.form['room_id']
	new_chatroom_name = request.form['new_chatroom_name']

	if not authenticate_user(username, cookie):
		return 'authentication failed'

	chatroom_name_taken = db.session.query(Room).filter_by(name=new_chatroom_name).first()
	if chatroom_name_taken:
		return 'failed'
	else:
		room = db.session.query(Room).filter_by(id=int(room_id)).first()
		old_chatroom_name = room.name
		room.name = new_chatroom_name
		db.session.commit()
		socketio.emit('chatroom_name_changed', {
			"room_id": room_id,
			"old_name": old_chatroom_name,
			"new_name": new_chatroom_name
		}, room=room_id)

		return 'successful'

@app.route('/add_member', methods=['POST'])
def add_member():
	username = request.form['username']
	cookie = request.form['cookie']
	chatroom_name = request.form['chatroom_name']
	new_member_name = request.form['new_member_name']
	
	if not authenticate_user(username, cookie):
		return 'authentication failed'
	
	user = db.session.query(Account).filter_by(name=username).first()
	room = db.session.query(Room).filter_by(name=chatroom_name).first()
	user_in_room = db.session.query(Belong).filter_by(account_id=user.id, room_id=room.id).first()
	if user_in_room:
		exist = db.session.query(Account).filter_by(name=new_member_name).first()
		if exist:
			room = db.session.query(Room).filter_by(name=chatroom_name).first()
			already_in_db = db.session.query(Belong).filter_by(account_id=exist.id, room_id=room.id).first()
			if already_in_db:
				return 'failed'
			else:
				b = Belong(exist, room)
				db.session.add(b)
				db.session.commit()

				new_member_cookies = db.session.query(Cookie).filter_by(username=new_member_name).all()
				for cookie in new_member_cookies:
					receiver = cookie.personal_room
					socketio.emit('invite', {'chatroom_name': chatroom_name}, room=receiver)
				
				people = []
				room_users = room.db_room_account_rel
				for ru in room_users:
					user = db.session.query(Account).filter_by(id=ru.account_id).first()
					nickname = ru.nickname if ru.nickname else user.name
					people.append({
						'username': user.name,
						'nickname': nickname
					})

				socketio.emit('new_members', {'room_id': str(room.id), "members": people}, room=str(room.id))

			return 'successful'
		else:
			return 'failed'
	else:
		return 'failed'

@socketio.on('message')
def message(data):
	username = data['username']
	content = data['content']
	chatroom_name = data['chatroom_name']
	print(username, content, chatroom_name)

	user = db.session.query(Account).filter_by(name=username).first()
	room = db.session.query(Room).filter_by(name=chatroom_name).first()

	emit('new_message', {
		"room_id": str(room.id),
		"sender": username,
		"body": content
	}, room=str(room.id))
	
	new_msg = Message(content, False, user.id, room.id)
	
	db.session.add(new_msg)
	db.session.commit()
	room.last_active = new_msg.timeSent
	db.session.commit()

@socketio.on('join')
def join(data):
	chatroom_name = data['chatroom_name']
	room = db.session.query(Room).filter_by(name=chatroom_name).first()
	join_room(str(room.id))

@socketio.on('leave')
def leave(data):
	username = data['username']
	chatroom_name = data['chatroom_name']
	user = db.session.query(Account).filter_by(name=username).first()
	room = db.session.query(Room).filter_by(name=chatroom_name).first()
	relation = db.session.query(Belong).filter_by(account_id=user.id, room_id=room.id).first()
	db.session.delete(relation)
	db.session.commit()
	
	if room.db_room_account_rel == []:
		db.session.delete(room)
		db.session.commit()
	
	leave_room(str(room.id))

	emit('member_left', {
		"room_id": str(room.id),
		'chatroom_name': chatroom_name,
		'left_member': username
	}, room=str(room.id))

@socketio.on('emoji_theme')
def emoji_theme_change(data):
	chatroom_id = data['chatroom_id']
	emoji_index = data['emoji_index']
	theme_index = data['theme_index']

	room = db.session.query(Room).filter_by(id=int(chatroom_id)).first()
	room.emoji_id = emoji_index
	room.theme_id = theme_index
	db.session.commit()

	emit('emoji_theme_out', {
		"room_id": chatroom_id,
		'chatroom_name': room.name,
		'emoji_index': emoji_index,
		'theme_index': theme_index
	}, room=chatroom_id)

@socketio.on('nickname_change')
def nickname_change(data):
	chatroom_id = data['room_id']
	member_name = data['username']
	nickname = data['nickname']
	
	room = db.session.query(Room).filter_by(id=int(chatroom_id)).first()
	member = db.session.query(Account).filter_by(name=member_name).first()
	b = db.session.query(Belong).filter_by(_account_rel=member, _room_rel=room).first()
	b.nickname = nickname
	db.session.commit()
	
	emit('nickname_change_out', {
		"room_id": chatroom_id,
		'username': member_name,
		'new_nickname': nickname
	}, room=chatroom_id)

@socketio.on('init')
def init(data):
	username = data['username']
	cookie = data['cookie']
	personal_room_id = request.sid
	
	user_cookie = db.session.query(Cookie).filter_by(username=username, cookie=cookie).first()
	user_cookie.personal_room = personal_room_id
	db.session.commit()