import os
import json
import re
from datetime import datetime
from pathlib import Path
import subprocess

# Configurações
TRANSCRIPTS_DIR = "transcripts"
OUTPUT_DIR = "docs"  # GitHub Pages usa /docs ou /gh-pages
GITHUB_REPO_OWNER = "iccommercedigital-art"
GITHUB_REPO_NAME = "transcripts"

# CSS personalizado para as páginas
CSS_CONTENT = """
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #333;
    line-height: 1.6;
    padding: 20px;
}

.container {
    max-width: 1000px;
    margin: 0 auto;
}

header {
    background: white;
    border-radius: 10px;
    padding: 30px;
    margin-bottom: 30px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
}

header h1 {
    color: #667eea;
    margin-bottom: 10px;
    font-size: 2.5em;
}

header p {
    color: #666;
    font-size: 1.1em;
}

.breadcrumb {
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid #eee;
    font-size: 0.9em;
}

.breadcrumb a {
    color: #667eea;
    text-decoration: none;
    margin: 0 5px;
}

.breadcrumb a:hover {
    text-decoration: underline;
}

main {
    background: white;
    border-radius: 10px;
    padding: 30px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
}

.transcript {
    margin: 20px 0;
    padding: 20px;
    border-left: 4px solid #667eea;
    background: #f8f9ff;
    border-radius: 5px;
}

.transcript-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
    padding-bottom: 15px;
    border-bottom: 2px solid #667eea;
}

.transcript-id {
    font-size: 1.3em;
    font-weight: bold;
    color: #667eea;
}

.transcript-date {
    font-size: 0.9em;
    color: #999;
}

.message {
    margin: 15px 0;
    padding: 12px;
    background: white;
    border-radius: 5px;
    border-left: 3px solid #764ba2;
}

.message-author {
    font-weight: bold;
    color: #667eea;
    font-size: 0.9em;
    margin-bottom: 5px;
}

.message-time {
    color: #999;
    font-size: 0.85em;
}

.message-content {
    margin-top: 8px;
    color: #333;
    word-wrap: break-word;
}

.message-attachment {
    margin-top: 10px;
    padding: 10px;
    background: #f0f0f0;
    border-radius: 5px;
    font-size: 0.9em;
    color: #666;
}

.stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
    margin-bottom: 20px;
}

.stat-card {
    padding: 15px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 8px;
    text-align: center;
}

.stat-value {
    font-size: 2em;
    font-weight: bold;
    margin-bottom: 5px;
}

.stat-label {
    font-size: 0.9em;
    opacity: 0.9;
}

.transcript-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 20px;
}

.transcript-card {
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 20px;
    transition: all 0.3s ease;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.transcript-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 5px 20px rgba(102, 126, 234, 0.3);
    border-color: #667eea;
}

.transcript-card a {
    color: #667eea;
    text-decoration: none;
    font-weight: bold;
    font-size: 1.2em;
    display: block;
    margin-bottom: 10px;
}

.transcript-card a:hover {
    text-decoration: underline;
}

.card-date {
    color: #999;
    font-size: 0.9em;
    margin-bottom: 10px;
}

.card-messages {
    color: #666;
    font-size: 0.9em;
}

.card-badge {
    display: inline-block;
    margin-top: 10px;
    padding: 5px 10px;
    background: #667eea;
    color: white;
    border-radius: 20px;
    font-size: 0.8em;
}

footer {
    text-align: center;
    color: white;
    margin-top: 30px;
    padding-top: 20px;
}

footer a {
    color: white;
    text-decoration: none;
}

footer a:hover {
    text-decoration: underline;
}

@media (max-width: 768px) {
    header h1 {
        font-size: 1.8em;
    }
    
    .transcript-list {
        grid-template-columns: 1fr;
    }
    
    .transcript-header {
        flex-direction: column;
        align-items: flex-start;
    }
}
"""

