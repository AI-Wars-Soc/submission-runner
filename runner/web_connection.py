from flask_socketio import emit, Namespace


class WebConnection(Namespace):
    def on_connect(self):
        pass

    def on_disconnect(self):
        pass

    def on_get(self, data):
        emit('response', data)
