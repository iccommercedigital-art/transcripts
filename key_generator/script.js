document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('keyForm');
    const toggleAdvanced = document.getElementById('toggleAdvanced');
    const advancedContent = document.getElementById('advancedContent');
    const submitBtn = document.getElementById('submitBtn');
    const btnText = document.querySelector('.btn-text');
    const loader = document.querySelector('.loader');
    const resultContainer = document.getElementById('resultContainer');
    const keysList = document.getElementById('keysList');

    // Toggle advanced settings
    toggleAdvanced.addEventListener('click', () => {
        toggleAdvanced.classList.toggle('active');
        if (toggleAdvanced.classList.contains('active')) {
            advancedContent.style.maxHeight = advancedContent.scrollHeight + "px";
        } else {
            advancedContent.style.maxHeight = "0";
        }
    });

    // Helper to find all objects with a "key" property in the API response
    function extractKeys(obj) {
        let keys = [];
        if (Array.isArray(obj)) {
            for (let item of obj) {
                keys = keys.concat(extractKeys(item));
            }
        } else if (typeof obj === 'object' && obj !== null) {
            if (typeof obj.key === 'string' && (obj.duration || obj.unit || obj.pass_key)) {
                keys.push(obj);
            } else {
                for (let k in obj) {
                    keys = keys.concat(extractKeys(obj[k]));
                }
            }
        }
        return keys;
    }

    // Handle form submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // UI State: Loading
        btnText.classList.add('hidden');
        loader.classList.remove('hidden');
        submitBtn.disabled = true;
        resultContainer.classList.add('hidden');
        keysList.innerHTML = ''; // Clear previous results

        const duration = document.getElementById('duration').value;
        const unit = document.getElementById('unit').value;
        const quantity = document.getElementById('quantity').value;
        const customKey = document.getElementById('customKey').value.trim();
        
        // Construct payload to send to index.php (backend proxy)
        const payload = {
            duration,
            unit
        };
        
        if (quantity) payload.quantity = quantity;
        if (customKey) payload.customKey = customKey;

        try {
            const response = await fetch('index.php', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            const data = await response.text();
            let parsedData = null;
            
            try {
                parsedData = JSON.parse(data);
            } catch (e) {
                // Ignore parse error, handled below
            }

            if (!response.ok) {
                showError(parsedData ? JSON.stringify(parsedData) : data);
            } else if (parsedData) {
                let foundKeys = [];
                // API has both "data" and "keys", prevent displaying duplicates
                if (Array.isArray(parsedData.keys)) {
                    foundKeys = parsedData.keys;
                } else if (parsedData.data && parsedData.data.key) {
                    foundKeys = [parsedData.data];
                } else {
                    foundKeys = extractKeys(parsedData);
                }
                
                if (foundKeys.length > 0) {
                    foundKeys.forEach(k => renderKeyItem(k));
                } else {
                    // Se não encontrou chaves no formato esperado, exibe o raw
                    showError("Resposta inválida da API: " + data);
                }
            } else {
                 showError(data);
            }
            
        } catch (error) {
            showError('Erro de conexão: ' + error.message);
        } finally {
            // UI State: Reset
            btnText.classList.remove('hidden');
            loader.classList.add('hidden');
            submitBtn.disabled = false;
            resultContainer.classList.remove('hidden');
            
            if (toggleAdvanced.classList.contains('active')) {
                advancedContent.style.maxHeight = advancedContent.scrollHeight + "px";
            }
        }
    });

    function renderKeyItem(keyObj) {
        const item = document.createElement('div');
        item.className = 'key-item';
        
        const durText = keyObj.duration || '';
        const unitText = keyObj.unit || '';
        
        item.innerHTML = `
            <div class="key-info">
                <span class="key-text" title="${keyObj.key}">${keyObj.key}</span>
                <div class="key-meta">
                    <span class="key-status">Gerada</span>
                    <span>${durText} ${unitText}</span>
                </div>
            </div>
            <button class="copy-btn" data-key="${keyObj.key}" title="Copiar chave">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            </button>
        `;
        
        keysList.appendChild(item);
        
        // Add copy event listener
        const copyBtn = item.querySelector('.copy-btn');
        copyBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(keyObj.key).then(() => {
                const originalIcon = copyBtn.innerHTML;
                copyBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
                setTimeout(() => {
                    copyBtn.innerHTML = originalIcon;
                }, 2000);
            });
        });
    }

    function showError(message) {
        const item = document.createElement('div');
        item.className = 'key-item error-item';
        item.innerHTML = `
            <div class="key-info">
                <span class="key-text">${message}</span>
            </div>
        `;
        keysList.appendChild(item);
    }
});