def parse_transcript(content):
    """Parse transcript content and extract structured data"""
    lines = content.strip().split('\n')
    
    # Extrai ID do ticket do header
    ticket_id = None
    for line in lines[:5]:
        match = re.search(r'#([a-f0-9]+)', line)
        if match:
            ticket_id = match.group(1)
            break
    
    # Extrai data e total de mensagens
    data_criacao = None
    total_mensagens = 0
    
    for line in lines:
        if "Data de Criação:" in line:
            data_criacao = line.split("Data de Criação:")[-1].strip()
        if "Total de Mensagens:" in line:
            total_mensagens = int(line.split("Total de Mensagens:")[-1].strip())
    
    # Extrai mensagens
    messages = []
    in_history = False
    current_message = None
    
    for line in lines:
        if "HISTÓRICO DE CONVERSA" in line:
            in_history = True
            continue
        
        if not in_history:
            continue
        
        if line.strip() == "" or "=" * 5 in line:
            continue
        
        # Detecta autor e hora: [DD/MM HH:MM:SS] autor:
        match = re.match(r'\[(\d{2}/\d{2} \d{2}:\d{2}:\d{2})\]\s+(\w+):\s*(.*)', line)
        
        if match:
            if current_message:
                messages.append(current_message)
            
            time, author, content = match.groups()
            current_message = {
                'time': time,
                'author': author,
                'content': content,
                'attachments': []
            }
        elif current_message and line.strip():
            if "📎" in line or "Arquivo:" in line:
                current_message['attachments'].append(line.strip())
            elif line.startswith("📌"):
                current_message['content'] += f"\n{line.strip()}"
            else:
                current_message['content'] += f"\n{line}"
    
    if current_message:
        messages.append(current_message)
    
    return {
        'ticket_id': ticket_id,
        'data_criacao': data_criacao,
        'total_mensagens': total_mensagens,
        'messages': messages
    }

def generate_transcript_page(filename, data):
    """Generate HTML page for a single transcript"""
    ticket_id = data['ticket_id'] or filename.replace('.txt', '').replace('.html', '')
    data_criacao = data['data_criacao'] or "Data desconhecida"
    
    messages_html = ""
    for msg in data['messages']:
        attachments_html = ""
        if msg['attachments']:
            for att in msg['attachments']:
                attachments_html += f'<div class="message-attachment">📎 {att}</div>'
        
        messages_html += f"""
        <div class="message">
            <div class="message-author">{msg['author']}</div>
            <div class="message-time">[{msg['time']}]</div>
            <div class="message-content">{msg['content']}</div>
            {attachments_html}
        </div>
        """
    
    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcrição do Ticket #{ticket_id}</title>
    <style>{CSS_CONTENT}</style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎫 Transcrição do Ticket #{ticket_id}</h1>
            <p>Visualização do histórico de conversa</p>
            <div class="breadcrumb">
                <a href="index.html">← Voltar para índice</a>
            </div>
        </header>
        
        <main>
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value">{data['total_mensagens']}</div>
                    <div class="stat-label">Total de Mensagens</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{data_criacao}</div>
                    <div class="stat-label">Data de Criação</div>
                </div>
            </div>
            
            <div class="transcript">
                <div class="transcript-header">
                    <div class="transcript-id">#{ticket_id}</div>
                    <div class="transcript-date">{data_criacao}</div>
                </div>
                
                {messages_html}
            </div>
        </main>
        
        <footer>
            <p>📊 Página gerada automaticamente pelo Bot de Tickets</p>
            <p><a href="https://github.com/iccommercedigital-art/transcripts">Repositório GitHub</a></p>
        </footer>
    </div>
