import cv2
import numpy as np
import math
import csv
import os
import time
import threading
from flask import Flask, Response, render_template_string, request

# ============================================================================
# 1. CONFIGURAÇÕES E CONSTANTES
# ============================================================================

# Nome do arquivo de banco de dados (deve estar na mesma pasta)
ARQUIVO_CSV = "Cores e Figuras.xlsx - Página1.csv"

# --- CALIBRAÇÃO DE CORES (Baseada na Imagem 1) ---
# A lógica é: Detectar o que é ÁGUA e inverter para achar objetos.
CALIB_AGUA_MIN = np.array([0, 0, 0])
CALIB_AGUA_MAX = np.array([97, 64, 167])

# --- CLASSIFICAÇÃO DE OBJETOS ---
MIN_OLEO = np.array([0, 0, 0])
MAX_OLEO = np.array([180, 255, 90]) 

MIN_ALGA = np.array([0, 0, 20])      
MAX_ALGA = np.array([180, 100, 160]) 

AREA_MINIMA_GERAL = 5        
AREA_MAXIMA_ALGA = 150       
AREA_MINIMA_OLEO = 151  

# Variáveis Globais de Imagem
frame_raw = None       # Imagem "crua" da câmera (para o preview)
frame_analisado = None # Imagem processada com os desenhos (para o relatório)
lock = threading.Lock()

app = Flask(__name__)

# ============================================================================
# 2. FUNÇÕES AUXILIARES E BANCO DE DADOS
# ============================================================================

def carregar_banco_dados_navios():
    """Lê o CSV e carrega MMSI e Cores na memória RAM"""
    db = []
    if not os.path.exists(ARQUIVO_CSV):
        print(f"AVISO: {ARQUIVO_CSV} não encontrado.")
        return []
    try:
        with open(ARQUIVO_CSV, 'r', encoding='utf-8') as f:
            leitor = csv.reader(f)
            next(leitor) # Pula cabeçalho
            for linha in leitor:
                if len(linha) >= 6:
                    try:
                        # Colunas 3, 4, 5 são R, G, B
                        r, g, b = int(linha[3]), int(linha[4]), int(linha[5])
                        db.append({'mmsi': linha[1], 'rgb': (r, g, b)})
                    except: continue
        return db
    except Exception as e:
        print(f"Erro no CSV: {e}")
        return []

# Carrega o banco ao iniciar o script
DB_NAVIOS = carregar_banco_dados_navios()

def desenhar_hud(img, n_navios, n_oleo, poluidor, lista_navios):
    """Desenha as informações na lateral da imagem processada"""
    h, w = img.shape[:2]
    w_hud = 260
    tela = np.zeros((h, w + w_hud, 3), dtype=np.uint8)
    tela[0:h, 0:w] = img
    
    # Fundo do HUD
    cv2.rectangle(tela, (w, 0), (w+w_hud, h), (20, 20, 20), -1)
    x, y = w + 15, 30
    fonte = cv2.FONT_HERSHEY_SIMPLEX
    
    cv2.putText(tela, "RELATORIO DE MISSAO", (x, y), fonte, 0.5, (0, 255, 255), 1)
    y += 40
    
    # Navios
    cv2.putText(tela, f"Navios na Area: {n_navios}", (x, y), fonte, 0.45, (0, 255, 0), 1)
    y += 20
    for nav in lista_navios:
        cv2.putText(tela, f"> MMSI: {nav['mmsi']}", (x, y), fonte, 0.4, (200, 255, 200), 1)
        y += 15
        
    y += 20
    # Óleo
    cor_oleo = (0, 0, 255) if n_oleo > 0 else (100, 100, 100)
    cv2.putText(tela, f"Manchas de Oleo: {n_oleo}", (x, y), fonte, 0.45, cor_oleo, 1)
    
    y += 40
    # Alerta Final
    if poluidor:
        cv2.rectangle(tela, (x-5, y-25), (w+w_hud-10, y+40), (0, 0, 150), -1)
        cv2.putText(tela, "ALERTA: POLUIDOR", (x, y), fonte, 0.5, (255, 255, 255), 2)
        cv2.putText(tela, f"MMSI: {poluidor['mmsi']}", (x, y+20), fonte, 0.45, (255, 255, 0), 2)
    else:
        cv2.putText(tela, "STATUS: SEGURO", (x, y), fonte, 0.6, (0, 255, 0), 2)
        
    return tela

# ============================================================================
# 3. NÚCLEO DE PROCESSAMENTO (Visão Computacional)
# ============================================================================

