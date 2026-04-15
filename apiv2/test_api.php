<?php
/**
 * APIv2 Test Panel — Killerbite95
 * Single-file tester for all APIv2 endpoints.
 * Place on the same server as the bot and open in browser.
 */

// ── Handle API proxy request ──
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['_action']) && $_POST['_action'] === 'proxy') {
    header('Content-Type: application/json');

    $base    = rtrim($_POST['base_url'] ?? 'http://127.0.0.1:8742', '/');
    $token   = $_POST['token'] ?? '';
    $method  = strtoupper($_POST['method'] ?? 'GET');
    $path    = $_POST['path'] ?? '/api/v2/health';
    $body    = $_POST['body'] ?? '';

    $url = $base . $path;

    $headers = ['Accept: application/json'];
    if ($token !== '') {
        $headers[] = 'Authorization: Bearer ' . $token;
    }

    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL            => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_CUSTOMREQUEST  => $method,
        CURLOPT_HTTPHEADER     => $headers,
    ]);

    if (in_array($method, ['POST', 'PATCH', 'PUT']) && $body !== '') {
        curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
        $headers[] = 'Content-Type: application/json';
        curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    }

    $response   = curl_exec($ch);
    $httpCode   = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlError  = curl_error($ch);
    $totalTime  = round(curl_getinfo($ch, CURLINFO_TOTAL_TIME) * 1000);
    curl_close($ch);

    if ($curlError) {
        echo json_encode(['_error' => $curlError, '_http' => 0, '_ms' => $totalTime]);
    } else {
        // Try to pretty-print JSON, fallback to raw
        $decoded = json_decode($response, true);
        echo json_encode([
            '_http' => $httpCode,
            '_ms'   => $totalTime,
            '_url'  => $method . ' ' . $url,
            '_body' => $decoded ?? $response,
        ], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
    }
    exit;
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>APIv2 Test Panel</title>
<style>
    :root { --bg: #0d1117; --surface: #161b22; --border: #30363d; --text: #e6edf3;
            --muted: #8b949e; --accent: #58a6ff; --green: #3fb950; --red: #f85149;
            --yellow: #d29922; --purple: #bc8cff; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text);
           padding: 20px; max-width: 1200px; margin: 0 auto; }
    h1 { font-size: 1.4em; margin-bottom: 4px; }
    .subtitle { color: var(--muted); font-size: 0.85em; margin-bottom: 20px; }

    /* Config bar */
    .config { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
    .config label { font-size: 0.8em; color: var(--muted); display: block; margin-bottom: 3px; }
    .config input { background: var(--surface); border: 1px solid var(--border); color: var(--text);
                    padding: 8px 12px; border-radius: 6px; font-size: 0.9em; }
    #inp_base { width: 280px; }
    #inp_token { width: 380px; font-family: monospace; }
    #inp_guild, #inp_user, #inp_role { width: 180px; font-family: monospace; }

    /* Sections */
    .section { margin-bottom: 16px; }
    .section-title { font-size: 0.75em; text-transform: uppercase; letter-spacing: 1px;
                     color: var(--muted); margin-bottom: 8px; padding-left: 4px; }
    .endpoints { display: flex; flex-wrap: wrap; gap: 6px; }

    /* Buttons */
    .btn { padding: 7px 14px; border: 1px solid var(--border); border-radius: 6px;
           background: var(--surface); color: var(--text); cursor: pointer; font-size: 0.82em;
           display: inline-flex; align-items: center; gap: 6px; transition: all 0.15s; }
    .btn:hover { border-color: var(--accent); background: #1c2333; }
    .btn .method { font-weight: 700; font-size: 0.75em; padding: 2px 5px; border-radius: 3px;
                   font-family: monospace; }
    .m-GET    { background: #0d419d; color: #79b8ff; }
    .m-POST   { background: #1b4721; color: #56d364; }
    .m-PATCH  { background: #4a3000; color: #e3b341; }
    .m-PUT    { background: #362065; color: #bc8cff; }
    .m-DELETE { background: #5c1a1a; color: #ff7b72; }

    /* Custom request */
    .custom { background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
              padding: 14px; margin-bottom: 16px; }
    .custom-row { display: flex; gap: 8px; align-items: end; flex-wrap: wrap; }
    .custom select, .custom input[type=text] { background: var(--bg); border: 1px solid var(--border);
        color: var(--text); padding: 8px 10px; border-radius: 6px; font-size: 0.85em; }
    .custom select { width: 100px; }
    #inp_path { flex: 1; min-width: 300px; font-family: monospace; }
    .custom textarea { width: 100%; margin-top: 8px; background: var(--bg); border: 1px solid var(--border);
        color: var(--text); padding: 8px 10px; border-radius: 6px; font-size: 0.85em; font-family: monospace;
        resize: vertical; min-height: 40px; }
    .btn-send { background: var(--accent); color: #fff; border: none; font-weight: 600; padding: 8px 20px; }
    .btn-send:hover { background: #79b8ff; }

    /* Response */
    .response { background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
                padding: 16px; margin-top: 16px; }
    .resp-header { display: flex; gap: 12px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
    .resp-status { font-weight: 700; font-size: 1.1em; }
    .resp-status.s2xx { color: var(--green); }
    .resp-status.s4xx { color: var(--yellow); }
    .resp-status.s5xx { color: var(--red); }
    .resp-meta { font-size: 0.8em; color: var(--muted); }
    .resp-url { font-family: monospace; font-size: 0.8em; color: var(--accent); }
    pre { background: var(--bg); padding: 12px; border-radius: 6px; overflow-x: auto;
          font-size: 0.85em; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
    .loading { color: var(--muted); font-style: italic; }
</style>
</head>
<body>

<h1>🔌 APIv2 Test Panel</h1>
<p class="subtitle">Red-DiscordBot REST API tester — by Killerbite95</p>

<!-- Config -->
<div class="config">
    <div>
        <label>Base URL</label>
        <input id="inp_base" type="text" value="http://127.0.0.1:8742" placeholder="http://127.0.0.1:8742">
    </div>
    <div>
        <label>API Token</label>
        <input id="inp_token" type="password" placeholder="Bearer token...">
    </div>
    <div>
        <label>Guild ID</label>
        <input id="inp_guild" type="text" placeholder="123456789">
    </div>
    <div>
        <label>User ID</label>
        <input id="inp_user" type="text" placeholder="987654321">
    </div>
    <div>
        <label>Role ID</label>
        <input id="inp_role" type="text" placeholder="111222333">
    </div>
</div>

<!-- Endpoints: System -->
<div class="section">
    <div class="section-title">Sistema</div>
    <div class="endpoints">
        <button class="btn" onclick="fire('GET','/api/v2/health')">
            <span class="method m-GET">GET</span> /health</button>
        <button class="btn" onclick="fire('GET','/api/v2/info')">
            <span class="method m-GET">GET</span> /info</button>
    </div>
</div>

<!-- Endpoints: Guilds -->
<div class="section">
    <div class="section-title">Guilds</div>
    <div class="endpoints">
        <button class="btn" onclick="fire('GET','/api/v2/guilds')">
            <span class="method m-GET">GET</span> /guilds</button>
        <button class="btn" onclick="fire('GET','/api/v2/guilds/'+g())">
            <span class="method m-GET">GET</span> /guilds/{id}</button>
    </div>
</div>

<!-- Endpoints: Members -->
<div class="section">
    <div class="section-title">Members</div>
    <div class="endpoints">
        <button class="btn" onclick="fire('GET','/api/v2/guilds/'+g()+'/members?limit=10')">
            <span class="method m-GET">GET</span> /members (list)</button>
        <button class="btn" onclick="fire('GET','/api/v2/guilds/'+g()+'/members/'+u())">
            <span class="method m-GET">GET</span> /members/{uid}</button>
        <button class="btn" onclick="fire('PATCH','/api/v2/guilds/'+g()+'/members/'+u(), JSON.stringify({nickname:'TestNick'}))">
            <span class="method m-PATCH">PATCH</span> nickname → "TestNick"</button>
    </div>
</div>

<!-- Endpoints: Roles -->
<div class="section">
    <div class="section-title">Roles</div>
    <div class="endpoints">
        <button class="btn" onclick="fire('GET','/api/v2/guilds/'+g()+'/roles')">
            <span class="method m-GET">GET</span> /roles (list)</button>
        <button class="btn" onclick="fire('PUT','/api/v2/guilds/'+g()+'/members/'+u()+'/roles/'+r())">
            <span class="method m-PUT">PUT</span> assign role</button>
        <button class="btn" onclick="fire('DELETE','/api/v2/guilds/'+g()+'/members/'+u()+'/roles/'+r())">
            <span class="method m-DELETE">DEL</span> remove role</button>
        <button class="btn" onclick="fire('POST','/api/v2/guilds/'+g()+'/members/'+u()+'/roles', JSON.stringify({role_ids:[r()]}))">
            <span class="method m-POST">POST</span> bulk set roles</button>
    </div>
</div>

<!-- Endpoints: Moderation -->
<div class="section">
    <div class="section-title">Moderación</div>
    <div class="endpoints">
        <button class="btn" onclick="fire('POST','/api/v2/guilds/'+g()+'/members/'+u()+'/kick', JSON.stringify({reason:'Test kick'}))">
            <span class="method m-POST">POST</span> kick</button>
        <button class="btn" onclick="fire('POST','/api/v2/guilds/'+g()+'/members/'+u()+'/ban', JSON.stringify({reason:'Test ban', delete_message_days:0}))">
            <span class="method m-POST">POST</span> ban</button>
        <button class="btn" onclick="fire('DELETE','/api/v2/guilds/'+g()+'/bans/'+u())">
            <span class="method m-DELETE">DEL</span> unban</button>
        <button class="btn" onclick="fire('POST','/api/v2/guilds/'+g()+'/members/'+u()+'/timeout', JSON.stringify({duration_seconds:300, reason:'Test timeout'}))">
            <span class="method m-POST">POST</span> timeout 5min</button>
        <button class="btn" onclick="fire('DELETE','/api/v2/guilds/'+g()+'/members/'+u()+'/timeout')">
            <span class="method m-DELETE">DEL</span> remove timeout</button>
    </div>
</div>

<!-- Custom request -->
<div class="custom">
    <div class="section-title">Petición personalizada</div>
    <div class="custom-row">
        <select id="inp_method">
            <option>GET</option><option>POST</option><option>PATCH</option>
            <option>PUT</option><option>DELETE</option>
        </select>
        <input id="inp_path" type="text" placeholder="/api/v2/...">
        <button class="btn btn-send" onclick="fireCustom()">Enviar</button>
    </div>
    <textarea id="inp_body" rows="2" placeholder='JSON body (opcional): {"key": "value"}'></textarea>
</div>

<!-- Response -->
<div class="response" id="response">
    <div class="resp-header">
        <span class="resp-status" id="resp_status">—</span>
        <span class="resp-meta" id="resp_meta"></span>
    </div>
    <div class="resp-url" id="resp_url"></div>
    <pre id="resp_body">Haz clic en un endpoint para ver la respuesta aquí.</pre>
</div>

<script>
const $ = id => document.getElementById(id);
const g = () => $('inp_guild').value || '0';
const u = () => $('inp_user').value || '0';
const r = () => $('inp_role').value || '0';

async function fire(method, path, body) {
    $('resp_status').textContent = '...';
    $('resp_status').className = 'resp-status';
    $('resp_meta').textContent = '';
    $('resp_url').textContent = method + ' ' + path;
    $('resp_body').textContent = 'Cargando...';
    $('resp_body').className = 'loading';

    const form = new FormData();
    form.append('_action', 'proxy');
    form.append('base_url', $('inp_base').value);
    form.append('token', $('inp_token').value);
    form.append('method', method);
    form.append('path', path);
    if (body) form.append('body', body);

    try {
        const res = await fetch(location.href, { method: 'POST', body: form });
        const data = await res.json();

        if (data._error) {
            $('resp_status').textContent = 'ERROR';
            $('resp_status').className = 'resp-status s5xx';
            $('resp_meta').textContent = data._ms + 'ms';
            $('resp_body').className = '';
            $('resp_body').textContent = data._error;
            return;
        }

        const code = data._http;
        $('resp_status').textContent = code;
        $('resp_status').className = 'resp-status ' + (code < 300 ? 's2xx' : code < 500 ? 's4xx' : 's5xx');
        $('resp_meta').textContent = data._ms + 'ms';
        $('resp_url').textContent = data._url || '';
        $('resp_body').className = '';
        $('resp_body').textContent = JSON.stringify(data._body, null, 2);
    } catch (e) {
        $('resp_status').textContent = 'FAIL';
        $('resp_status').className = 'resp-status s5xx';
        $('resp_body').className = '';
        $('resp_body').textContent = 'Fetch error: ' + e.message;
    }

    // Actualizar Custom con la última petición
    $('inp_method').value = method;
    $('inp_path').value = path;
    if (body) $('inp_body').value = body;
}

function fireCustom() {
    const method = $('inp_method').value;
    const path = $('inp_path').value;
    const body = $('inp_body').value.trim() || undefined;
    if (!path) { alert('Introduce un path'); return; }
    fire(method, path, body);
}

// Persist config in localStorage
['inp_base','inp_token','inp_guild','inp_user','inp_role'].forEach(id => {
    const saved = localStorage.getItem('apiv2_' + id);
    if (saved) $(id).value = saved;
    $(id).addEventListener('input', () => localStorage.setItem('apiv2_' + id, $(id).value));
});
</script>

</body>
</html>
