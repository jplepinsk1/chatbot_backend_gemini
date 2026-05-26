import eventlet
eventlet.monkey_patch()

from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from google import genai
from google.genai import types
from threading import Timer
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*")

# Inicializa o cliente do Gemini
client = genai.Client(api_key=config.GEMINI_API_KEY)

# DICIONÁRIOS GLOBAIS: Estruturas de dados para gerenciar o estado da aplicação
active_chats = {}
inactivity_timers = {}

# ==============================================================================
# FUNÇÕES DE SUPORTE (Regras de Negócio)
# ==============================================================================

def encerrar_por_inatividade(sid):
    """Disparada automaticamente quando o cronômetro do usuário zera."""
    print(f"[TIMEOUT] Sessão {sid} encerrada por inatividade.")
    try:
        # Avisa o front-end específico pelo canal dele (room=sid)
        socketio.emit('erro', {'erro': 'Sessão encerrada por inatividade.'}, room=sid)
        socketio.disconnect(sid)
    except Exception as e:
        print(f"Erro ao desconectar {sid} por timeout: {e}")


def resetar_timer_usuario(sid):
    """Zera o cronômetro antigo e inicia um novo para o usuário atual."""
    # Se o usuário já tiver um timer rodando, cancela ele primeiro
    if sid in inactivity_timers:
        inactivity_timers[sid].cancel()
    
    # Cria um novo temporizador de 10 minutos para este SID
    novo_timer = Timer(config.TIMEOUT_INATIVIDADE, encerrar_por_inatividade, args=[sid])
    inactivity_timers[sid] = novo_timer
    novo_timer.start()


def obter_ou_criar_chat(sid):
    """Busca o chat do usuário no dicionário ou cria um novo se não existir."""
    if sid not in active_chats:
        print(f"[IA] Criando nova sessão Gemini para o ID: {sid}")
        novo_chat = client.chats.create(
            model=config.MODEL_NAME,
            config=types.GenerateContentConfig(system_instruction=config.SYSTEM_INSTRUCTION)
        )
        active_chats[sid] = novo_chat
    return active_chats[sid]


def limpar_dados_usuario(sid):
    """Remove o usuário dos dicionários para liberar memória do servidor."""
    if sid in active_chats:
        del active_chats[sid]
    if sid in inactivity_timers:
        inactivity_timers[sid].cancel()
        del inactivity_timers[sid]
    print(f"[MEMÓRIA] Recursos liberados para o ID: {sid}")

# ==============================================================================
# EVENTOS DO SOCKET.IO (Camada de Comunicação)
# ==============================================================================

@app.route("/")
def index():
    return jsonify({"status": "running", "message": "Servidor WebSocket ativo"}), 200


@socketio.on('connect')
def handle_connect():
    user_sid = request.sid
    print(f"[CONEXÃO] Cliente conectado: {user_sid}")
    try:
        obter_ou_criar_chat(user_sid)
        resetar_timer_usuario(user_sid)
        
        emit('status_conexao', {
            'data': 'Conectado com sucesso!', 
            'session_id': user_sid
        })
    except Exception as e:
        app.logger.error(f"Erro no connect para {user_sid}: {e}", exc_info=True)
        emit('erro', {'erro': 'Falha ao inicializar o chat no servidor.'})


@socketio.on('enviar_mensagem')
def handle_enviar_mensagem(data):
    user_sid = request.sid
    mensagem_usuario = data.get("mensagem")

    if not mensagem_usuario:
        emit('erro', {"erro": "Mensagem não pode ser vazia."})
        return

    try:
        # Interagiu? Reseta o cronômetro de 10 minutos dele
        resetar_timer_usuario(user_sid)
        
        # Recupera o chat correto desse usuário
        user_chat = obter_ou_criar_chat(user_sid)
        
        # Envia os pedaços (stream) para o front-end em tempo real
        response_stream = user_chat.send_message_stream(mensagem_usuario)
        for chunk in response_stream:
            emit('resposta_bot', {"texto": chunk.text})
            
        emit('resposta_bot_fim')

    except Exception as e:
        app.logger.error(f"Erro em enviar_mensagem para {user_sid}: {e}", exc_info=True)
        emit('erro', {"erro": "Ocorreu um erro ao processar sua mensagem."})


@socketio.on('disconnect')
def handle_disconnect():
    user_sid = request.sid
    print(f"[DESCONEXÃO] Cliente desconectado: {user_sid}")
    limpar_dados_usuario(user_sid)


if __name__ == "__main__":
    socketio.run(app, debug=True)