# 📊 Publicando as Páginas no GitHub Pages

## 1️⃣ Configurar o repositório (uma única vez)

Se você ainda não tem um repositório Git, crie um:

```bash
cd "c:\Users\ianpi\OneDrive\Área de Trabalho\bot tickets"

# Inicializar repositório (se não existir)
git init

# Adicionar todos os arquivos
git add .

# Fazer o commit inicial
git commit -m "Inicializar projeto com transcrições"
```

## 2️⃣ Conectar ao repositório remoto no GitHub

### Se o repositório remoto ainda não existe:

```bash
# Adicionar o repositório remoto
git remote add origin https://github.com/iccommercedigital-art/transcripts.git

# Fazer push para GitHub
git branch -M main
git push -u origin main
```

### Se o repositório remoto já existe:

```bash
git push origin main
```

## 3️⃣ Ativar GitHub Pages

1. Vá para: https://github.com/iccommercedigital-art/transcripts
2. Clique em **Settings** (Configurações)
3. Vá para **Pages** (no menu esquerdo)
4. Em **Source**, selecione:
   - Branch: `main`
   - Folder: **`/docs`** ⚠️ IMPORTANTE!
5. Clique em **Save**

## 4️⃣ Pronto! Sua página estará disponível em:

```
https://iccommercedigital-art.github.io/transcripts/
```

---

## 🔄 Atualizar transcrições no futuro

Quando tiver novos transcritos:

```bash
# 1. Coloque os novos .txt files na pasta /transcripts/

# 2. Execute o gerador de páginas
python generate_pages.py

# 3. Faça commit e push
git add docs/
git commit -m "Atualizar transcrições - $(date +%d/%m/%Y)"
git push origin main
```

---

## 📁 Estrutura esperada do repositório

```
transcripts/
├── .git/
├── docs/                    ← Pasta com páginas HTML (publicada)
│   ├── index.html          ← Página principal
│   ├── 19c5772a.html       ← Transcrição individual
│   ├── 1fd1d48d.html
│   └── ... (mais transcrições)
├── transcripts/            ← Pasta com arquivos originais
│   ├── ticket_19c5772a_20260316_034040.txt
│   └── ... (mais transcrições)
├── generate_pages.py       ← Script para gerar HTML
└── database.json
```

---

## ✨ Características das Páginas Geradas

✅ Design responsivo (mobile-friendly)
✅ Índice automático com todas as transcrições
✅ Busca visual por tickets
✅ Temas com gradiente moderno
✅ Timestamps de cada mensagem
✅ Suporte a anexos/arquivos
✅ Gerado automaticamente a partir dos transcripts
