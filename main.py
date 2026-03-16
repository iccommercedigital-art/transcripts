import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import uuid
import asyncio
from dotenv import load_dotenv
import google.auth
from google.oauth2 import service_account
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
import requests
import base64

# Carrega as variáveis de ambiente
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = os.getenv('GUILD_ID') # Opcional: para sincronização instantânea de comandos slash

# ================= CONFIGURAÇÃO VERTEX AI (GOOGLE CLOUD) =================
# 1. Coloque o arquivo JSON na mesma pasta do bot e mude o nome abaixo:
JSON_KEY_FILE = "project-1eb79017-df64-4e63-ac9-204474171108.json" 

AI_ENABLED = False
model_ia = None

# Tentar habilitar usando a Vertex AI e os créditos do Google Cloud
if os.path.exists(JSON_KEY_FILE):
    try:
        # Carrega as credenciais do arquivo JSON
        credentials = service_account.Credentials.from_service_account_file(JSON_KEY_FILE)
        
        # Inicializa a Vertex AI
        # O 'project' você encontra dentro do seu arquivo JSON (project_id)
        with open(JSON_KEY_FILE, 'r') as f:
            project_id = json.load(f)["project_id"]
            
        vertexai.init(project=project_id, location="us-central1", credentials=credentials)
        
        # Configura o modelo (Usando o 2.0-flash para melhor compatibilidade)
        model_ia = GenerativeModel("gemini-2.0-flash")
        AI_ENABLED = True
        print(f"✅ IA Vertex AI habilitada com sucesso (Projeto: {project_id})")
    except Exception as e:
        print(f"⚠️ Erro ao habilitar Vertex AI: {e}")
else:
    print(f"⚠️ Arquivo {JSON_KEY_FILE} não encontrado. IA desabilitada.")

# ================= CONFIGURAÇÃO GITHUB PARA TRANSCRIPTS =================
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO_OWNER = os.getenv('GITHUB_REPO_OWNER')
GITHUB_REPO_NAME = os.getenv('GITHUB_REPO_NAME')
GITHUB_TRANSCRIPTS_BRANCH = "transcripts"  # Branch para armazenar transcripts

GITHUB_ENABLED = False
if GITHUB_TOKEN and GITHUB_REPO_OWNER and GITHUB_REPO_NAME:
    GITHUB_ENABLED = True
    print(f"✅ GitHub configurado para armazenar transcripts - {GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}")
else:
    print(f"⚠️ GitHub não configurado. Configure as variáveis: GITHUB_TOKEN, GITHUB_REPO_OWNER, GITHUB_REPO_NAME no .env")

# ==========================================
# ESTRUTURA DO BANCO DE DADOS (RAM E JSON)
# ==========================================
DATA_FILE = "database.json"
db_lock = asyncio.Lock()

# Estrutura base em RAM (Paralelismo e Fila)
db_cache = {
    "configs": {
        "bot_settings": {
            "ticket_channel": None, 
            "manager_role": None,
            "bot_name": "Ticket Bot",
            "bot_status": "🎫 Gerenciando Tickets",
            "ia_prompt": "Você é um assistente de suporte profissional. Ajude o usuário resolver seu problema de forma clara e concisa."
        },
        "panels": {}, # Armazena as categorias de tickets com configurações
        "active_panel_msg": {"channel_id": None, "message_id": None}, # Rastreia o embed ativo
        "products": {}, # Armazena produtos para a IA
        "permissions": {
            "manager_roles": [],
            "support_roles": []
        }
    },
    "tickets": {
        "active": {}, # Tickets abertos em RAM
        "closed": {}, # Tickets fechados
        "queue": []   # Fila de processamento
    }
}

async def load_db():
    global db_cache
    if os.path.exists(DATA_FILE):
        async with db_lock:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                # Mescla recursiva para garantir que a estrutura base exista
                if "configs" in saved_data:
                    db_cache["configs"].update(saved_data["configs"])
                    # Garante que subchaves existem
                    if "bot_settings" in saved_data["configs"]:
                        if "bot_settings" not in db_cache["configs"]:
                            db_cache["configs"]["bot_settings"] = {}
                        db_cache["configs"]["bot_settings"].update(saved_data["configs"]["bot_settings"])
                    if "panels" in saved_data["configs"]:
                        db_cache["configs"]["panels"] = saved_data["configs"]["panels"]
                    if "products" not in db_cache["configs"]:
                        db_cache["configs"]["products"] = {}
                    if "products" in saved_data["configs"]:
                        db_cache["configs"]["products"] = saved_data["configs"]["products"]
                    if "permissions" not in db_cache["configs"]:
                        db_cache["configs"]["permissions"] = {"manager_roles": [], "support_roles": []}
                if "tickets" in saved_data:
                    db_cache["tickets"].update(saved_data["tickets"])
    else:
        await save_db()

async def save_db():
    async with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db_cache, f, indent=4, ensure_ascii=False)

# ==========================================
# COMPONENTES VISUAIS (UI) - MODALS E VIEWS
# ==========================================

# ===== MODALS =====
class BotCustomizeModal(discord.ui.Modal, title="Personalizar Bot"):
    name = discord.ui.TextInput(label="Nome do Bot", default="Ticket Bot", max_length=100)
    status = discord.ui.TextInput(label="Status/Presença", default="🎫 Gerenciando Tickets", max_length=128)
    
    async def on_submit(self, interaction: discord.Interaction):
        db_cache["configs"]["bot_settings"]["bot_name"] = str(self.name)
        db_cache["configs"]["bot_settings"]["bot_status"] = str(self.status)
        await save_db()
        
        # Atualiza a presença do bot
        await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.playing, 
            name=str(self.status)
        ))
        
        await interaction.response.send_message(
            f"✅ Bot configurado com sucesso!\n**Nome:** {self.name}\n**Status:** {self.status}",
            ephemeral=True
        )

class IAPromptModal(discord.ui.Modal, title="Configurar Prompt da IA"):
    prompt = discord.ui.TextInput(label="Prompt do Sistema", style=discord.TextStyle.long, 
                                   default="Você é um assistente de suporte profissional.")
    
    async def on_submit(self, interaction: discord.Interaction):
        db_cache["configs"]["bot_settings"]["ia_prompt"] = str(self.prompt)
        await save_db()
        
        await interaction.response.send_message(
            f"✅ Prompt da IA atualizado com sucesso!\n```\n{self.prompt}\n```",
            ephemeral=True
        )

class AddProductModal(discord.ui.Modal, title="Adicionar Novo Produto"):
    product_name = discord.ui.TextInput(label="Nome do Produto", max_length=100)
    product_desc = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.long, max_length=1024)
    
    async def on_submit(self, interaction: discord.Interaction):
        product_id = str(uuid.uuid4())[:8]
        if "products" not in db_cache["configs"]:
            db_cache["configs"]["products"] = {}
        db_cache["configs"]["products"][product_id] = {
            "name": str(self.product_name),
            "desc": str(self.product_desc),
            "info": "",
            "created_at": str(discord.utils.utcnow())
        }
        await save_db()
        
        await interaction.response.send_message(
            f"✅ Produto adicionado com sucesso!\n**ID:** `{product_id}`\n**Nome:** {self.product_name}",
            ephemeral=True
        )

class EditProductModal(discord.ui.Modal, title="Editar Informações do Produto"):
    info = discord.ui.TextInput(label="Adicionar/Editar Informação", style=discord.TextStyle.long, max_length=2000)
    
    def __init__(self, product_id):
        super().__init__()
        self.product_id = product_id
    
    async def on_submit(self, interaction: discord.Interaction):
        if "products" not in db_cache["configs"]:
            db_cache["configs"]["products"] = {}
        
        if self.product_id not in db_cache["configs"]["products"]:
            return await interaction.response.send_message("❌ Produto não encontrado.", ephemeral=True)
        
        old_info = db_cache["configs"]["products"][self.product_id].get("info", "")
        new_info = f"{old_info}\n\n[{discord.utils.utcnow().strftime('%d/%m %H:%M')}]: {self.info}" if old_info else str(self.info)
        
        db_cache["configs"]["products"][self.product_id]["info"] = new_info
        await save_db()
        
        await interaction.response.send_message(
            f"✅ Produto atualizado com sucesso!\n```\n{new_info}\n```",
            ephemeral=True
        )

