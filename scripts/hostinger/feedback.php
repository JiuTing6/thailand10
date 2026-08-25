<?php
/**
 * feedback.php — Thailand10 newsroom 👍/👎 反馈端点（Hostinger 共享主机）
 *
 * - POST：浏览器投一票，append 一行 JSON 到 votes.jsonl
 * - GET ：ingest 拉取，按 id 聚合「最新一票」返回 {"updated_at":..,"votes":[..]}
 * - 鉴权：Authorization: Bearer <TOKEN>（与前端/ingest 共享 secret）
 * - CORS：允许 GitHub Pages 源跨域（迁站到 Hostinger 同源后可收紧/去掉）
 *
 * 部署：把本文件改名为 feedback.php，连同（自动生成的）votes.jsonl 放进某 public_html
 *      目录（如 rusabiru.com/t10/）。确保目录可写（PHP 进程能创建/追加 votes.jsonl）。
 *      改下面 TOKEN 为真实 secret，与前端 newsroom.html 的 FEEDBACK_TOKEN、
 *      Mac mini 的 ~/.config/claude-notify/env 里 T10_FEEDBACK_TOKEN 三处一致。
 */

// ── 配置 ──────────────────────────────────────────────────────────────────
$TOKEN          = 'CHANGE_ME_SHARED_SECRET';     // ⚠️ 部署时改成真实随机串
$DATA_FILE      = __DIR__ . '/votes.jsonl';       // append-only 投票日志
$ALLOWED_ORIGIN = '*';                            // 收紧示例：'https://<user>.github.io'
$MAX_BODY       = 4096;                            // 单条 POST body 上限（字节），防滥用
$VALID_VOTES    = array('up', 'down', 'none');     // none = 撤销

// ── CORS ──────────────────────────────────────────────────────────────────
header('Access-Control-Allow-Origin: ' . $ALLOWED_ORIGIN);
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Authorization, Content-Type');
header('Access-Control-Max-Age: 86400');

$method = $_SERVER['REQUEST_METHOD'];
if ($method === 'OPTIONS') {            // 预检
    http_response_code(204);
    exit;
}

// ── 鉴权 ──────────────────────────────────────────────────────────────────
function bearer_token() {
    $h = '';
    if (isset($_SERVER['HTTP_AUTHORIZATION'])) {
        $h = $_SERVER['HTTP_AUTHORIZATION'];
    } elseif (function_exists('apache_request_headers')) {
        $hdrs = apache_request_headers();
        if (isset($hdrs['Authorization'])) $h = $hdrs['Authorization'];
    }
    if (stripos($h, 'Bearer ') === 0) return trim(substr($h, 7));
    return '';
}

if (!hash_equals($TOKEN, bearer_token())) {
    http_response_code(403);
    header('Content-Type: application/json');
    echo json_encode(array('error' => 'forbidden'));
    exit;
}

header('Content-Type: application/json; charset=utf-8');

// ── POST：写一票 ────────────────────────────────────────────────────────────
if ($method === 'POST') {
    $raw = file_get_contents('php://input', false, null, 0, $MAX_BODY + 1);
    if (strlen($raw) > $MAX_BODY) {
        http_response_code(413);
        echo json_encode(array('error' => 'payload too large'));
        exit;
    }
    $in = json_decode($raw, true);
    if (!is_array($in) || empty($in['id']) || !in_array(($in['vote'] ?? ''), $VALID_VOTES, true)) {
        http_response_code(400);
        echo json_encode(array('error' => 'bad request'));
        exit;
    }
    // 规范化记录：只留需要的字段 + 服务端时间戳（不信任客户端 ts）
    $rec = array(
        'id'        => substr((string)$in['id'], 0, 64),
        'vote'      => $in['vote'],
        'title_cn'  => isset($in['title_cn'])  ? substr((string)$in['title_cn'], 0, 300) : '',
        'topic_tag' => isset($in['topic_tag']) ? substr((string)$in['topic_tag'], 0, 32)  : '',
        'source'    => isset($in['source'])    ? substr((string)$in['source'], 0, 64)     : '',
        'ts'        => gmdate('Y-m-d\TH:i:s\Z'),
    );
    $line = json_encode($rec, JSON_UNESCAPED_UNICODE) . "\n";
    $fp = fopen($DATA_FILE, 'a');
    if ($fp === false) {
        http_response_code(500);
        echo json_encode(array('error' => 'cannot open data file'));
        exit;
    }
    flock($fp, LOCK_EX);
    fwrite($fp, $line);
    flock($fp, LOCK_UN);
    fclose($fp);
    echo json_encode(array('ok' => true));
    exit;
}

// ── GET：聚合返回每 id 最新一票 ───────────────────────────────────────────────
if ($method === 'GET') {
    $latest = array();   // id → record
    if (is_readable($DATA_FILE)) {
        $fp = fopen($DATA_FILE, 'r');
        if ($fp) {
            while (($l = fgets($fp)) !== false) {
                $l = trim($l);
                if ($l === '') continue;
                $r = json_decode($l, true);
                if (!is_array($r) || empty($r['id'])) continue;
                $id = $r['id'];
                if (!isset($latest[$id]) || strcmp((string)$r['ts'], (string)$latest[$id]['ts']) >= 0) {
                    $latest[$id] = $r;
                }
            }
            fclose($fp);
        }
    }
    // 撤销（vote=none）的不下发
    $votes = array();
    foreach ($latest as $r) {
        if (($r['vote'] ?? '') === 'none') continue;
        $votes[] = $r;
    }
    echo json_encode(array(
        'updated_at' => gmdate('Y-m-d\TH:i:s\Z'),
        'votes'      => array_values($votes),
    ), JSON_UNESCAPED_UNICODE);
    exit;
}

http_response_code(405);
echo json_encode(array('error' => 'method not allowed'));
