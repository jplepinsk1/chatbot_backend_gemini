import asyncio
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from google import genai
from google.genai import types
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Trocamos o Eventlet pelo modo nativo 'asyncio' do Flask-SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='asyncio')

# Inicializa o cliente da API
client = genai.Client(api_key=config.GEMINI_API_KEY)

# DICIONÁRIOS GLOBAIS: Estruturas de dados limpas em memória
active_chats = {}
inactivity_tasks = {}  # Agora armazena tarefas assíncronas em vez de Threads nativas

# ==============================================================================
# FUNÇÕES DE SUPORTE (Regras de Negócio Assíncronas)
# ==============================================================================

async def encerrar_por_inatividade(sid):
    """Aguarda o tempo limite de forma não-bloqueante. Se o tempo esgotar, desliga o usuário."""
    try:
        await asyncio.sleep(config.TIMEOUT_INATIVIDADE)
        print(f"[TIMEOUT] Sessão {sid} encerrada por inatividade.")
        
        # Envia aviso e desconecta o canal WebSocket de forma segura
        socketio.emit('erro', {'erro': 'Sessão encerrada por inatividade.'}, room=sid)
        socketio.disconnect(sid)
    except asyncio.CancelledError:
        # A tarefa foi cancelada porque o usuário mandou mensagem a tempo
        pass

def resetar_timer_usuario(sid):
    """Cancela a espera antiga e agenda um novo ciclo de contagem assíncrona."""
    if sid in inactivity_tasks:
        inactivity_tasks[sid].cancel()
    
    # Cria uma tarefa em segundo plano que não pesa no servidor
    inactivity_tasks[sid] = asyncio.create_task(encerrar_por_inatividade(sid))


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
    if sid in inactivity_tasks:
        inactivity_tasks[sid].cancel()
        del inactivity_tasks[sid]
    print(f"[MEMÓRIA] Recursos liberados para o ID: {sid}")

# ==============================================================================
# EVENTOS DO SOCKET.IO (Camada de Transporte)
# ==============================================================================

@app.route("/")
def index():
    return jsonify({"status": "running", "message": "Servidor WebSocket Nativo Ativo"}), 200


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
        resetar_timer_usuario(user_sid)
        user_chat = obter_ou_criar_chat(user_sid)
        
        # O stream consome os dados nativamente sem travar o loop do asyncio
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
    # Roda o app usando o motor assíncrono padrão
    socketio.run(app, debug=True)