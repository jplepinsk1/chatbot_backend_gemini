import eventlet
eventlet.monkey_patch()
eventlet.hubs.use_hub("select")

from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from google import genai
from google.genai import types
from threading import Timer
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*")

client = genai.Client(api_key=config.GEMINI_API_KEY)

active_chats = {}
inactivity_timers = {}

def encerrar_por_inatividade(sid):
    print(f"[TIMEOUT] Sessão {sid} encerrada por inatividade.")
    try:
        socketio.emit('erro', {'erro': 'Sessão encerrada por inatividade.'}, room=sid)
        socketio.disconnect(sid)
    except Exception as e:
        print(f"Erro ao desconectar {sid}: {e}")

def resetar_timer_usuario(sid):
    if sid in inactivity_timers:
        inactivity_timers[sid].cancel()
    novo_timer = Timer(config.TIMEOUT_INATIVIDADE, encerrar_por_inatividade, args=[sid])
    inactivity_timers[sid] = novo_timer
    novo_timer.start()

def obter_ou_criar_chat(sid):
    if sid not in active_chats:
        print(f"[IA] Criando nova sessão Gemini para o ID: {sid}")
        active_chats[sid] = client.chats.create(
            model=config.MODEL_NAME,
            config=types.GenerateContentConfig(system_instruction=config.SYSTEM_INSTRUCTION)
        )
    return active_chats[sid]

def limpar_dados_usuario(sid):
    if sid in active_chats:
        del active_chats[sid]
    if sid in inactivity_timers:
        inactivity_timers[sid].cancel()
        del inactivity_timers[sid]

@app.route("/")
def index():
    return jsonify({"status": "running"}), 200

@socketio.on('connect')
def handle_connect():
    user_sid = request.sid
    try:
        obter_ou_criar_chat(user_sid)
        resetar_timer_usuario(user_sid)
        emit('status_conexao', {'session_id': user_sid})
    except Exception as e:
        emit('erro', {'erro': 'Falha ao inicializar.'})

@socketio.on('enviar_mensagem')
def handle_enviar_mensagem(data):
    user_sid = request.sid
    mensagem = data.get("mensagem")
    if not mensagem: return

    try:
        resetar_timer_usuario(user_sid)
        user_chat = obter_ou_criar_chat(user_sid)
        response_stream = user_chat.send_message_stream(mensagem)
        for chunk in response_stream:
            emit('resposta_bot', {"texto": chunk.text})
        emit('resposta_bot_fim')
    except Exception as e:
        emit('erro', {"erro": f"Erro: {str(e)}"})

@socketio.on('disconnect')
def handle_disconnect():
    limpar_dados_usuario(request.sid)

if __name__ == "__main__":
    socketio.run(app, debug=True)