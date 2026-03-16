# 🎫 Bot de Tickets com Transcrição em GitHub

## 📋 Sistema de Transcrição

O bot agora gera automaticamente transcrições de todas as conversas em tickets e as hospeda no GitHub com URLs HTTPS acessíveis.

### ✨ Funcionalidades

- ✅ Transcrição automática de cada ticket ao ser fechado
- ✅ Arquivo backup local em `/transcripts/`
- ✅ Upload automático para GitHub
- ✅ URLs HTTPS públicas e acessíveis
- ✅ Integração com logs do Discord

### 🔧 Configuração

#### 1. Criar um Repositório GitHub

1. Vá para https://github.com/new
2. Crie um repositório público chamado `bot-tickets-transcripts`
3. Deixar público é importante para acessar os links HTTPS!

#### 2. Gerar Token de Acesso Pessoal

1. Vá para https://github.com/settings/tokens
2. Clique em "Generate new token" → "Generate new token (classic)"
3. Dê um nome descritivo (ex: "Bot Tickets Transcripts")
4. Selecione a permissão `repo` (acesso completo a repositórios)
5. Copie o token SEGURO

**ℹ️ IMPORTANTE**: Nunca compartilhe este token em público!

#### 3. Configurar o .env

```bash
# Copie o arquivo de exemplo
cp .env.example .env

# Edite o arquivo .env e preencha:
GITHUB_TOKEN=github_pat_seu_token_aqui
GITHUB_REPO_OWNER=seu_usuario_github
GITHUB_REPO_NAME=bot-tickets-transcripts
```

### 📊 Exemplo de Transcrição

```
╔════════════════════════════════════════════════╗
║          TRANSCRIÇÃO DO TICKET #a1b2c3d4      ║
╚════════════════════════════════════════════════╝

Data de Criação: 16/03/2026 23:30:45
Total de Mensagens: 15

==================================================
HISTÓRICO DE CONVERSA
==================================================

[16/03 23:31:12] usuario_teste:
Olá, tenho um problema com meu pedido!

[16/03 23:31:45] suporte_bot:
Olá! Poderia descrever o problema com mais detalhes?

[16/03 23:32:20] usuario_teste:
Meu pedido não chegou ainda...
  📎 Arquivo: comprovante.pdf (245 KB)
```

### 🔗 URLs de Acesso

Após fechar um ticket, você terá:

- **URL Raw** (para ler o arquivo): 
  ```
  https://raw.githubusercontent.com/seu_usuario/bot-tickets-transcripts/transcripts/ticket_a1b2c3d4_20260316_233045.txt
  ```

- **URL GitHub** (para visualizar):
  ```
  https://github.com/seu_usuario/bot-tickets-transcripts/blob/transcripts/ticket_a1b2c3d4_20260316_233045.txt
  ```

### 📤 Fluxo Automático

```
Ticket Fechado
    ↓
📝 Gera Transcrição Local
    ↓
💾 Salva em /transcripts/
    ↓
📤 Upload para GitHub
    ↓
🔗 Retorna URL HTTPS
    ↓
📊 Adiciona URL ao Embed de Log
    ↓
🗑️ Deleta Canal do Ticket
```

### ⚙️ Logs do Sistema

Ao fechar um ticket, você verá no console:

```
🎫 Gerando transcrição para ticket a1b2c3d4 no canal ticket-a1b2c3d4
📝 Iniciando geração de transcrição para ticket a1b2c3d4
📊 Total de mensagens coletadas: 15
💾 Transcrição salva em: transcripts/ticket_a1b2c3d4_20260316_233045.txt (2345 bytes)
✅ Transcrição gerada com sucesso: transcripts/ticket_a1b2c3d4_20260316_233045.txt
📤 Fazendo upload para GitHub...
📤 Iniciando upload de transcrição para GitHub...
✅ Transcrição enviada para GitHub com sucesso!
🔗 URL Raw: https://raw.githubusercontent.com/seu_usuario/bot-tickets-transcripts/transcripts/ticket_a1b2c3d4_20260316_233045.txt
🔗 URL GitHub: https://github.com/seu_usuario/bot-tickets-transcripts/blob/transcripts/ticket_a1b2c3d4_20260316_233045.txt
📄 Enviando transcrição: transcripts/ticket_a1b2c3d4_20260316_233045.txt
✅ Transcrição enviada com sucesso
```

### 🚨 Troubleshooting

#### "GitHub não está configurado"
- Verifique se preencheu todas as variáveis no `.env`
- Reinicie o bot após salvar o `.env`

#### "Erro no upload para GitHub: 401"
- Token inválido ou expirado
- Gere um novo token em https://github.com/settings/tokens

#### "Erro no upload para GitHub: 404"
- Repositório não existe ou nome incorreto
- Verifique `GITHUB_REPO_OWNER` e `GITHUB_REPO_NAME`

#### "Erro no upload para GitHub: 403"
- Repositório é privado (deve ser público!)
- Ou token sem permissão correta

### 📚 Mais Informações

- [Documentação GitHub API](https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28)
- [Criar Personal Access Token](https://github.com/settings/tokens/new)
- [Raw GitHub Links](https://stackoverflow.com/questions/25526/what-is-the-raw-content-github-link)
