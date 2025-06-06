from flask import Flask, request, session
from flask_socketio import SocketIO, emit
from google import genai
from google.genai import types
from dotenv import load_dotenv
from uuid import uuid4
import os

# Carrega variáveis de ambiente (inclui a chave da API Gemini)
load_dotenv()
client = genai.Client(api_key=os.getenv("GENAI_KEY"))

# Instruções que serão enviadas como prompt de sistema
instrucoes = """
Você é um professor de Língua Portuguesa, especialista em gramática normativa, redação, ortografia, interpretação de texto, morfologia, sintaxe e literatura brasileira.

Sua missão é ensinar, corrigir e orientar alunos de forma didática, clara, gentil e objetiva.  
Explique os conteúdos de forma simples, com exemplos práticos quando necessário.  
Sempre que o aluno cometer erros gramaticais, de pontuação ou de concordância, corrija com paciência e mostre o motivo.  

Não use listas com marcadores ou tópicos. Prefira respostas diretas, fluidas e com tom acolhedor.  
Você está aqui para ajudar o aluno a **aprender português de verdade**, sem julgamentos, sempre incentivando a evolução.

Só responda perguntas relacionadas à Língua Portuguesa.  
Se o aluno perguntar algo fora desse tema, oriente-o a fazer perguntas sobre gramática, interpretação de texto ou redação.
"""


# Inicializa o Flask e o SocketIO
app = Flask(__name__)
app.secret_key = "uma_chave_secreta_muito_forte_padrao"
socketio = SocketIO(app, cors_allowed_origins="*")

# Dicionário para armazenar sessões ativas por usuário
active_chats = {}

# Gerencia a criação e reutilização de chats por sessão
def get_user_chat():
    if 'session_id' not in session:
        session['session_id'] = str(uuid4())
        print(f"Nova sessão Flask criada: {session['session_id']}")
    session_id = session['session_id']

    if session_id not in active_chats or active_chats[session_id] is None:
        print(f"Criando novo chat Gemini para session_id: {session_id}")
        try:
            chat_session = client.chats.create(
                model="gemini-2.0-flash",
                config=types.GenerateContentConfig(system_instruction=instrucoes)
            )
            active_chats[session_id] = chat_session
            print(f"Novo chat Gemini criado e armazenado para {session_id}")
        except Exception as e:
            app.logger.error(f"Erro ao criar chat Gemini para {session_id}: {e}")
            raise
    return active_chats[session_id]

# Evento de conexão inicial
@socketio.on('connect')
def handle_connect():
    print(f"Cliente conectado: {request.sid}")
    try:
        get_user_chat()
        user_session_id = session.get('session_id', 'N/A')
        print(f"Sessão Flask para {request.sid} usa session_id: {user_session_id}")
        emit('status_conexao', {'data': 'Conectado com sucesso!', 'session_id': user_session_id})
    except Exception as e:
        app.logger.error(f"Erro durante o evento connect para {request.sid}: {e}")
        emit('erro', {'erro': 'Falha ao inicializar a sessão de chat no servidor.'})

# Evento que lida com o envio de mensagens do usuário
@socketio.on('enviar_mensagem')
def handle_enviar_mensagem(data):
    try:
        mensagem_usuario = data.get("mensagem")
        session_id = session.get('session_id', request.sid)
        app.logger.info(f"Mensagem recebida de {session_id}: {mensagem_usuario}")

        if not mensagem_usuario or not mensagem_usuario.strip():
            emit('erro', {"erro": "Mensagem não pode ser vazia."})
            return

        user_chat = get_user_chat()
        if user_chat is None:
            emit('erro', {"erro": "Sessão de chat não pôde ser estabelecida."})
            return

        resposta_gemini = user_chat.send_message(mensagem_usuario)
        if hasattr(resposta_gemini, 'text'):
            resposta_texto = resposta_gemini.text
        else:
            resposta_texto = resposta_gemini.candidates[0].content.parts[0].text

        emit('nova_mensagem', {"remetente": "bot", "texto": resposta_texto})
        app.logger.info(f"Resposta enviada para {session_id}: {resposta_texto}")

    except Exception as e:
        if hasattr(e, 'args') and e.args and '503' in str(e.args[0]):
            mensagem_erro = "O modelo está sobrecarregado no momento. Por favor, tente novamente em instantes."
        else:
            mensagem_erro = f"Ocorreu um erro no servidor: {str(e)}"
        session_id = session.get('session_id', request.sid)
        app.logger.error(f"Erro ao processar 'enviar_mensagem' para {session_id}: {e}")
        emit('erro', {"erro": mensagem_erro})

# Evento de desconexão do usuário
@socketio.on('disconnect')
def handle_disconnect():
    print(f"Cliente desconectado: {request.sid}, session_id: {session.get('session_id', 'N/A')}")

# Inicializa o servidor
if __name__ == "__main__":
    socketio.run(app, debug=False, host='0.0.0.0', port=10000)


