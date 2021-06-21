import socketio

from runner import web_connection, views

app = socketio.WSGIApp(web_connection.sio, views.app)