def processar_imagem_completa(img):
    """Roda apenas quando o botão é clicado. Faz a detecção pesada."""
    h_arena, w_arena = img.shape[:2]
    
    # 1. Conversão de Cor e Máscara
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Define o que é água e inverte a máscara para pegar objetos
    mask_agua = cv2.inRange(hsv, CALIB_AGUA_MIN, CALIB_AGUA_MAX)
    mask_obj = cv2.bitwise_not(mask_agua)
    
    # Limpeza de ruído
    kernel = np.ones((2,2), np.uint8)
    mask_obj = cv2.morphologyEx(mask_obj, cv2.MORPH_OPEN, kernel)
    
    contornos, _ = cv2.findContours(mask_obj, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    objs_navio = []
    objs_oleo = []
    
    for cnt in contornos:
        area = cv2.contourArea(cnt)
        
        # Filtros de Tamanho
        if area < AREA_MINIMA_GERAL: continue
        if area > (w_arena * h_arena) * 0.95: continue # Ignora tela cheia

        x, y, w, h = cv2.boundingRect(cnt)
        centro = (int(x + w/2), int(y + h/2))
        
        # Pega a cor média DENTRO do objeto
        mask_i = np.zeros((h_arena, w_arena), dtype=np.uint8)
        cv2.drawContours(mask_i, [cnt], -1, 255, -1)
        media_hsv = cv2.mean(hsv, mask=mask_i)[:3]
        media_bgr = cv2.mean(img, mask=mask_i)[:3]

        # --- LÓGICA DE CLASSIFICAÇÃO ---
        label = "NAVIO"
        cor_draw = (0, 0, 255) # Vermelho padrão navio desconhecido

        # Verifica se é OLEO
        checa_oleo = (MIN_OLEO[0] <= media_hsv[0] <= MAX_OLEO[0] and 
                      MIN_OLEO[1] <= media_hsv[1] <= MAX_OLEO[1] and 
                      MIN_OLEO[2] <= media_hsv[2] <= MAX_OLEO[2])
        
        # Verifica se é ALGA
        checa_alga = (MIN_ALGA[0] <= media_hsv[0] <= MAX_ALGA[0] and 
                      MIN_ALGA[1] <= media_hsv[1] <= MAX_ALGA[1] and 
                      MIN_ALGA[2] <= media_hsv[2] <= MAX_ALGA[2])

        if checa_oleo and area > AREA_MINIMA_OLEO:
            label = "OLEO"
        elif checa_alga and area <= AREA_MAXIMA_ALGA:
            label = "ALGA"

        # --- DESENHO NA TELA ---
        if label == "OLEO":
            objs_oleo.append({'pos': centro})
            cv2.drawContours(img, [cnt], -1, (0,0,255), 2)
            cv2.putText(img, "OLEO", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 2)
            
        elif label == "ALGA":
            cv2.circle(img, centro, 4, (180, 180, 180), -1)
            
        elif label == "NAVIO":
            # Busca MMSI no Banco de Dados
            b, g, r = media_bgr
            menor_d = float('inf')
            mmsi = "Desconhecido"
            
            for nav in DB_NAVIOS:
                r_db, g_db, b_db = nav['rgb']
                # Distância Euclidiana de Cor
                d = math.sqrt((r - r_db)**2 + (g - g_db)**2 + (b - b_db)**2)
                if d < menor_d:
                    menor_d = d
                    mmsi = nav['mmsi']
            
            # Se a cor for muito diferente, considera não listado
            if menor_d > 60: mmsi = "Nao Listado"
            
            objs_navio.append({'pos': centro, 'mmsi': mmsi})
            cv2.rectangle(img, (x,y), (x+w, y+h), (0, 255, 0), 2)
            if w > 15:
                cv2.putText(img, str(mmsi), (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)

    # 2. Detecção de Poluição (Distância Óleo -> Navio)
    poluidor = None
    for oleo in objs_oleo:
        menor_dist_navio = float('inf')
        navio_prox = None
        
        for navio in objs_navio:
            dist = math.dist(oleo['pos'], navio['pos'])
            if dist < menor_dist_navio:
                menor_dist_navio = dist
                navio_prox = navio
                
        # Se o navio está a menos de 200px do óleo
        if navio_prox and menor_dist_navio < 200:
            cv2.line(img, oleo['pos'], navio_prox['pos'], (0, 255, 255), 2)
            poluidor = navio_prox

    # 3. Retorna imagem com HUD
    return desenhar_hud(img, len(objs_navio), len(objs_oleo), poluidor, objs_navio)

# ============================================================================
# 4. THREAD DA CÂMERA (Background)
# ============================================================================

def camera_loop():
    global frame_raw, lock
    print("Iniciando câmera...")
    
    # Define o backend correto para evitar erro do GStreamer
    backend = cv2.CAP_V4L2
    
    # Tenta conectar na câmera 0 com o backend V4L2
    cap = cv2.VideoCapture(0, backend)
    
    if not cap.isOpened():
        print("Câmera 0 falhou. Tentando Câmera 1...")
        cap = cv2.VideoCapture(1, backend)
    
    # --- CONFIGURAÇÕES CRÍTICAS PARA CÂMERA Jieli/HBVCAM ---
    # 1. Força o formato MJPEG (evita travamentos e erros de buffer)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
    
    # 2. Configura resolução de hardware direto para 640x480
    # Isso elimina a necessidade de fazer cv2.resize depois (economiza CPU)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    
    while True:
        ret, frame = cap.read()
        if ret:
            with lock:
                # O frame já vem em 640x480 do hardware, não precisa de resize
                frame_raw = frame
        else:
            print("Erro de leitura da câmera (tentando reconectar...)")
            time.sleep(2)
            # Ao reconectar, precisamos passar o backend e reconfigurar o MJPEG
            cap.open(0, backend)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
        time.sleep(0.04) # ~25 FPS

# ============================================================================
# 5. SERVIDOR WEB (Flask)
# ============================================================================

# HTML Template Principal
HTML_INDEX = """
<!DOCTYPE html>
<html>
<head>
    <title>Controle CubeSat</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background-color: #111; color: #0ff; font-family: monospace; text-align: center; margin: 0; padding: 0;}
        h1 { margin: 10px; border-bottom: 1px solid #333; padding-bottom: 10px; }
        .cam-container { position: relative; display: inline-block; border: 2px solid #333; }
        .btn-analisar {
            display: block; width: 80%; margin: 20px auto; padding: 15px;
            background: #005500; color: white; font-size: 1.2rem; font-weight: bold;
            border: none; border-radius: 8px; cursor: pointer; text-decoration: none;
        }
        .btn-analisar:active { background: #00ff00; color: black; }
    </style>
</head>
<body>
    <h1>CUBESAT AO VIVO</h1>
    <div class="cam-container">
        <img src="/video_stream" width="100%">
    </div>
    
    <form action="/analisar" method="post">
        <button class="btn-analisar" type="submit">CAPTURAR E ANALISAR AGORA</button>
    </form>
</body>
</html>
"""

# HTML Template Resultado
HTML_RESULTADO = """
<!DOCTYPE html>
<html>
<head>
    <title>Resultado CubeSat</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background-color: #222; color: #fff; font-family: sans-serif; text-align: center; }
        img { max-width: 100%; border: 3px solid #yellow; margin-top: 10px; }
        .btn-voltar {
            display: inline-block; margin-top: 20px; padding: 10px 30px;
            background: #444; color: #fff; text-decoration: none; border: 1px solid #fff;
        }
    </style>
</head>
<body>
    <h2 style="color: yellow;">ANALISE CONCLUIDA</h2>
    <img src="/imagem_processada_estatica">
    <br>
    <a href="/" class="btn-voltar">VOLTAR PARA CÂMERA</a>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_INDEX)

@app.route("/video_stream")
def video_stream():
    """Gera o vídeo MJPEG para o preview"""
    return Response(gerar_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/analisar", methods=['POST'])
def rota_analisar():
    """Gatilho: Pega o frame atual, processa e mostra o resultado"""
    global frame_raw, frame_analisado, lock
    
    with lock:
        if frame_raw is None: return "Câmera não pronta", 503
        img_copia = frame_raw.copy()
        
    # Processamento pesado acontece aqui
    frame_analisado = processar_imagem_completa(img_copia)
    
    # Salva backup em disco
    cv2.imwrite("resultado_cubesat.jpg", frame_analisado)
    
    return render_template_string(HTML_RESULTADO)

@app.route("/imagem_processada_estatica")
def imagem_estatica():
    """Serve a imagem estática corrigida para evitar erros de rede"""
    global frame_analisado
    
    if frame_analisado is None:
        if os.path.exists("resultado_cubesat.jpg"):
            frame_analisado = cv2.imread("resultado_cubesat.jpg")
        else:
            return "Sem imagem", 404

    # Codifica para JPG
    flag, encoded = cv2.imencode(".jpg", frame_analisado)
    if not flag: return "Erro encoding", 500
    
    # CONVERSÃO CRÍTICA PARA CORRIGIR O ERRO "MISMATCH"
    imagem_bytes = encoded.tobytes()
    
    return Response(imagem_bytes, 
                    mimetype="image/jpeg", 
                    headers={"Content-Length": len(imagem_bytes)})

def gerar_frames():
    global frame_raw, lock
    while True:
        with lock:
            if frame_raw is None: continue
            
            # Adiciona uma mira simples no preview
            preview = frame_raw.copy()
            h, w = preview.shape[:2]
            cv2.line(preview, (int(w/2)-15, int(h/2)), (int(w/2)+15, int(h/2)), (0,255,255), 1)
            cv2.line(preview, (int(w/2), int(h/2)-15), (int(w/2), int(h/2)+15), (0,255,255), 1)
            
            flag, encoded = cv2.imencode(".jpg", preview)
            if not flag: continue
            
        yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 
              bytearray(encoded) + b'\r\n')
        time.sleep(0.05) # Limita FPS do stream para economizar CPU

# ============================================================================
# MAIN
# ============================================================================
if __name__ == '__main__':
    # Inicia Thread da Câmera
    t = threading.Thread(target=camera_loop)
    t.daemon = True
    t.start()
    
    print("\n=========================================")
    print(" SISTEMA CUBESAT ONLINE")
    print(" Acesse: http://<IP_DO_RASPBERRY>:5000")
    print("=========================================\n")
    
    # Roda Servidor Flask

    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