</body>
</html>"""
    
    return html_content

def generate_index_page(transcripts_info):
    """Generate main index page with list of all transcripts"""
    cards_html = ""
    
    # Ordena por data (mais recentes primeiro)
    def sort_key(x):
        data = x.get('data_criacao', '')
        return data if data else '0000-00-00'
    
    sorted_transcripts = sorted(transcripts_info, key=sort_key, reverse=True)
    
    for info in sorted_transcripts:
        ticket_id = info['ticket_id']
        html_filename = f"{ticket_id}.html"
        
        cards_html += f"""
        <div class="transcript-card">
            <a href="{html_filename}">🎫 Ticket #{ticket_id}</a>
            <div class="card-date">📅 {info.get('data_criacao', 'Data desconhecida')}</div>
            <div class="card-messages">💬 {info.get('total_mensagens', 0)} mensagens</div>
            <div class="card-badge">Ver Detalhes →</div>
        </div>
        """
    
    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcrições de Tickets - Bot Support</title>
    <style>{CSS_CONTENT}</style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 Transcrições de Tickets</h1>
            <p>Histórico completo de todas as conversas de suporte</p>
        </header>
        
        <main>
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value">{len(transcripts_info)}</div>
                    <div class="stat-label">Total de Tickets</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{sum(t.get('total_mensagens', 0) for t in transcripts_info)}</div>
                    <div class="stat-label">Total de Mensagens</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{datetime.now().strftime('%d/%m/%Y')}</div>
                    <div class="stat-label">Última Atualização</div>
                </div>
            </div>
            
            <h2 style="margin-top: 30px; margin-bottom: 20px; color: #667eea;">📋 Todos os Tickets</h2>
            <div class="transcript-list">
                {cards_html}
            </div>
        </main>
        
        <footer>
            <p>📊 Página gerada automaticamente pelo Bot de Tickets</p>
            <p>🔗 Acesse em: <a href="https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}">GitHub</a></p>
            <p style="margin-top: 20px; font-size: 0.9em; opacity: 0.8;">
                Última atualização: {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}
            </p>
        </footer>
    </div>
</body>
</html>"""
    
    return html_content

def main():
    """Main function to generate all pages"""
    
    # Cria o diretório de saída
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    
    # Verifica se a pasta de transcritos existe
    if not os.path.exists(TRANSCRIPTS_DIR):
        print(f"❌ Pasta '{TRANSCRIPTS_DIR}' não encontrada!")
        return
    
    print(f"🔍 Processando transcritos de '{TRANSCRIPTS_DIR}'...\n")
    
    transcripts_info = []
    transcript_files = []
    
    # Lista todos os arquivos de transcrição
    for filename in os.listdir(TRANSCRIPTS_DIR):
        if filename.endswith(('.txt', '.html')):
            filepath = os.path.join(TRANSCRIPTS_DIR, filename)
            transcript_files.append((filename, filepath))
    
    if not transcript_files:
        print("⚠️ Nenhum arquivo de transcrição encontrado!")
        return
    
    # Processa cada arquivo
    for filename, filepath in sorted(transcript_files):
        print(f"📝 Processando: {filename}")
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse do conteúdo
            data = parse_transcript(content)
            ticket_id = data['ticket_id'] or filename.replace('.txt', '').replace('.html', '')
            
            # Gera página HTML
            html_page = generate_transcript_page(filename, data)
            html_filename = f"{ticket_id}.html"
            html_path = os.path.join(OUTPUT_DIR, html_filename)
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_page)
            
            print(f"   ✅ Gerado: {html_filename}")
            
            # Armazena info para o índice
            transcripts_info.append({
                'ticket_id': ticket_id,
                'data_criacao': data['data_criacao'],
                'total_mensagens': data['total_mensagens']
            })
        
        except Exception as e:
            print(f"   ❌ Erro ao processar: {e}")
    
    # Gera página de índice
    print(f"\n📑 Gerando página de índice...")
    index_html = generate_index_page(transcripts_info)
    index_path = os.path.join(OUTPUT_DIR, "index.html")
    
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_html)
    
    print(f"✅ Índice gerado: index.html")
    
    print(f"\n{'='*50}")
    print(f"✨ Sucesso! {len(transcripts_info)} páginas geradas em '{OUTPUT_DIR}'")
    print(f"{'='*50}")
    print(f"\n📂 Arquivos gerados:")
    print(f"   📄 {OUTPUT_DIR}/index.html (Página Principal)")
    for info in transcripts_info:
        print(f"   📄 {OUTPUT_DIR}/{info['ticket_id']}.html")
    
    print(f"\n🚀 Próximos passos:")
    print(f"   1. Verifique os arquivos gerados em {OUTPUT_DIR}/")
    print(f"   2. Faça push para o GitHub usando:")
    print(f"      git add {OUTPUT_DIR}/")
    print(f"      git commit -m 'Atualizar transcrições'")
    print(f"      git push origin main")
    print(f"   3. Acesse: https://{GITHUB_REPO_OWNER}.github.io/{GITHUB_REPO_NAME}/")

if __name__ == "__main__":
    main()
