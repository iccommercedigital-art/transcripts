<?php
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    header('Content-Type: application/json');
    
    // Lê o JSON enviado pelo fetch()
    $input = json_decode(file_get_contents('php://input'), true);
    
    // SEU TOKEN SEGURO NO BACKEND
    $token = 'caa646733a20adec11ee12f6808a1c9e86c85e381213ee98d78d7dde934b5cc0';
    $apiUrl = 'https://nexusproxy.up.railway.app/CreateKeyAPI.php';
    
    $params = [
        'token' => $token,
        'duration' => $input['duration'] ?? 1,
        'unit' => $input['unit'] ?? 'day'
    ];
    
    $quantity = $input['quantity'] ?? '';
    $customKey = trim($input['customKey'] ?? '');
    
    if (!empty($quantity)) {
        $params['quantity'] = $quantity;
    }
    
    if (!empty($customKey)) {
        if (empty($quantity) || $quantity == '1') {
            $params['key'] = $customKey;
        } else {
            $params['prefix'] = $customKey;
        }
    }
    
    $url = $apiUrl . '?' . http_build_query($params);
    
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    // Desabilitar a verificação de SSL pode ser necessário em localhost, mas não recomendado em prod.
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false); 
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    curl_close($ch);
    
    if ($error) {
        http_response_code(500);
        echo json_encode(['error' => 'Erro de conexão no backend: ' . $error]);
        exit;
    }
    
    http_response_code($httpCode);
    echo $response;
    exit;
}
?>
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gerador de Chaves | NexusProxy</title>
    <meta name="description" content="Gere suas chaves de acesso com facilidade e rapidez.">
    <link rel="stylesheet" href="style.css">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
</head>
<body>
    <div class="background-elements">
        <div class="blob blob-1"></div>
        <div class="blob blob-2"></div>
    </div>
    
    <main class="container">
        <div class="glass-panel">
            <header class="header">
                <div class="logo-container">
                    <div class="logo-icon"></div>
                    <h1>Nexus <span>Keys</span></h1>
                </div>
                <p>Gerador Oficial de Chaves</p>
            </header>

            <form id="keyForm" class="form">
                <div class="form-row">
                    <div class="input-group">
                        <label for="duration">Tempo</label>
                        <input type="number" id="duration" name="duration" min="1" value="1" required placeholder="Ex: 30">
                    </div>
                    
                    <div class="input-group">
                        <label for="unit">Unidade</label>
                        <select id="unit" name="unit" required>
                            <option value="hour">Horas</option>
                            <option value="day" selected>Dias</option>
                            <option value="week">Semanas</option>
                            <option value="month">Meses</option>
                            <option value="year">Anos</option>
                        </select>
                    </div>
                </div>

                <div class="collapsible-section">
                    <button type="button" class="collapsible-toggle" id="toggleAdvanced">
                        Configurações Avançadas
                        <span class="chevron">▼</span>
                    </button>
                    <div class="collapsible-content" id="advancedContent">
                        <div class="form-row">
                            <div class="input-group">
                                <label for="customKey">Personalização (Opcional)</label>
                                <input type="text" id="customKey" name="customKey" placeholder="Nome exato ou Prefixo">
                            </div>
                            
                            <div class="input-group">
                                <label for="quantity">Quantidade (Opcional)</label>
                                <input type="number" id="quantity" name="quantity" min="1" max="100" placeholder="1">
                            </div>
                        </div>
                    </div>
                </div>

                <button type="submit" class="submit-btn" id="submitBtn">
                    <span class="btn-text">Gerar Chave</span>
                    <span class="loader hidden"></span>
                </button>
            </form>

            <div id="resultContainer" class="result-container hidden">
                <h3>Chaves Geradas:</h3>
                <div id="keysList" class="keys-list">
                    <!-- Keys will be injected here -->
                </div>
            </div>
        </div>
    </main>

    <script src="script.js"></script>
</body>
</html>