class CreateTicketCategoryModal(discord.ui.Modal, title="Criar Categoria de Tickets"):
    category_name = discord.ui.TextInput(label="Nome da Categoria", max_length=100)
    category_desc = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.long, max_length=500)
    category_emoji = discord.ui.TextInput(label="Emoji", default="🎫", max_length=2)
    
    async def on_submit(self, interaction: discord.Interaction):
        category_id = str(uuid.uuid4())[:8]
        
        db_cache["configs"]["panels"][category_id] = {
            "name": str(self.category_name),
            "desc": str(self.category_desc),
            "icon": str(self.category_emoji),
            "embed_title": f"Atendimento: {self.category_name}",
            "embed_desc": str(self.category_desc),
            "embed_author": "Suporte",
            "embed_footer": "Responderemos em breve",
            "embed_color": "0x2F3136",
            "embed_banner": None,
            "embed_thumbnail": None,
            "responsible_roles": [],
            "allowed_roles": [],
            "working_hours": "24/7",
            "panel_button_type": "select",
            "created_at": str(discord.utils.utcnow())
        }
        await save_db()
        
        embed = discord.Embed(
            title="✅ Categoria Criada",
            description=f"Categoria de tickets **{self.category_name}** foi criada com sucesso!",
            color=discord.Color.green()
        )
        embed.add_field(name="ID da Categoria", value=f"`{category_id}`", inline=False)
        embed.add_field(name="Próximo Passo", value="Clique em 'Configurar Categoria' para definir permissões e horários", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ConfigTicketCategoryModal(discord.ui.Modal, title="Configurar Categoria de Tickets"):
    working_hours = discord.ui.TextInput(label="Horário (ex: 09:00-18:00 / 24/7)", default="24/7", max_length=50)
    notes = discord.ui.TextInput(label="Notas Adicionais", style=discord.TextStyle.long, max_length=500, required=False)
    
    def __init__(self, category_id):
        super().__init__()
        self.category_id = category_id
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.category_id not in db_cache["configs"]["panels"]:
            return await interaction.response.send_message("❌ Categoria não encontrada.", ephemeral=True)
        
        category = db_cache["configs"]["panels"][self.category_id]
        category["working_hours"] = str(self.working_hours)
        category["notes"] = str(self.notes) if self.notes else ""
        
        await save_db()
        
        embed = discord.Embed(
            title="✅ Categoria Configurada",
            description=f"Categoria **{category['name']}** foi atualizada!",
            color=discord.Color.green()
        )
        embed.add_field(name="Horário", value=str(self.working_hours), inline=True)
        embed.add_field(name="Notas", value=str(self.notes) if self.notes else "Nenhuma", inline=False)
        embed.add_field(name="Próximo Passo", value="Use os botões para adicionar responsáveis e permissões", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class EmbedTitleModal(discord.ui.Modal, title="Configurar Título"):
    title = discord.ui.TextInput(label="Título do Embed", max_length=256)
    
    def __init__(self, category_id):
        super().__init__()
        self.category_id = category_id
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.category_id not in db_cache["configs"]["panels"]:
            return
        db_cache["configs"]["panels"][self.category_id]["embed_title"] = str(self.title)
        await save_db()
        await interaction.response.send_message(f"✅ Título atualizado: **{self.title}**", ephemeral=True)

class EmbedDescriptionModal(discord.ui.Modal, title="Configurar Descrição"):
    desc = discord.ui.TextInput(label="Descrição do Embed", style=discord.TextStyle.long, max_length=2000)
    
    def __init__(self, category_id):
        super().__init__()
        self.category_id = category_id
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.category_id not in db_cache["configs"]["panels"]:
            return
        db_cache["configs"]["panels"][self.category_id]["embed_desc"] = str(self.desc)
        await save_db()
        await interaction.response.send_message(f"✅ Descrição atualizada", ephemeral=True)

class EmbedAuthorModal(discord.ui.Modal, title="Configurar Autor"):
    author = discord.ui.TextInput(label="Nome do Autor", max_length=256)
    
    def __init__(self, category_id):
        super().__init__()
        self.category_id = category_id
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.category_id not in db_cache["configs"]["panels"]:
            return
        db_cache["configs"]["panels"][self.category_id]["embed_author"] = str(self.author)
        await save_db()
        await interaction.response.send_message(f"✅ Autor atualizado: **{self.author}**", ephemeral=True)

class EmbedFooterModal(discord.ui.Modal, title="Configurar Rodapé"):
    footer = discord.ui.TextInput(label="Texto do Rodapé", max_length=256)
    
    def __init__(self, category_id):
        super().__init__()
        self.category_id = category_id
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.category_id not in db_cache["configs"]["panels"]:
            return
        db_cache["configs"]["panels"][self.category_id]["embed_footer"] = str(self.footer)
        await save_db()
        await interaction.response.send_message(f"✅ Rodapé atualizado: **{self.footer}**", ephemeral=True)

class EmbedColorModal(discord.ui.Modal, title="Configurar Cor"):
    color = discord.ui.TextInput(label="Cor (HEX: #FF0000 ou 0xFF0000)", default="0x2F3136", max_length=7)
    
    def __init__(self, category_id):
        super().__init__()
        self.category_id = category_id
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.category_id not in db_cache["configs"]["panels"]:
            return
        db_cache["configs"]["panels"][self.category_id]["embed_color"] = str(self.color)
        await save_db()
        await interaction.response.send_message(f"✅ Cor atualizada: **{self.color}**", ephemeral=True)

class EmbedBannerModal(discord.ui.Modal, title="Configurar Banner"):
    banner_url = discord.ui.TextInput(label="URL da Imagem de Banner", max_length=256, required=False)
    
    def __init__(self, category_id):
        super().__init__()
        self.category_id = category_id
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.category_id not in db_cache["configs"]["panels"]:
            return
        db_cache["configs"]["panels"][self.category_id]["embed_banner"] = str(self.banner_url) if self.banner_url else None
        await save_db()
        await interaction.response.send_message(f"✅ Banner atualizado", ephemeral=True)

class EmbedThumbnailModal(discord.ui.Modal, title="Configurar Miniatura"):
    thumbnail_url = discord.ui.TextInput(label="URL da Imagem de Miniatura", max_length=256, required=False)
    
    def __init__(self, category_id):
        super().__init__()
        self.category_id = category_id
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.category_id not in db_cache["configs"]["panels"]:
            return
        db_cache["configs"]["panels"][self.category_id]["embed_thumbnail"] = str(self.thumbnail_url) if self.thumbnail_url else None
        await save_db()
        await interaction.response.send_message(f"✅ Miniatura atualizada", ephemeral=True)

class PanelButtonTypeSelect(discord.ui.Select):
    """Select para escolher entre painel com Select ou com Buttons"""
    def __init__(self, category_id):
        self.category_id = category_id
        options = [
            discord.SelectOption(
                label="📋 Caixa de Seleção (Select)",
                description="Dropdown com lista de categorias",
                value="select",
                emoji="📋"
            ),
            discord.SelectOption(
                label="🔘 Botões (Buttons)",
                description="Botões individuais para cada categoria",
                value="buttons",
                emoji="🔘"
            )
        ]
        super().__init__(
            placeholder="Escolha como deseja exibir os tickets...",
            min_values=1, max_values=1,
            options=options,
            custom_id=f"panel_type_select_{category_id}"
        )
    
    async def callback(self, interaction: discord.Interaction):
        if self.category_id not in db_cache["configs"]["panels"]:
            return await interaction.response.send_message("❌ Categoria não encontrada.", ephemeral=True)
        
        button_type = self.values[0]
        db_cache["configs"]["panels"][self.category_id]["panel_button_type"] = button_type
        await save_db()
        
        type_name = "Caixa de Seleção (Select)" if button_type == "select" else "Botões (Buttons)"
        embed = discord.Embed(
            title="✅ Tipo de Painel Atualizado",
            description=f"O painel será exibido como: **{type_name}**",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class CategorySelectForMessage(discord.ui.Select):
    def __init__(self):
        panels = db_cache["configs"].get("panels", {})
        options = []
        
        if not panels:
            options.append(discord.SelectOption(label="Nenhuma categoria criada", value="none"))
        else:
            for cid, cdata in list(panels.items())[:25]:
                options.append(discord.SelectOption(
                    label=cdata.get("name", "Sem Nome")[:100],
                    description=f"ID: {cid}",
                    emoji=cdata.get("icon", "🎫"),
                    value=cid
                ))
        
        super().__init__(placeholder="Selecione a categoria...", min_values=1, max_values=1, 
                        options=options, custom_id="category_select_for_message")
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message("Nenhuma categoria criada.", ephemeral=True)
        
        category_id = self.values[0]
        
        # Agora abre o select de canais
        view = discord.ui.View()
        view.add_item(ChannelSelectForMessage(category_id, interaction.guild))
        
        embed = discord.Embed(
            title="📤 Selecione o Canal",
            description="Escolha em qual canal deseja enviar o painel de tickets:",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ChannelSelectForMessage(discord.ui.Select):
    def __init__(self, category_id, guild):
        self.category_id = category_id
        options = []
        
        if not guild or not guild.text_channels:
            options.append(discord.SelectOption(label="Nenhum canal disponível", value="none"))
        else:
            # Filtra apenas canais de texto disponíveis
            text_channels = [ch for ch in guild.text_channels[:25]]
            
            if not text_channels:
                options.append(discord.SelectOption(label="Sem canais disponíveis", value="none"))
            else:
                for channel in text_channels:
                    options.append(discord.SelectOption(
                        label=f"#{channel.name}",
                        description=channel.topic[:50] if channel.topic else "Sem tópico",
                        value=str(channel.id)
                    ))
        
        super().__init__(placeholder="Selecione um canal...", min_values=1, max_values=1, 
                        options=options, custom_id=f"channel_select_{category_id}")
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message("Nenhum canal disponível.", ephemeral=True)
        
        channel_id = int(self.values[0])
        channel = bot.get_channel(channel_id)
        
        if not channel:
            return await interaction.response.send_message("❌ Canal não encontrado.", ephemeral=True)
        
        # Constrói o embed baseado nas configurações da categoria
        category = db_cache["configs"]["panels"].get(self.category_id)
        if not category:
            return await interaction.response.send_message("❌ Categoria não encontrada.", ephemeral=True)
        
        try:
            color_value = int(category.get("embed_color", "0x2F3136"), 16) if isinstance(category.get("embed_color"), str) else 0x2F3136
        except:
            color_value = 0x2F3136
        
        embed = discord.Embed(
            title=category.get("embed_title", "Atendimento"),
            description=category.get("embed_desc", "Selecione uma categoria abaixo."),
            color=color_value
        )
        
        if category.get("embed_author"):
            embed.set_author(name=category.get("embed_author"))
        
        if category.get("embed_footer"):
            embed.set_footer(text=category.get("embed_footer"))
        
        if category.get("embed_thumbnail"):
            try:
                embed.set_thumbnail(url=category.get("embed_thumbnail"))
            except:
                pass
        
        if category.get("embed_banner"):
            try:
                embed.set_image(url=category.get("embed_banner"))
            except:
                pass
        
        # Envia a mensagem com o painel baseado no tipo configurado
        try:
            button_type = category.get("panel_button_type", "select")
            
            if button_type == "buttons":
                # Usa view com botões individuais
                view = PanelButtonsView(self.category_id)
            else:
                # Usa view com select dropdown (padrão)
                view = PanelView()
            
            msg = await channel.send(embed=embed, view=view)
            
            # Salva a mensagem como ativa para esta categoria
            db_cache["configs"]["active_panel_msg"]["channel_id"] = channel_id
            db_cache["configs"]["active_panel_msg"]["message_id"] = msg.id
            await save_db()
            
            embed_success = discord.Embed(
                title="✅ Painel Enviado",
                description=f"Painel de tickets enviado com sucesso em {channel.mention}!",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed_success, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Sem permissão para enviar mensagens neste canal.",
                ephemeral=True
            )

# ===== SELECTS E DROPDOWNS =====
class ProductSelect(discord.ui.Select):
    def __init__(self):
        products = db_cache["configs"].get("products", {})
        options = []
        
        if not products:
            options.append(discord.SelectOption(label="Nenhum produto cadastrado", value="none"))
        else:
            for pid, pdata in list(products.items())[:25]:  # Discord tem limite de 25 opções
                options.append(discord.SelectOption(
                    label=pdata.get("name", "Sem Nome")[:100],
                    description=pdata.get("desc", "")[:50],
                    value=pid
                ))
        
        super().__init__(placeholder="Selecione um produto para gerenciar...", min_values=1, max_values=1, 
                        options=options, custom_id="product_select_menu")
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message("Nenhum produto cadastrado.", ephemeral=True)
        
        product_id = self.values[0]
        product = db_cache["configs"]["products"].get(product_id)
        
        if not product:
            return await interaction.response.send_message("❌ Produto não encontrado.", ephemeral=True)
        
        embed = discord.Embed(
            title=f"📦 {product['name']}",
            description=product.get("desc", "Sem descrição"),
            color=discord.Color.gold()
        )
        embed.add_field(name="Informações Acumuladas", value=product.get("info", "Nenhuma informação") or "Nenhuma informação", inline=False)
        embed.set_footer(text=f"ID: {product_id}")
        
        await interaction.response.send_message(embed=embed, view=ProductActionView(product_id), ephemeral=True)

class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        panels = db_cache["configs"].get("panels", {})
        options = []
        
        if not panels:
            options.append(discord.SelectOption(label="Nenhuma categoria criada", value="none"))
        else:
            for cid, cdata in list(panels.items())[:25]:
                options.append(discord.SelectOption(
                    label=cdata.get("name", "Sem Nome")[:100],
                    description=cdata.get("desc", "")[:50],
                    emoji=cdata.get("icon", "🎫"),
                    value=cid
                ))
        
        super().__init__(placeholder="Selecione uma categoria para configurar...", min_values=1, max_values=1, 
                        options=options, custom_id="ticket_category_select")
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message("Nenhuma categoria criada.", ephemeral=True)
        
        category_id = self.values[0]
        category = db_cache["configs"]["panels"].get(category_id)
        
        if not category:
            return await interaction.response.send_message("❌ Categoria não encontrada.", ephemeral=True)
        
        embed = discord.Embed(
            title=f"{category['icon']} {category['name']}",
            description=category.get("desc", "Sem descrição"),
            color=discord.Color.blue()
        )
        embed.add_field(name="Horário de Atendimento", value=category.get("working_hours", "24/7"), inline=True)
        embed.add_field(name="Responsáveis", value=f"{len(category.get('responsible_roles', []))} cargo(s)", inline=True)
        embed.add_field(name="Permissão para Abrir", value=f"{len(category.get('allowed_roles', []))} cargo(s)", inline=True)
        embed.add_field(name="Notas", value=category.get("notes", "Nenhuma") or "Nenhuma", inline=False)
        embed.set_footer(text=f"ID: {category_id}")
        
        await interaction.response.send_message(embed=embed, view=CategoryConfigView(category_id), ephemeral=True)

class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = []
        panels = db_cache["configs"]["panels"]
        
        if not panels:
            options.append(discord.SelectOption(label="Nenhum painel configurado", value="none"))
        else:
            for pid, pdata in panels.items():
                options.append(discord.SelectOption(
                    label=pdata.get("name", "Sem Nome"),
                    description=pdata.get("desc", "")[:50],
                    emoji=pdata.get("icon", "🎫"),
                    value=pid
                ))
                
        super().__init__(placeholder="Selecione uma categoria de atendimento...", min_values=1, max_values=1, 
                        options=options, custom_id="ticket_select_menu")

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message("Nenhum painel configurado no momento.", ephemeral=True)
        
        panel_id = self.values[0]
        painel_selecionado = db_cache["configs"]["panels"][panel_id]
        
        # Cria um novo canal para o ticket
        ticket_id = str(uuid.uuid4())[:8]
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"ticket-{ticket_id}",
            category=None,
            reason=f"Ticket criado por {interaction.user.name}"
        )
        
        # Salva informações do ticket
        db_cache["tickets"]["active"][ticket_id] = {
            "channel_id": ticket_channel.id,
            "user_id": interaction.user.id,
            "panel_id": panel_id,
            "created_at": str(discord.utils.utcnow()),
            "status": "open",
            "messages": []
        }
        await save_db()
        
        # Cria embed de boas-vindas no ticket
        embed = discord.Embed(
            title=f"🎫 {painel_selecionado['name']}",
            description=f"Olá {interaction.user.mention}!\n\nDescreva seu problema abaixo. Um membro da equipe em breve irá ajudá-lo.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Ticket ID: {ticket_id}")
        
        await ticket_channel.send(embed=embed, view=TicketActionView(ticket_id))
        await interaction.response.send_message(
            f"✅ Ticket criado com sucesso!\n{ticket_channel.mention}",
            ephemeral=True
        )

# ===== VIEWS (BOTÕES) =====
class BotConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Personalizar Bot", style=discord.ButtonStyle.secondary, emoji="🎨", 
                      custom_id="e6c1edae40364719d2ac157f9d3babff")
    async def btn_personalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BotCustomizeModal())

    @discord.ui.button(label="⚙️ Permissões", style=discord.ButtonStyle.secondary, custom_id="8f801ec8214749e6e854929883d2feb6")
    async def btn_permissoes(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="⚙️ Gerenciamento de Permissões",
            description="Selecione quem pode gerenciar e suportar tickets.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=PermissionsView(), ephemeral=True)

    @discord.ui.button(label="🤖 Configurar IA", style=discord.ButtonStyle.secondary, custom_id="852dbb10c722453fd628c01f48bc181d")
    async def btn_config_ia(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not AI_ENABLED:
            return await interaction.response.send_message(
                "❌ IA não está habilitada. Verifique o arquivo JSON de credenciais.",
                ephemeral=True
            )
        
        embed = discord.Embed(
            title="🤖 Configuração de IA",
            description="Escolha o que deseja configurar:",
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed, view=AIConfigView(), ephemeral=True)

    @discord.ui.button(label="🎫 Configurar Tickets", style=discord.ButtonStyle.primary, custom_id="btn_config_tickets")
    async def btn_config_tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎫 Gestão de Categorias de Tickets",
            description="Criada e configure as categorias de suporte.",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, view=TicketConfigView(), ephemeral=True)

    @discord.ui.button(label="📤 Enviar Msg de Ticket", style=discord.ButtonStyle.success, custom_id="btn_send_ticket_msg")
    async def btn_send_ticket_msg(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(CategorySelectForMessage())
        
        embed = discord.Embed(
            title="📤 Enviar Painel de Tickets",
            description="Escolha a categoria do painel que deseja enviar:",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class AIConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Configurar Prompt", style=discord.ButtonStyle.primary, custom_id="btn_ia_prompt_config")
    async def btn_prompt(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(IAPromptModal())
    
    @discord.ui.button(label="Adicionar Produto", style=discord.ButtonStyle.success, custom_id="btn_ia_add_product")
    async def btn_add_product(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddProductModal())
    
    @discord.ui.button(label="Visualizar Produtos", style=discord.ButtonStyle.secondary, custom_id="btn_ia_view_products")
    async def btn_view_products(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(ProductSelect())
        
        embed = discord.Embed(
            title="📦 Produtos Cadastrados",
            description=f"Total: {len(db_cache['configs']['products'])} produto(s)",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ProductActionView(discord.ui.View):
    def __init__(self, product_id):
        super().__init__(timeout=None)
        self.product_id = product_id
    
    @discord.ui.button(label="Editar Informações", style=discord.ButtonStyle.primary, custom_id="btn_edit_product_info")
    async def btn_edit_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditProductModal(self.product_id))
    
    @discord.ui.button(label="Deletar Produto", style=discord.ButtonStyle.danger, custom_id="btn_delete_product")
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.product_id in db_cache["configs"]["products"]:
            del db_cache["configs"]["products"][self.product_id]
            await save_db()
            await interaction.response.send_message("✅ Produto deletado com sucesso!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Produto não encontrado.", ephemeral=True)

class PermissionsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Adicionar Manager", style=discord.ButtonStyle.green, custom_id="btn_add_manager")
    async def btn_add_manager(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Mencione o cargo que terá acesso de administrador:\n`@manager_role`",
            ephemeral=True
        )
    
    @discord.ui.button(label="Adicionar Suporte", style=discord.ButtonStyle.blurple, custom_id="btn_add_support")
    async def btn_add_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Mencione o cargo que será suporte de tickets:\n`@support_role`",
            ephemeral=True
        )
    
    @discord.ui.button(label="Ver Permissões", style=discord.ButtonStyle.secondary, custom_id="btn_view_perms")
    async def btn_view_permissions(self, interaction: discord.Interaction, button: discord.ui.Button):
        managers = db_cache["configs"]["bot_settings"].get("manager_role", "Não configurado")
        embed = discord.Embed(
            title="📋 Permissões Configuradas",
            color=discord.Color.blue()
        )
        embed.add_field(name="Manager", value=f"<@&{managers}>" if isinstance(managers, int) else managers, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Função auxiliar para gerar transcrição de ticket em formato HTML estilo Discord
async def generate_ticket_transcript(ticket_id: str, channel: discord.TextChannel) -> str:
    """Gera um arquivo HTML com aparência do Discord com todas as mensagens do ticket"""
    try:
        print(f"📝 Iniciando geração de transcrição para ticket {ticket_id}")
        
        # Coleta todas as mensagens do canal
        messages = []
        async for msg in channel.history(limit=None, oldest_first=True):
            messages.append(msg)
        
        print(f"📊 Total de mensagens coletadas: {len(messages)}")
        
        # Cria a pasta de transcripts se não existir
        import os
        transcript_dir = "transcripts"
        if not os.path.exists(transcript_dir):
            os.makedirs(transcript_dir)
            print(f"📁 Pasta 'transcripts' criada")
        
        # Inicia o HTML com CSS do Discord
        html_content = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcrição do Ticket</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            background-color: #36393f;
            color: #dcddde;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            font-size: 14px;
            line-height: 1.4;
            overflow-x: hidden;
        }
        
        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            background-color: #2c2f33;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 4px;
            border-left: 4px solid #7289da;
        }
        
        .header h1 {
            color: #ffffff;
            font-size: 24px;
            margin-bottom: 10px;
        }
        
        .header-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            font-size: 13px;
            color: #99aab5;
        }
        
        .header-info-item {
            display: flex;
            flex-direction: column;
        }
        
        .header-info-label {
            color: #72767d;
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .messages-container {
            background-color: #2c2f33;
            border-radius: 4px;
            padding: 15px 0;
            margin-bottom: 20px;
        }
        
        .message-group {
            padding: 0 15px;
            margin-bottom: 8px;
            display: flex;
            gap: 12px;
        }
        
        .message-avatar {
            flex-shrink: 0;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background-color: #7289da;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            color: white;
            font-size: 16px;
        }
        
        .message-content {
            flex-grow: 1;
        }
        
        .message-header {
            display: flex;
            align-items: baseline;
            gap: 8px;
            margin-bottom: 4px;
        }
        
        .message-author {
            color: #ffffff;
            font-weight: 600;
            word-break: break-word;
        }
        
        .message-timestamp {
            color: #72767d;
            font-size: 12px;
            margin-left: 8px;
        }
        
        .message-text {
            color: #dcddde;
            word-wrap: break-word;
            white-space: pre-wrap;
            margin-bottom: 8px;
        }
        
        .message-attachment {
            background-color: #292b2f;
            border: 1px solid #202225;
            border-radius: 4px;
            padding: 8px 12px;
            margin: 8px 0;
            display: inline-block;
            color: #99aab5;
            font-size: 12px;
        }
        
        .message-embed {
            background-color: #2c2f33;
            border-left: 4px solid #7289da;
            border-radius: 4px;
            padding: 12px;
            margin: 8px 0;
            max-width: 500px;
        }
        
        .embed-title {
            color: #ffffff;
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .embed-description {
            color: #dcddde;
            font-size: 13px;
            margin-bottom: 8px;
        }
        
        .embed-field {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-top: 8px;
        }
        
        .embed-field-item {
            display: flex;
            flex-direction: column;
        }
        
        .embed-field-name {
            color: #ffffff;
            font-weight: 600;
            font-size: 12px;
            margin-bottom: 4px;
        }
        
        .embed-field-value {
            color: #dcddde;
            font-size: 13px;
        }
        
        .footer {
            background-color: #2c2f33;
            padding: 15px;
            margin-top: 20px;
            border-radius: 4px;
            text-align: center;
            color: #72767d;
            font-size: 12px;
        }
        
        .system-message {
            color: #72767d;
            font-style: italic;
            padding: 0 15px;
            margin: 12px 0;
            text-align: center;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎫 Transcrição do Ticket</h1>
            <div class="header-info">
                <div class="header-info-item">
                    <span class="header-info-label">ID do Ticket</span>
                    <span>#""" + ticket_id + """</span>
                </div>
                <div class="header-info-item">
                    <span class="header-info-label">Canal</span>
                    <span>#""" + channel.name + """</span>
                </div>
                <div class="header-info-item">
                    <span class="header-info-label">Data de Geração</span>
                    <span>""" + discord.utils.utcnow().strftime('%d/%m/%Y %H:%M:%S') + """</span>
                </div>
                <div class="header-info-item">
                    <span class="header-info-label">Total de Mensagens</span>
                    <span>""" + str(len(messages)) + """</span>
                </div>
            </div>
        </div>
        
        <div class="messages-container">
"""
        
        # Formata cada mensagem
        last_author = None
        for msg in messages:
            # Pula mensagens de bot de sistema (opcional)
            if msg.author.bot and msg.author.name == "clyde":
                continue
            
            # Formata timestamp
            timestamp = msg.created_at.strftime('%d/%m/%Y %H:%M:%S')
            author_name = msg.author.name if msg.author else "Usuário Deletado"
            
            # Avatar (primeira letra do nome em maiúscula)
            avatar_initial = author_name[0].upper() if author_name else "?"
            
            # Cor do avatar baseada no hash do nome
            colors = ["#7289da", "#43b581", "#faa61a", "#f04747", "#f47fff", "#00b0f4", "#593695"]
            color_index = sum(ord(c) for c in author_name) % len(colors)
            avatar_color = colors[color_index]
            
            html_content += f"""            <div class="message-group" style="{f'opacity: 0.8;' if msg.author.bot else ''}">
                <div class="message-avatar" style="background-color: {avatar_color};">{avatar_initial}</div>
                <div class="message-content">
                    <div class="message-header">
                        <span class="message-author">{author_name}</span>
                        <span class="message-timestamp">{timestamp}</span>
"""
            
            # Tag de bot
            if msg.author.bot:
                html_content += '                        <span style="background-color: #7289da; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600;">BOT</span>\n'
            
            html_content += "                    </div>\n"
            
            # Conteúdo da mensagem
            if msg.content:
                # Escapa caracteres HTML
                msg_text = msg.content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_content += f'                    <div class="message-text">{msg_text}</div>\n'
            
            # Attachments
            if msg.attachments:
                for attachment in msg.attachments:
                    size_kb = attachment.size / 1024
                    size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
                    html_content += f'                    <div class="message-attachment">📎 {attachment.filename} ({size_str})</div>\n'
            
            # Embeds
            if msg.embeds:
                for embed in msg.embeds:
                    html_content += '                    <div class="message-embed">\n'
                    
                    if embed.title:
                        html_content += f'                        <div class="embed-title">{embed.title}</div>\n'
                    
                    if embed.description:
                        desc = embed.description.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        html_content += f'                        <div class="embed-description">{desc}</div>\n'
                    
                    if embed.fields:
                        html_content += '                        <div class="embed-field">\n'
                        for field in embed.fields:
                            field_name = field.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                            field_value = field.value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                            html_content += f'                            <div class="embed-field-item">\n'
                            html_content += f'                                <span class="embed-field-name">{field_name}</span>\n'
                            html_content += f'                                <span class="embed-field-value">{field_value}</span>\n'
                            html_content += f'                            </div>\n'
                        html_content += '                        </div>\n'
                    
                    html_content += '                    </div>\n'
            
            html_content += "                </div>\n            </div>\n"
        
        # Fecha HTML
        html_content += """        </div>
        
        <div class="footer">
            <p>💾 Transcrição gerada automaticamente | 🔒 Arquivo protegido e arquivado</p>
        </div>
    </div>
</body>
</html>
"""
        
        # Salva o arquivo HTML
        filename = f"{transcript_dir}/ticket_{ticket_id}_{discord.utils.utcnow().strftime('%Y%m%d_%H%M%S')}.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        file_size = os.path.getsize(filename)
        print(f"💾 Transcrição HTML salva em: {filename} ({file_size} bytes)")
        
        return filename
    except Exception as e:
        print(f"❌ Erro ao gerar transcrição: {e}")
        import traceback
        traceback.print_exc()
        return None

# Função para fazer upload de transcrição para GitHub
async def upload_transcript_to_github(ticket_id: str, local_file_path: str) -> str:
    """Faz upload do arquivo de transcrição para o repositório GitHub e retorna a URL"""
    if not GITHUB_ENABLED:
        print("⚠️ GitHub não está configurado")
        return None
    
    try:
        print(f"📤 Iniciando upload de transcrição para GitHub...")
        
        # Lê o arquivo
        with open(local_file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        # Prepara os dados para a API do GitHub
        filename = os.path.basename(local_file_path)
        api_url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/transcripts/{filename}"
        
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
        
        # Codifica o conteúdo em base64 (requerido pela API do GitHub)
        encoded_content = base64.b64encode(file_content.encode('utf-8')).decode('utf-8')
        
        # Tenta criar a branch "transcripts" se não existir (usando a branch padrão como base)
        print(f"🔀 Verificando/Criando branch '{GITHUB_TRANSCRIPTS_BRANCH}'...")
        try:
            # Obtém informações da branch padrão
            repo_url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"
            repo_response = requests.get(repo_url, headers=headers, timeout=5)
            
            if repo_response.status_code == 200:
                repo_data = repo_response.json()
                default_branch = repo_data.get("default_branch", "main")
                
                # Tenta obter a SHA da branch padrão
                branch_url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/refs/heads/{default_branch}"
                branch_response = requests.get(branch_url, headers=headers, timeout=5)
                
                if branch_response.status_code == 200:
                    default_branch_sha = branch_response.json()["object"]["sha"]
                    
                    # Tenta criar a branch de transcripts a partir da default
                    create_branch_data = {
                        "ref": f"refs/heads/{GITHUB_TRANSCRIPTS_BRANCH}",
                        "sha": default_branch_sha
                    }
                    
                    create_branch_url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/git/refs"
                    requests.post(create_branch_url, json=create_branch_data, headers=headers, timeout=5)
                    # Ignora erro se a branch já existe
        except:
            pass  # Continua mesmo se não conseguir criar a branch
        
        # Dados do commit
        data = {
            "message": f"📝 Transcrição do Ticket #{ticket_id}",
            "content": encoded_content,
            "branch": GITHUB_TRANSCRIPTS_BRANCH
        }
        
        # Faz a requisição
        response = requests.put(api_url, json=data, headers=headers, timeout=15)
        
        if response.status_code in [201, 200]:
            result = response.json()
            
            # URL do arquivo via GitHub Pages (recomendado - mais bonita e confiável)
            # Para usar essa URL, você precisa ativar GitHub Pages em Settings > Pages > Source: Deploy from a branch > /transcripts
            github_pages_url = f"https://{GITHUB_REPO_OWNER}.github.io/{GITHUB_REPO_NAME}/transcripts/{filename}"
            
            # URL alternativa (raw.githubusercontent.com) - funciona se repo for público
            raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/{GITHUB_TRANSCRIPTS_BRANCH}/transcripts/{filename}"
            
            # URL do arquivo no GitHub (para ver/editar no site)
            github_web_url = f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/blob/{GITHUB_TRANSCRIPTS_BRANCH}/transcripts/{filename}"
            
            print(f"✅ Transcrição enviada para GitHub com sucesso!")
            print(f"🔗 URL GitHub Pages (recomendada): {github_pages_url}")
            print(f"🔗 URL Raw (alternativa): {raw_url}")
            print(f"📄 Ver no GitHub: {github_web_url}")
            
            # Retorna a URL do GitHub Pages (mais bonita e confiável)
            return github_pages_url
        else:
            error_msg = response.text
            print(f"❌ Erro no upload para GitHub: {response.status_code}")
            print(f"Resposta: {error_msg}")
            
            # Dicas de troubleshooting
            if response.status_code == 403:
                print("\n⚠️ ERRO 403 - Permissão negada. Verifique:")
                print("  1. O token foi criado com permissão 'repo' (full control)?")
                print("  2. O repositório existe e é acessível?")
                print("  3. O GitHub_REPO_OWNER e GITHUB_REPO_NAME estão corretos?")
                print("  📖 Documentação: https://docs.github.com/pt/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token")
            elif response.status_code == 404:
                print("\n⚠️ ERRO 404 - Repositório não encontrado!")
                print(f"  Verifique: {GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}")
            
            return None
            
    except Exception as e:
        print(f"❌ Erro ao fazer upload para GitHub: {e}")
        import traceback
        traceback.print_exc()
        return None
        return None

class TicketActionView(discord.ui.View):
    def __init__(self, ticket_id):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
    
    @discord.ui.button(label="Fechar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_close_ticket")
    async def btn_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.ticket_id not in db_cache["tickets"]["active"]:
            return await interaction.response.send_message("❌ Ticket não encontrado.", ephemeral=True)
        
        # RESPONDE IMEDIATAMENTE à interação
        await interaction.response.send_message("✅ Ticket fechado com sucesso! Processando...  ", ephemeral=True)
        
        # Executa o resto em background para não timeout
        asyncio.create_task(self._close_ticket_background(interaction))
    
    async def _close_ticket_background(self, interaction: discord.Interaction):
        """Processa o fechamento do ticket em background"""
        try:
            ticket = db_cache["tickets"]["active"][self.ticket_id]
            ticket["status"] = "closed"
            ticket["closed_by"] = interaction.user.id
            ticket["closed_at"] = str(discord.utils.utcnow())
            
            # Move para histórico
            db_cache["tickets"]["closed"][self.ticket_id] = db_cache["tickets"]["active"].pop(self.ticket_id)
            await save_db()
            
            # Gera a transcrição ANTES de deletar o canal
            ticket_channel = bot.get_channel(ticket["channel_id"])
            transcript_file = None
            if ticket_channel:
                print(f"🎫 Gerando transcrição para ticket {self.ticket_id} no canal {ticket_channel.name}")
                transcript_file = await generate_ticket_transcript(self.ticket_id, ticket_channel)
                if transcript_file:
                    print(f"✅ Transcrição gerada com sucesso: {transcript_file}")
                else:
                    print(f"❌ Falha ao gerar transcrição")
            
            # Busca o canal de logs
            log_channel = bot.get_channel(1431123587254849718)
            
            if log_channel:
                # Busca informações do ticket
                user = await bot.fetch_user(ticket["user_id"])
                category = db_cache["configs"]["panels"].get(ticket["panel_id"], {})
                
                # Calcula duração do ticket
                created_time = discord.utils.parse_time(ticket["created_at"])
                if created_time:
                    duration = discord.utils.utcnow() - created_time
                    duration_str = f"{duration.days}d {duration.seconds//3600}h {(duration.seconds//60)%60}m"
                else:
                    duration_str = "Desconhecida"
                
                # Cria embed de log
                embed_log = discord.Embed(
                    title="🎫 Ticket Fechado",
                    description=f"Um ticket foi fechado com sucesso!",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow()
                )
                embed_log.add_field(name="ID do Ticket", value=f"`{self.ticket_id}`", inline=True)
                embed_log.add_field(name="Usuário", value=f"{user.mention}", inline=True)
                embed_log.add_field(name="Categoria", value=category.get("name", "Desconhecida"), inline=True)
                embed_log.add_field(name="Fechado por", value=f"{interaction.user.mention}", inline=True)
                embed_log.add_field(name="Duração", value=duration_str, inline=True)
                embed_log.add_field(name="Canal", value=f"{ticket_channel.mention if ticket_channel else 'Deletado'}", inline=True)
                embed_log.set_thumbnail(url=user.avatar.url if user.avatar else "")
                
                # Faz upload para GitHub se habilitado
                if transcript_file and GITHUB_ENABLED:
                    print(f"📤 Fazendo upload para GitHub...")
                    github_url = await upload_transcript_to_github(self.ticket_id, transcript_file)
                    if github_url:
                        embed_log.add_field(name="📱 Transcrição Online", value=f"[Visualizar no GitHub]({github_url})", inline=False)
                        print(f"✅ Upload para GitHub concluído: {github_url}")
                    else:
                        print(f"❌ Falha ao fazer upload para GitHub")
                    
                    # Se GitHub está habilitado, envia APENAS o link (sem arquivo)
                    try:
                        await log_channel.send(embed=embed_log)
                        print(f"✅ Log enviado com link GitHub")
                    except Exception as e:
                        print(f"⚠️ Erro ao enviar log: {e}")
                else:
                    # Se GitHub não está habilitado, envia o arquivo de transcrição
                    try:
                        if transcript_file:
                            print(f"📄 Enviando transcrição HTML (GitHub desabilitado): {transcript_file}")
                            # Extrai o nome do arquivo para ter um nome mais bonito
                            display_filename = os.path.basename(transcript_file)
                            await log_channel.send(embed=embed_log, file=discord.File(transcript_file, filename=display_filename))
                            print(f"✅ Transcrição enviada com sucesso")
                        else:
                            print(f"⚠️ Nenhum arquivo de transcrição foi gerado")
                            await log_channel.send(embed=embed_log)
                    except Exception as e:
                        print(f"❌ Erro ao enviar arquivo de transcrição: {e}")
                        try:
                            await log_channel.send(embed=embed_log)
                        except:
                            pass
            
            # Deleta o canal após 3 segundos
            await asyncio.sleep(3)
            if ticket_channel:
                try:
                    await ticket_channel.delete(reason="Ticket fechado")
                    print(f"✅ Canal do ticket {self.ticket_id} deletado")
                except Exception as e:
                    print(f"⚠️ Erro ao deletar canal: {e}")
        
        except Exception as e:
            print(f"❌ Erro ao processar fechamento do ticket: {e}")
            import traceback
            traceback.print_exc()

class TicketConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="➕ Criar Categoria", style=discord.ButtonStyle.success, custom_id="btn_create_category")
    async def btn_create_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CreateTicketCategoryModal())
    
    @discord.ui.button(label="⚙️ Configurar Categoria", style=discord.ButtonStyle.primary, custom_id="btn_configure_category")
    async def btn_configure_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(TicketCategorySelect())
        
        embed = discord.Embed(
            title="⚙️ Configurar Categoria",
            description="Selecione a categoria que deseja configurar:",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class CategoryConfigView(discord.ui.View):
    def __init__(self, category_id):
        super().__init__(timeout=None)
        self.category_id = category_id
    
    @discord.ui.button(label="📝 Editar Configurações", style=discord.ButtonStyle.primary, custom_id="btn_edit_category")
    async def btn_edit_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ConfigTicketCategoryModal(self.category_id))

    @discord.ui.button(label="🎨 Configurar Embed", style=discord.ButtonStyle.primary, custom_id="btn_config_embed")
    async def btn_config_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎨 Editar Elementos do Embed",
            description="Escolha qual elemento deseja editar:",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=EmbedConfigView(self.category_id), ephemeral=True)
    
    @discord.ui.button(label="👷 Adicionar Responsável", style=discord.ButtonStyle.blurple, custom_id="btn_add_responsible")
    async def btn_add_responsible(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="👷 Adicionar Responsável",
            description="Mencione o cargo que será responsável por responder tickets nesta categoria:\n```\n@cargo_aqui\n```",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🔓 Permissão para Abrir", style=discord.ButtonStyle.blurple, custom_id="btn_add_permission")
    async def btn_add_permission(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🔓 Quem Pode Abrir Tickets?",
            description="Mencione o cargo que será permitido abrir tickets nesta categoria:\n```\n@cargo_aqui\n```",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🗑️ Deletar Categoria", style=discord.ButtonStyle.danger, custom_id="btn_delete_category")
    async def btn_delete_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.category_id in db_cache["configs"]["panels"]:
            category_name = db_cache["configs"]["panels"][self.category_id].get("name", "Desconhecida")
            del db_cache["configs"]["panels"][self.category_id]
            await save_db()
            embed = discord.Embed(
                title="🗑️ Categoria Deletada",
                description=f"Categoria **{category_name}** foi removida com sucesso!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Categoria não encontrada.", ephemeral=True)

class EmbedConfigView(discord.ui.View):
    def __init__(self, category_id):
        super().__init__(timeout=None)
        self.category_id = category_id
    
    @discord.ui.button(label="📌 Título", style=discord.ButtonStyle.secondary, custom_id="btn_embed_title")
    async def btn_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedTitleModal(self.category_id))
    
    @discord.ui.button(label="📄 Descrição", style=discord.ButtonStyle.secondary, custom_id="btn_embed_desc")
    async def btn_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedDescriptionModal(self.category_id))
    
    @discord.ui.button(label="👤 Autor", style=discord.ButtonStyle.secondary, custom_id="btn_embed_author")
    async def btn_author(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedAuthorModal(self.category_id))
    
    @discord.ui.button(label="📍 Rodapé", style=discord.ButtonStyle.secondary, custom_id="btn_embed_footer")
    async def btn_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedFooterModal(self.category_id))
    
    @discord.ui.button(label="🎨 Cor", style=discord.ButtonStyle.secondary, custom_id="btn_embed_color")
    async def btn_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedColorModal(self.category_id))
    
    @discord.ui.button(label="🖼️ Banner", style=discord.ButtonStyle.secondary, custom_id="btn_embed_banner")
    async def btn_banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedBannerModal(self.category_id))
    
    @discord.ui.button(label="🖻 Miniatura", style=discord.ButtonStyle.secondary, custom_id="btn_embed_thumbnail")
    async def btn_thumbnail(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedThumbnailModal(self.category_id))
    
    @discord.ui.button(label="🔘 Tipo de Painel", style=discord.ButtonStyle.blurple, custom_id="btn_panel_type")
    async def btn_panel_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(PanelButtonTypeSelect(self.category_id))
        
        embed = discord.Embed(
            title="🔘 Escolher Tipo de Painel",
            description="Como deseja exibir as opções de abertura de tickets?",
            color=discord.Color.blue()
        )
        embed.add_field(name="📋 Select", value="Dropdown com lista para seleção", inline=False)
        embed.add_field(name="🔘 Buttons", value="Botões individuais em grid", inline=False)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

class PanelButtonsView(discord.ui.View):
    """View com botões individuais para abrir tickets (alternativa ao Select)"""
    def __init__(self, category_id=None):
        super().__init__(timeout=None)
        self.category_id = category_id
        
        # Adiciona botões para cada categoria
        panels = db_cache["configs"].get("panels", {})
        
        if not panels:
            return
        
        # Cria um botão para cada categoria (filtra para evitar overflow)
        for panel_id, panel_data in list(panels.items())[:5]:  # Máx 5 botões por linha
            emoji = panel_data.get("icon", "🎫")
            label = panel_data.get("name", "Sem Nome")[:50]
            
            # Cria um botão com callback específico para este painel
            button = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.blurple,
                custom_id=f"panel_btn_{panel_id[:6]}"  # Limita o tamanho
            )
            
            # Annexa o callback usando closure
            async def button_callback(interaction: discord.Interaction, pan_id=panel_id):
                await self.create_ticket_from_button(interaction, pan_id)
            
            button.callback = button_callback
            self.add_item(button)
    
    async def create_ticket_from_button(self, interaction: discord.Interaction, panel_id: str):
        """Cria um ticket quando um botão é clicado"""
        try:
            if panel_id not in db_cache["configs"]["panels"]:
                return await interaction.response.send_message("❌ Categoria não encontrada.", ephemeral=True)
            
            painel_selecionado = db_cache["configs"]["panels"][panel_id]
            ticket_id = str(uuid.uuid4())[:8]
            
            # Cria um novo canal para o ticket
            category_check = interaction.guild.categories
            ticket_category = discord.utils.find(lambda c: c.name.lower() == "tickets", category_check) or interaction.guild
            
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            ticket_channel = await interaction.guild.create_text_channel(
                name=f"ticket-{ticket_id}",
                category=ticket_category if isinstance(ticket_category, discord.CategoryChannel) else None,
                overwrites=overwrites,
                topic=f"Ticket #{ticket_id} | Usuário: {interaction.user.name}"
            )
            
            # Salva no banco de dados
            db_cache["tickets"]["active"][ticket_id] = {
                "user_id": interaction.user.id,
                "channel_id": ticket_channel.id,
                "panel_id": panel_id,
                "status": "open",
                "created_at": str(discord.utils.utcnow()),
                "closed_by": None,
                "closed_at": None
            }
            await save_db()
            
            # Envia mensagem no canal do ticket
            embed = discord.Embed(
                title=f"{painel_selecionado['icon']} {painel_selecionado['name']}",
                description=painel_selecionado.get("desc", "Descreva seu problema aqui"),
                color=discord.Color.blue()
            )
            
            await ticket_channel.send(
                embed=embed,
                view=TicketActionView(ticket_id)
            )
            
            await interaction.response.send_message(
                f"✅ Ticket criado com sucesso! {ticket_channel.mention}",
                ephemeral=True
            )
        except Exception as e:
            print(f"❌ Erro ao criar ticket: {e}")
            await interaction.response.send_message(
                f"❌ Erro ao criar ticket: {str(e)[:100]}",
                ephemeral=True
            )

# ==========================================
# CONFIGURAÇÃO DO BOT
# ==========================================
class TicketBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await load_db()
        # Registra views persistentes
        self.add_view(BotConfigView())
        self.add_view(PanelView())
        self.add_view(PanelButtonsView())
        self.add_view(AIConfigView())
        self.add_view(PermissionsView())
        self.add_view(ProductActionView("dummy"))
        self.add_view(TicketConfigView())
        self.add_view(CategoryConfigView("dummy"))
        self.add_view(EmbedConfigView("dummy"))
        
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

bot = TicketBot()

# Função auxiliar para atualizar o Embed ativo em tempo real
async def update_active_panel():
    active_msg_data = db_cache["configs"]["active_panel_msg"]
    if active_msg_data["channel_id"] and active_msg_data["message_id"]:
        try:
            channel = bot.get_channel(active_msg_data["channel_id"])
            if channel:
                msg = await channel.fetch_message(active_msg_data["message_id"])
                
                # Monta o embed padrão escuro/profissional
                embed = discord.Embed(
                    title="Central de Atendimento",
                    description="Selecione a categoria abaixo para abrir um ticket.",
                    color=discord.Color.dark_theme() # Estética Dark Mode
                )
                await msg.edit(embed=embed, view=PanelView())
        except Exception as e:
            print(f"Erro ao atualizar painel ativo: {e}")

# ==========================================
# COMANDOS SLASH (APP COMMANDS)
# ==========================================

@bot.tree.command(name="botconfig", description="Configurações principais do bot de tickets.")
@app_commands.describe(ticket_channel="Canal onde os tickets serão criados", manager_role="Cargo que pode gerenciar tickets")
async def botconfig(interaction: discord.Interaction, ticket_channel: discord.TextChannel = None, manager_role: discord.Role = None):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Você precisa ser administrador!", ephemeral=True)
    
    if ticket_channel:
        db_cache["configs"]["bot_settings"]["ticket_channel"] = ticket_channel.id
    if manager_role:
        db_cache["configs"]["bot_settings"]["manager_role"] = manager_role.id
        
    await save_db()
    
    embed = discord.Embed(
        title="⚙️ Configurações do Bot",
        description="Utilize os botões abaixo para configurar módulos avançados.",
        color=discord.Color.blurple()
    )
    embed.add_field(name="Canal de Tickets", value=f"{ticket_channel.mention}" if ticket_channel else "Não configurado", inline=False)
    embed.add_field(name="Cargo Manager", value=f"{manager_role.mention}" if manager_role else "Não configurado", inline=False)
    
    await interaction.response.send_message(embed=embed, view=BotConfigView(), ephemeral=True)

@bot.tree.command(name="criar_painel_ticket", description="Cria uma nova categoria de ticket e gera um ID.")
@app_commands.describe(nome="Nome de identificação do painel (Ex: Suporte Clientes)")
async def criar_painel_ticket(interaction: discord.Interaction, nome: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Você precisa ser administrador!", ephemeral=True)
    
    panel_id = str(uuid.uuid4())[:8]
    
    db_cache["configs"]["panels"][panel_id] = {
        "name": nome,
        "desc": "Descrição padrão",
        "icon": "🎫",
        "embed_title": f"Atendimento: {nome}",
        "embed_desc": "Descreva seu problema."
    }
    await save_db()
    await update_active_panel()
    
    embed = discord.Embed(
        title="✅ Painel Criado",
        description=f"Painel **{nome}** criado com sucesso!",
        color=discord.Color.green()
    )
    embed.add_field(name="ID do Painel", value=f"`{panel_id}`", inline=False)
    embed.add_field(name="Próximo Passo", value=f"Use `/painelconfig {panel_id}` para customizar.", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="painelconfig", description="Customiza as informações de um painel específico.")
@app_commands.describe(panel_id="O ID do painel", nome="Novo nome", desc="Nova descrição", icon="Emoji de ícone")
async def painelconfig(interaction: discord.Interaction, panel_id: str, nome: str = None, desc: str = None, icon: str = None):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Você precisa ser administrador!", ephemeral=True)
    
    if panel_id not in db_cache["configs"]["panels"]:
        return await interaction.response.send_message("❌ ID de painel não encontrado.", ephemeral=True)
        
    panel = db_cache["configs"]["panels"][panel_id]
    if nome: panel["name"] = nome
    if desc: panel["desc"] = desc
    if icon: panel["icon"] = icon
    
    await save_db()
    await update_active_panel()
    
    embed = discord.Embed(
        title="✅ Painel Atualizado",
        description=f"Painel `{panel_id}` foi sincronizado!",
        color=discord.Color.green()
    )
    embed.add_field(name="Nome", value=panel.get("name", "N/A"), inline=True)
    embed.add_field(name="Ícone", value=panel.get("icon", "N/A"), inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="set_painel_config", description="Envia o painel de criação de tickets para o canal.")
async def set_painel_config(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Você precisa ser administrador!", ephemeral=True)
    
    embed = discord.Embed(
        title="🎫 Central de Atendimento",
        description="Selecione a categoria abaixo para abrir um ticket de suporte.",
        color=discord.Color.dark_theme()
    )
    embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else "")
    
    await interaction.response.send_message("Enviando painel...", ephemeral=True)
    msg = await interaction.channel.send(embed=embed, view=PanelView())
    
    db_cache["configs"]["active_panel_msg"]["channel_id"] = interaction.channel.id
    db_cache["configs"]["active_panel_msg"]["message_id"] = msg.id
    await save_db()

@bot.tree.command(name="listar_tickets", description="Lista todos os tickets ativos.")
async def listar_tickets(interaction: discord.Interaction):
    active_tickets = db_cache["tickets"]["active"]
    
    if not active_tickets:
        embed = discord.Embed(
            title="🎫 Tickets Ativos",
            description="Nenhum ticket aberto no momento.",
            color=discord.Color.green()
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    embed = discord.Embed(
        title=f"🎫 Tickets Ativos ({len(active_tickets)})",
        color=discord.Color.blue()
    )
    
    for ticket_id, ticket_info in active_tickets.items():
        user = await bot.fetch_user(ticket_info["user_id"])
        panel_name = db_cache["configs"]["panels"].get(ticket_info["panel_id"], {}).get("name", "Desconhecido")
        embed.add_field(
            name=f"Ticket {ticket_id}",
            value=f"👤 Usuário: {user.mention}\n📁 Categoria: {panel_name}\n🔗 <#{ticket_info['channel_id']}>",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="listar_produtos", description="Lista todos os produtos cadastrados.")
async def listar_produtos(interaction: discord.Interaction):
    products = db_cache["configs"].get("products", {})
    
    if not products:
        embed = discord.Embed(
            title="📦 Produtos",
            description="Nenhum produto cadastrado.",
            color=discord.Color.gold()
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    embed = discord.Embed(
        title=f"📦 Produtos Cadastrados ({len(products)})",
        color=discord.Color.gold()
    )
    
    for product_id, product_data in list(products.items())[:10]:
        embed.add_field(
            name=product_data.get("name", "Sem Nome"),
            value=f"```{product_data.get('desc', 'Sem descrição')[:100]}```",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    # Atualiza a presença do bot
    status = db_cache["configs"]["bot_settings"].get("bot_status", "🎫 Gerenciando Tickets")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.playing,
        name=status
    ))
    
    print(f'✅ Bot {bot.user} conectado com sucesso!')
    print(f'📊 Servidores: {len(bot.guilds)}')
    print(f'🎫 Tickets Ativos: {len(db_cache["tickets"]["active"])}')
    print(f'📦 Produtos Cadastrados: {len(db_cache["configs"]["products"])}')

if __name__ == '__main__':
    bot.run(TOKEN)