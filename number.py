# app.py
from flask import Flask, request, redirect, url_for, render_template_string, session, abort
import random, string, os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "imigawakaranai")
# 本番(https)でセッションが安定するようクッキー設定
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=True
)

# ====== 定数 ======
NUM_MIN = 1
NUM_MAX = 50
HIDDEN_MIN = 1
HIDDEN_MAX = 30

# 最大数のデフォルト（プレイヤーごとに上書きできるように）
INFO_MAX_DEFAULT = 7

def get_info_max(room, pid):
    return room.get('info_max', {}).get(pid, INFO_MAX_DEFAULT)

# ルームごとのルール既定値
RULE_DEFAULTS = {
    'trap': True,       # kill/info トラップ
    'bluff': True,      # ブラフヒント
    'guessflag': True,  # ゲスフラグ
    'decl1': True,      # 一の位の宣言＆嘘だ！コール
    'press': True,      # サドン・プレス（Double or Nothing）
}

# ルームの全状態を保持（簡易インメモリ）
rooms = {}  # room_id -> dict(state)

# ====== ユーティリティ ======

def get_int(form, key, default=None, min_v=None, max_v=None):
    """form[key] を安全に int に。失敗時は default を返す。範囲もチェック。"""
    v = form.get(key)
    if v is None or v == '':
        return default
    try:
        x = int(v)
    except Exception:
        return default
    if min_v is not None and x < min_v:
        return default
    if max_v is not None and x > max_v:
        return default
    return x

def push_and_back(room, pid, msg, to_play=True):
    """ログを残してプレイ画面へ戻る（またはロビーへ）。"""
    if msg:
        push_log(room, msg)
    rid = get_current_room_id()
    if to_play:
        return redirect(url_for('play', room_id=rid))
    else:
        return redirect(url_for('room_lobby', room_id=rid))

def gen_room_id():
    while True:
        rid = ''.join(random.choices(string.digits, k=4))
        if rid not in rooms:
            return rid

def eff_ranges(allow_negative: bool):
    if allow_negative:
        return -NUM_MAX, NUM_MAX, -HIDDEN_MAX, HIDDEN_MAX
    return NUM_MIN, NUM_MAX, HIDDEN_MIN, HIDDEN_MAX

def bootstrap_page(title, body_html):
    # Bootstrap + ちょいデザイン（コントラスト高め＆灰色→明るめ）
    return render_template_string("""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{title}}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background:#0b1220; color:#f1f5f9; }
    a, .btn-link { color:#93c5fd; }
    a:hover, .btn-link:hover { color:#bfdbfe; }

    .card { background:#0f172a; border:1px solid #334155; }
    .card-header { background:#0b1323; border-bottom:1px solid #334155; }

    .btn-primary { background:#2563eb; border-color:#1d4ed8; }
    .btn-primary:hover { background:#1d4ed8; border-color:#1e40af; }

    .btn-outline-light { color:#f1f5f9; border-color:#94a3b8; }
    .btn-outline-light:hover { color:#0b1220; background:#e2e8f0; border-color:#e2e8f0; }

    .badge { font-size:.9rem; }
    /* 明るいバッジに変更（灰色撤廃） */
    .badge.bg-secondary {
      background-color:#f472b6 !important;  /* ピンク */
      color:#0b1220 !important;             /* コントラスト確保 */
      border:1px solid #fda4af !important;
    }

    .form-control, .form-select { background:#0b1323; color:#f1f5f9; border-color:#475569; }
    .form-control::placeholder { color:#e9c5d9; opacity:1; }
    .form-control:focus, .form-select:focus { border-color:#93c5fd; box-shadow:none; }

    /* 明るめに統一（グレー排除） */
    .text-muted, .small.text-muted, .form-label { color:#f9a8d4 !important; }
    .small.text-warning, .text-warning { color:#f9a8d4 !important; }

    .log-box { max-height:40vh; overflow:auto; background:#0b1323; color:#e2e8f0; padding:1rem; border:1px solid #334155; border-radius:.5rem; }
    .value { color:#f9a8d4; font-weight:600; }
  </style>
</head>
<body>
  <div class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h1 class="h4 m-0">やまやまやま</h1>
      <div class="d-flex gap-2">
        <button type="button" class="btn btn-sm btn-outline-light" data-bs-toggle="modal" data-bs-target="#rulesModal">ルール</button>
        <a class="btn btn-sm btn-outline-light" href="{{ url_for('index') }}">ホームへ</a>
      </div>
    </div>
    {{ body|safe }}
    <!-- Rules Modal -->
    <div class="modal fade" id="rulesModal" tabindex="-1" aria-hidden="true">
      <div class="modal-dialog modal-lg modal-dialog-scrollable">
        <div class="modal-content" style="background:#0f172a;color:#f1f5f9;border:1px solid #334155;">
          <div class="modal-header">
            <h5 class="modal-title">ルール説明</h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body">
            <p class="mb-2">※ ルーム作成時のトグルで<strong>各機能をON/OFF</strong>できます（ルームにより無効な場合があります）。</p>
            <ol class="mb-3">
              <li class="mb-2"><strong>勝利条件</strong>：相手の秘密の数字を当てるとラウンド勝利。先取ポイントに到達したプレイヤーがマッチ勝利。</li>
              <li class="mb-2"><strong>基本レンジ</strong>：選べる数は <code>{{ NUM_MIN }}</code>〜<code>{{ NUM_MAX }}</code>（負の数ON時は ±範囲）。隠し数は <code>{{ HIDDEN_MIN }}</code>〜<code>{{ HIDDEN_MAX }}</code>。</li>
              <li class="mb-2"><strong>ヒント</strong>：和/差/積から1つが得られます。後攻のみ各ラウンド1回、種類の指定が可能。ブラフが有効な場合は常に「ブラフかどうか」の確認が入ります。</li>
              <li class="mb-2"><strong>トラップ</strong>（ON時）：
                <ul>
                  <li><strong>kill</strong>：±1命中で即死、±5命中で次ターンスキップ（設置はターン消費／上書き1個）。</li>
                  <li><strong>info</strong>：踏まれると、<em>その時点以降</em>の相手の行動履歴を閲覧可能。通常は同時最大7個・1ターンに無料1個設置（ターン消費なし）。チェックすると3個まとめて（ターン消費）設置できます。</li>
                </ul>
              </li>
              <li class="mb-2"><strong>ブラフヒント</strong>（ON時）：相手の次回ヒント時に偽の値を提示。相手は「信じる／ブラフだ！」を選択。指摘成功で本物ヒント×2（在庫消費）、失敗で以後ヒント取得時にCT1。</li>
              <li class="mb-2"><strong>ゲスフラグ</strong>（ON時）：自分ターンに設置（ターン消費・各ラウンド1回）。次の相手ターンで相手が予想したら即死。未発動ならその次の相手ターン開始時に「危なかった！」通知。</li>
              <li class="mb-2"><strong>一の位 宣言（decl1）</strong>（ON時）：ターン消費なし・各ラウンド1回。「自分の一の位(0〜9)」を宣言。嘘だ！成功で正しい一の位公開＋直後に無料予想。失敗で次ターンスキップ。<br>
                さらに宣言者は<strong>そのラウンド中</strong>、無料infoが<strong>1ターン2個</strong>に増え、info最大数が<strong>10</strong>になります。</li>
              <li class="mb-2"><strong>サドン・プレス</strong>（ON時）：ハズレ直後に同ターンでもう1回だけ連続予想（当たれば勝利、外せば次ターンスキップ）。各ラウンド1回。</li>
              <li class="mb-2"><strong>自分の数の変更（c）</strong>：自分のトラップ値とは重複不可。使用後は自分の<span class="value">CT2</span>、かつ相手のヒント在庫をリセット。</li>
            </ol>
            <p class="small text-warning">UIの表記色は明るめに統一しています。ログに表示される相手行動の詳細は、infoトラップで閲覧権が付与された場合のみ（発動時以降）表示されます。</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-primary" data-bs-dismiss="modal">閉じる</button>
          </div>
        </div>
      </div>
    </div>
    <!-- Bootstrap JS bundle for modal support -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  </div>
</body>
</html>
""", title=title, body=body_html)

def init_room(allow_negative: bool, target_points: int, rules=None):
    if rules is None:
        rules = RULE_DEFAULTS.copy()
    else:
        base = RULE_DEFAULTS.copy()
        base.update({k: bool(v) for k, v in rules.items()})
        rules = base
    eff_nmin, eff_nmax, eff_hmin, eff_hmax = eff_ranges(allow_negative)
    return {
        'allow_negative': allow_negative,
        'eff_num_min': eff_nmin,
        'eff_num_max': eff_nmax,
        'eff_hidden_min': eff_hmin,
        'eff_hidden_max': eff_hmax,
        'target_points': target_points,
        'round_no': 1,
        'score': {1:0, 2:0},
        'turn': 1,  # このラウンドの開始番（途中で勝敗ついたら、次は負け側が先手）
        'pname': {1: None, 2: None},
        'secret': {1: None, 2: None},
        'hidden': None,
        'tries': {1:0, 2:0},
        'available_hints': {1: ['和','差','積'], 2: ['和','差','積']},
        'hint_choice_available': {1: False, 2: True},  # 毎ラウンド後攻のみ可（ベースルール）
        'cooldown': {1:0, 2:0},  # c のCT（自分の番カウント）
        'trap_kill': {1: [], 2: []}, # ±1即死, ±5次ターンスキップ
        'trap_info': {1: [], 2: []}, # 踏むと相手が次ターン以降ログ閲覧可
        'pending_view': {1: False, 2: False},
        'can_view': {1: False, 2: False},
        'view_cut_index': {1: None, 2: None},
        'skip_next_turn': {1: False, 2: False},
        'info_set_this_turn': {1: False, 2: False},  # 当ターンにinfoを1個置いたか
        'info_max': {1: INFO_MAX_DEFAULT, 2: INFO_MAX_DEFAULT},  # info最大数（通常7、宣言で10へ）
        'info_free_per_turn': {1: 1, 2: 1},                      # 無料info/ターン（通常1、宣言で2へ）
        'info_free_used_this_turn': {1: 0, 2: 0},                # 当ターンに無料で置いた個数
        'actions': [],
        'winner': None,   # ラウンド勝者(1 or 2)
        'phase': 'lobby', # lobby -> play -> end_round
        'starter': 1,     # 次ラウンドの先手（負け側に自動切替）
        'rules': rules,   # ★ ルームに紐づくルールトグル

        # === 既存：ブラフヒント／ゲスフラグ ===
        'bluff': {1: None, 2: None},
        'hint_penalty_active': {1: False, 2: False},
        'hint_ct': {1: 0, 2: 0},
        'guess_flag_armed': {1: False, 2: False},
        'guess_flag_ct': {1: 0, 2: 0},
        'guess_penalty_active': {1: False, 2: False},
        'guess_ct': {1: 0, 2: 0},
        'guess_flag_warn': {1: False, 2: False},
        'guess_flag_used': {1: False, 2: False},

        # === 新規：一の位宣言 ===
        'decl1_value': {1: None, 2: None},      # 宣言した一の位（0〜9）
        'decl1_used': {1: False, 2: False},     # 各ラウンド1回
        'decl1_resolved': {1: True, 2: True},   # 宣言が解決済みか（最初は解決扱い）
        'decl1_hint_token_ready': {1: False, 2: False},   # 宣言者の「次の自分ターンだけ種類指定可」予約
        'decl1_hint_token_active': {1: False, 2: False},  # 上記が有効化中（そのターン限定）
        'free_guess_pending': {1: False, 2: False},       # 嘘だ！成功で直後の無料予想待ち

        # === 新規：サドン・プレス（Double or Nothing） ===
        'press_used': {1: False, 2: False},     # ラウンド1回まで
        'press_pending': {1: False, 2: False},  # ハズレ直後の追撃予想待ち
    }

def room_or_404(rid):
    room = rooms.get(rid)
    if not room:
        abort(404)
    return room

def player_guard(rid, pid):
    room = room_or_404(rid)
    if pid not in (1,2):
        abort(404)
    return room

def push_log(room, s):
    room['actions'].append(s)

def switch_turn(room, cur_pid):
    # CTを減らす
    for p in (1,2):
        if room['cooldown'][p] > 0: room['cooldown'][p] -= 1
        if room['hint_ct'][p] > 0: room['hint_ct'][p] -= 1
        if room['guess_ct'][p] > 0: room['guess_ct'][p] -= 1
        if room['guess_flag_ct'][p] > 0: room['guess_flag_ct'][p] -= 1

    # infoトラップの閲覧反映
    opp = 2 if cur_pid == 1 else 1
    if room['pending_view'][opp]:
        room['can_view'][opp] = True
        room['pending_view'][opp] = False

    room['turn'] = opp
    # ★ info：ターン交代で無料設置カウンタをリセット
    room['info_free_used_this_turn'][opp] = 0

    # ★ 一の位の“ヒント指定トークン”の仕組みは廃止（今回の新効果に置換）
    # （トークン関連のフラグ操作は削除）

    # ゲスフラグ未発動の失効は guessflag 有効時のみ
    if room['rules'].get('guessflag', True):
        gf_owner = 2 if cur_pid == 1 else 1
        if room['guess_flag_armed'][gf_owner]:
            room['guess_flag_armed'][gf_owner] = False
            room['guess_flag_warn'][cur_pid] = True

# ====== ルーティング ======

@app.route('/')
def index():
    body = """
<div class="row g-3">
  <div class="col-12 col-lg-6">
    <div class="card">
      <div class="card-header">ルーム作成</div>
      <div class="card-body">
        <form method="post" action="/create_room">
          <div class="mb-3">
            <label class="form-label">負の数を許可</label>
            <select class="form-select" name="allow_negative">
              <option value="n">しない</option>
              <option value="y">する</option>
            </select>
          </div>
          <div class="mb-3">
            <label class="form-label">先取ポイント</label>
            <input type="number" class="form-control" name="target_points" min="1" value="3">
          </div>
          <hr class="my-3">
          <div class="mb-2"><span class="badge bg-secondary">ルールトグル</span></div>
          <div class="form-check">
            <input class="form-check-input" type="checkbox" id="rule_trap" name="rule_trap" checked>
            <label class="form-check-label" for="rule_trap">トラップ（kill / info）</label>
          </div>
          <div class="form-check">
            <input class="form-check-input" type="checkbox" id="rule_bluff" name="rule_bluff" checked>
            <label class="form-check-label" for="rule_bluff">ブラフヒント</label>
          </div>
          <div class="form-check">
            <input class="form-check-input" type="checkbox" id="rule_guessflag" name="rule_guessflag" checked>
            <label class="form-check-label" for="rule_guessflag">ゲスフラグ</label>
          </div>
          <div class="form-check">
            <input class="form-check-input" type="checkbox" id="rule_decl1" name="rule_decl1" checked>
            <label class="form-check-label" for="rule_decl1">一の位の宣言＆嘘だ！コール</label>
          </div>
          <div class="form-check mb-3">
            <input class="form-check-input" type="checkbox" id="rule_press" name="rule_press" checked>
            <label class="form-check-label" for="rule_press">サドン・プレス（Double or Nothing）</label>
          </div>
          <button class="btn btn-primary w-100">ルームを作成</button>
        </form>
      </div>
    </div>
  </div>
  
  <div class="col-12 col-lg-6">
    <div class="card">
      <div class="card-header">ルームに参加</div>
      <div class="card-body">
        <form method="get" action="/room">
          <div class="mb-3">
            <label class="form-label">ルームID（4桁）</label>
            <input class="form-control" name="room_id" inputmode="numeric" pattern="\\d{4}" placeholder="1234" required>
          </div>
          <button class="btn btn-outline-light w-100">ロビーへ</button>
        </form>
      </div>
    </div>
  </div>
</div>
"""
    return bootstrap_page("ホーム", body)

@app.post('/create_room')
def create_room():
    allow_neg = request.form.get('allow_negative', 'n') == 'y'
    target_points = int(request.form.get('target_points', 3))
    rules = {
        'trap': bool(request.form.get('rule_trap')),
        'bluff': bool(request.form.get('rule_bluff')),
        'guessflag': bool(request.form.get('rule_guessflag')),
        'decl1': bool(request.form.get('rule_decl1')),
        'press': bool(request.form.get('rule_press')),
    }
    rid = gen_room_id()
    rooms[rid] = init_room(allow_neg, target_points, rules)
    return redirect(url_for('room_lobby', room_id=rid))

@app.get('/room')
def room_lobby_redirect():
    rid = request.args.get('room_id', '').strip()
    if not rid or rid not in rooms:
        return bootstrap_page("エラー", f"""
<div class="alert alert-danger">そのルームは見つかりませんでした。</div>
<a class="btn btn-primary" href="{url_for('index')}">ホームへ</a>
""")
    return redirect(url_for('room_lobby', room_id=rid))

@app.get('/room/<room_id>')
def room_lobby(room_id):
    room = room_or_404(room_id)
    l1 = url_for('join', room_id=room_id, player_id=1, _external=True)
    l2 = url_for('join', room_id=room_id, player_id=2, _external=True)
    p1 = room['pname'][1] or '未参加'
    p2 = room['pname'][2] or '未参加'
    body = f"""
<div class="card mb-3">
  <div class="card-header">ルーム {room_id}</div>
  <div class="card-body">
  <!-- ルーム番号を大きく表示 -->
  <div class="p-3 rounded border border-secondary mb-3">
    <div class="small text-warning">ルーム番号</div>
    <div class="h1 m-0 value">{room_id}</div>
    <div class="small">相手は「ホーム → ルームに参加」でこの番号を入力してください。</div>
  </div>

  <p class="mb-2">URLを共有したい場合はこちらを送ってください。</p>
    <div class="row g-2">
      <div class="col-12 col-md-6">
        <div class="p-2 rounded border border-secondary">
          <div class="small text-warning mb-1">プレイヤー1用リンク</div>
          <a href="{l1}">{l1}</a>
          <div class="mt-1"><span class="badge bg-secondary">状態</span> {p1}</div>
        </div>
      </div>
      <div class="col-12 col-md-6">
        <div class="p-2 rounded border border-secondary">
          <div class="small text-warning mb-1">プレイヤー2用リンク</div>
          <a href="{l2}">{l2}</a>
          <div class="mt-1"><span class="badge bg-secondary">状態</span> {p2}</div>
        </div>
      </div>
    </div>
    <hr/>
    <a class="btn btn-outline-light" href="{url_for('index')}">ホームへ</a>
  </div>
</div>
"""
    return bootstrap_page(f"ロビー {room_id}", body)

@app.route('/join/<room_id>/<int:player_id>', methods=['GET','POST'])
def join(room_id, player_id):
    room = player_guard(room_id, player_id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip() or f'プレイヤー{player_id}'
        secret = int(request.form.get('secret'))
        # 入力チェック
        if not (room['eff_num_min'] <= secret <= room['eff_num_max']):
            err = f"{room['eff_num_min']}〜{room['eff_num_max']}の整数で入力してください。"
            return join_form(room_id, player_id, err)
        # 参加登録
        room['pname'][player_id] = name
        room['secret'][player_id] = secret
        session['room_id'] = room_id
        session['player_id'] = player_id
        # 相手が揃ったらラウンド開始準備
        if room['pname'][1] and room['pname'][2]:
            start_new_round(room)
        # セッションが飛んでもURLで本人識別できるよう as=player_id を付与
        return redirect(url_for('play', room_id=room_id) + f"?as={player_id}")
    return join_form(room_id, player_id)

def join_form(room_id, player_id, error=None):
    room = rooms[room_id]
    body = f"""
<div class="card">
  <div class="card-header">ルーム {room_id} に プレイヤー{player_id} として参加</div>
  <div class="card-body">
    {"<div class='alert alert-danger'>" + error + "</div>" if error else ""}
    <form method="post">
      <div class="mb-3">
        <label class="form-label">ニックネーム</label>
        <input class="form-control" name="name" placeholder="プレイヤー{player_id}">
      </div>
      <div class="mb-3">
        <label class="form-label">秘密の数字 ({room['eff_num_min']}〜{room['eff_num_max']})</label>
        <input class="form-control" type="number" name="secret"
                required min="{room['eff_num_min']}" max="{room['eff_num_max']}"
                placeholder="{room['eff_num_min']}〜{room['eff_num_max']}">
      </div>
      <button class="btn btn-primary w-100">参加</button>
    </form>
  </div>
</div>
"""
    return bootstrap_page("参加", body)

def start_new_round(room):
    # ラウンド開始（両者の秘密の数字が入ったタイミングで）
    
    room['hidden'] = random.randint(room['eff_hidden_min'], room['eff_hidden_max'])
    room['tries'] = {1:0, 2:0}
    room['actions'] = []
    room['trap_kill'] = {1: [], 2: []}
    room['trap_info'] = {1: [], 2: []}
    room['pending_view'] = {1: False, 2: False}
    room['can_view'] = {1: False, 2: False}
    room['view_cut_index'] = {1: None, 2: None}
    room['skip_next_turn'] = {1: False, 2: False}
    room['info_set_this_turn'] = {1: False, 2: False}
    room['info_max'] = {1: INFO_MAX_DEFAULT, 2: INFO_MAX_DEFAULT}
    room['info_free_per_turn'] = {1: 1, 2: 1}
    room['info_free_used_this_turn'] = {1: 0, 2: 0}
    room['cooldown'] = {1: 0, 2: 0}
    room['available_hints'] = {1: ['和','差','積'], 2: ['和','差','積']}
    room['bluff'] = {1: None, 2: None}
    room['hint_penalty_active'] = {1: False, 2: False}
    room['hint_ct'] = {1: 0, 2: 0}
    room['guess_flag_armed'] = {1: False, 2: False}
    room['guess_flag_ct'] = {1: 0, 2: 0}
    room['guess_penalty_active'] = {1: False, 2: False}
    room['guess_ct'] = {1: 0, 2: 0}
    room['guess_flag_warn'] = {1: False, 2: False}
    room['guess_flag_used'] = {1: False, 2: False}

    # 一の位宣言
    room['decl1_value'] = {1: None, 2: None}
    room['decl1_used'] = {1: False, 2: False}
    room['decl1_resolved'] = {1: True, 2: True}
    room['decl1_hint_token_ready'] = {1: False, 2: False}
    room['decl1_hint_token_active'] = {1: False, 2: False}
    room['free_guess_pending'] = {1: False, 2: False}

    # サドン・プレス
    room['press_used'] = {1: False, 2: False}
    room['press_pending'] = {1: False, 2: False}
    
    # 先手/後手のヒント指定可フラグ
    if room['starter'] == 1:
        room['hint_choice_available'] = {1: False, 2: True}
        room['turn'] = 1
    else:
        room['hint_choice_available'] = {1: True, 2: False}
        room['turn'] = 2
    room['winner'] = None
    room['phase'] = 'play'

@app.route('/play/<room_id>', methods=['GET','POST'])
def play(room_id):
    room = room_or_404(room_id)
    # クエリ ?as=1/2 が来たら、その場でセッションをバインド（別タブ/クッキー無効対策）
    as_pid = request.args.get('as')
    if as_pid in ('1','2'):
        session['room_id'] = room_id
        session['player_id'] = int(as_pid)
    # プレイヤー同定（URLだけで来たとき用）
    pid = session.get('player_id')
    rid = session.get('room_id')
    if rid != room_id or pid not in (1,2):
        # 未紐付けならロビーへ誘導
        return redirect(url_for('room_lobby', room_id=room_id))

    # まだ2人揃ってない場合はロビーに戻さず待機画面を表示
    if not (room['pname'][1] and room['pname'][2]):
        l1 = url_for('join', room_id=room_id, player_id=1, _external=True)
        l2 = url_for('join', room_id=room_id, player_id=2, _external=True)
        p1 = room['pname'][1] or '未参加'
        p2 = room['pname'][2] or '未参加'
        opp = 2 if pid == 1 else 1
        wait_body = f"""
<div class="card mb-3">
  <div class="card-header">相手を待っています…</div>
  <div class="card-body">
  <!-- ルーム番号を大きく表示 -->
  <div class="p-3 rounded border border-secondary mb-3">
    <div class="small text-warning">ルーム番号</div>
    <div class="h1 m-0 value">{room_id}</div>
    <div class="small">相手は「ホーム → ルームに参加」でこの番号を入力できます。</div>
  </div>

  <div class="alert alert-info">あなたは <span class="value">プレイヤー{pid}</span> として参加済みです。相手が参加すると自動で開始します。</div>
    <p class="mb-2">相手に送るべきリンクは <span class="value">プレイヤー{opp}用リンク</span> です。</p>
    <div class="row g-2">
      <div class="col-12 col-md-6">
        <div class="p-2 rounded border border-secondary">
          <div class="small text-warning mb-1">プレイヤー1用リンク</div>
          <a href="{l1}">{l1}</a>
          <div class="mt-1"><span class="badge bg-secondary">状態</span> {p1}</div>
        </div>
      </div>
      <div class="col-12 col-md-6">
        <div class="p-2 rounded border border-secondary">
          <div class="small text-warning mb-1">プレイヤー2用リンク</div>
          <a href="{l2}">{l2}</a>
          <div class="mt-1"><span class="badge bg-secondary">状態</span> {p2}</div>
        </div>
      </div>
    </div>
    <div class="mt-3 d-flex gap-2">
      <a class="btn btn-primary" href="{url_for('play', room_id=room_id)}">更新</a>
      <a class="btn btn-outline-light" href="{url_for('room_lobby', room_id=room_id)}">ロビーへ</a>
    </div>
  </div>
</div>
"""
        return bootstrap_page("相手待ち", wait_body)

    # 勝敗確定（end_roundへ）
    if room['winner'] is not None:
        return redirect(url_for('end_round', room_id=room_id))

    # スキップ処理
    if room['skip_next_turn'][room['turn']]:
        room['skip_next_turn'][room['turn']] = False
        push_log(room, f"{room['pname'][room['turn']]} のターンは近接トラップ効果でスキップ")
        cur = room['turn']
        switch_turn(room, cur)
        # ターンを進めたらリダイレクトして状態を反映
        return redirect(url_for('play', room_id=room_id))

    # POST: アクション処理
    if request.method == 'POST':
        if room['turn'] != pid:
            return redirect(url_for('play', room_id=room_id))  # 自分の番でなければ無視
        try:
            action = request.form.get('action')

            if action == 'g':
                guess_val = get_int(request.form, 'guess',
                                    default=None,
                                    min_v=room['eff_num_min'], max_v=room['eff_num_max'])
                if guess_val is None:
                    return push_and_back(room, pid, "⚠ 予想値が不正です。")
                return handle_guess(room, pid, guess_val)

            elif action == 'h':
                return handle_hint(room, pid, request.form)

            elif action == 'c':
                new_secret = get_int(request.form, 'new_secret',
                                     default=None,
                                     min_v=room['eff_num_min'], max_v=room['eff_num_max'])
                if new_secret is None:
                    return push_and_back(room, pid, "⚠ 変更する数が不正です。")
                return handle_change(room, pid, new_secret)

            elif action == 't':
                return handle_trap(room, pid, request.form)

            elif action == 't_kill':
                return handle_trap_kill(room, pid, request.form)

            elif action == 't_info':
                return handle_trap_info(room, pid, request.form)

            elif action == 'bh':
                return handle_bluff(room, pid, request.form)

            elif action == 'gf':
                return handle_guessflag(room, pid)

            elif action == 'decl1':
                return handle_decl1(room, pid, request.form)

            elif action == 'decl1_challenge':
                return handle_decl1_challenge(room, pid)

            elif action == 'press':
                press_val = get_int(request.form, 'press_guess',
                                    default=None,
                                    min_v=room['eff_num_min'], max_v=room['eff_num_max'])
                if press_val is None:
                    return push_and_back(room, pid, "⚠ サドン・プレスの値が不正です。")
                return handle_press(room, pid, press_val)

            elif action == 'free_guess':
                fg_val = get_int(request.form, 'free_guess',
                                 default=None,
                                 min_v=room['eff_num_min'], max_v=room['eff_num_max'])
                if fg_val is None:
                    return push_and_back(room, pid, "⚠ 無料予想の値が不正です。")
                return handle_free_guess(room, pid, fg_val)

            else:
                return push_and_back(room, pid, "⚠ 不明なアクションです。")

        except Exception:
            app.logger.exception("POST処理中の例外")
            return redirect(url_for('index'))
    # 表示用データ
    p1, p2 = room['pname'][1], room['pname'][2]
    myname = room['pname'][pid]
    opp   = 2 if pid == 1 else 1
    oppname = room['pname'][opp]

    c_available = (room['cooldown'][pid] == 0)
    hint_available = True  # 表示上は在庫非表示にする（内部在庫は維持）

    # ゲスフラグ失効の警告（自分のターン開始時に一度だけ表示）
    if request.method == 'GET' and room['turn'] == pid and room.get('guess_flag_warn', {}).get(pid):
        other = 2 if pid == 1 else 1
        # 自分宛ての通知として記録（自分の名前で始めてフィルタに掛からないようにする）
        push_log(room, f"{room['pname'][pid]} への通知: 実は前のターンに {room['pname'][other]} がゲスフラグを立てていた。危なかった！")
        room['guess_flag_warn'][pid] = False

    # 相手のフル行動は info トラップで閲覧権が付与された場合のみ、かつ発動時点以降を表示
    filtered = []
    cut = room['view_cut_index'][pid]
    for idx, entry in enumerate(room['actions']):
        if entry.startswith(f"{myname} "):
            filtered.append(entry)
            continue
        if entry.startswith(f"{oppname} が g（予想）→"):
            filtered.append(entry)
            continue
        if room['can_view'][pid] and (cut is None or idx >= cut) and entry.startswith(f"{oppname} "):
            filtered.append(entry)
            continue
        # それ以外の相手の行動は隠す

    log_html = "".join(f"<li>{e}</li>" for e in filtered)

    # 自分の番フォーム
    my_turn_block = ""
    ru = room['rules']
    if room['turn'] == pid:
        # 無料予想（嘘だ！成功）優先（decl1が有効のときだけ現れるUI）
        if room['free_guess_pending'][pid] and ru.get('decl1', True):
            my_turn_block = f"""
<div class="card mb-3">
  <div class="card-header">無料予想（嘘だ！成功）</div>
  <div class="card-body">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="free_guess">
      <label class="form-label">もう一度だけ無料で予想できます</label>
      <input class="form-control mb-2" name="free_guess" type="number" required min="{room['eff_num_min']}" max="{room['eff_num_max']}" placeholder="{room['eff_num_min']}〜{room['eff_num_max']}">
      <button class="btn btn-primary w-100">予想を送る</button>
      <div class="small text-warning mt-1">※ トラップは有効（±1即死/±5スキップ/info）。ゲスフラグは発動しません。</div>
    </form>
  </div>
</div>
"""
        # サドン・プレス（有効時のみ）
        elif room['press_pending'][pid] and ru.get('press', True):
            my_turn_block = f"""
<div class="card mb-3">
  <div class="card-header">サドン・プレス（Double or Nothing）</div>
  <div class="card-body">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="press">
      <label class="form-label">さっきのハズレ直後に、もう一回だけ連続で予想できます</label>
      <input class="form-control mb-2" name="press_guess" type="number" required min="{room['eff_num_min']}" max="{room['eff_num_max']}" placeholder="{room['eff_num_min']}〜{room['eff_num_max']}">
      <button class="btn btn-primary w-100">もう一回だけ予想！</button>
      <div class="small text-warning mt-1">※ 当たれば勝利。外すと次ターンスキップ（このラウンド1回まで）。</div>
    </form>
  </div>
</div>
"""
        else:
            # ★ 宣言の“ヒント指定トークン”を廃止 → 先攻/後攻の既存フラグのみ
            choose_allowed = room['hint_choice_available'][pid]

            # ルールごとのUI出し分け
            if ru.get('trap', True):
                trap_block = f"""
  <div class="col-12 col-md-6">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="t">
      <label class="form-label">トラップ</label>
      <select class="form-select mb-2" name="trap_kind">
        <option value="k">kill（±1即死 / ±5次ターンスキップ）</option>
        <option value="i">info（踏むと相手行動のフル履歴を閲覧可）</option>
      </select>
      <div class="mb-2">
        <input class="form-control mb-2" name="trap_kill_value" type="number" placeholder="killは1つだけ（上書き）">
        <div class="small text-warning">
        infoは通常 最大7個（宣言後は10個）。入力欄は3つ。<br>
        既定：<strong>無料で1個/ターン（宣言後は2個/ターン、ターン消費なし）</strong>。<br>
        チェックで<strong>3個まとめて（ターン消費）</strong>。同一ターンに無料とまとめ置きを併用できます（※まとめ置きを送信するとターン終了）。
        </div>
        <input class="form-control mb-2" name="trap_info_value" type="number" placeholder="info(1)">
        <input class="form-control mb-2" name="trap_info_value_1" type="number" placeholder="info(2)">
        <input class="form-control mb-2" name="trap_info_value_2" type="number" placeholder="info(3)">
        <div class="form-check">
          <input class="form-check-input" type="checkbox" name="info_bulk" value="1" id="info_bulk">
          <label class="form-check-label" for="info_bulk">infoを3つまとめて置く（ターン消費）</label>
        </div>
      </div>
      <button class="btn btn-outline-light w-100">設定する</button>
    </form>
  </div>
"""
            else:
                trap_block = ""

            if ru.get('bluff', True):
                bluff_block = f"""
  <div class="col-12 col-md-6">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="bh">
      <label class="form-label">ブラフヒントを仕掛ける</label>
      <div class="mb-2">
        <select class="form-select mb-2" name="bluff_type">
          <option value="和">和（相手には種類は表示されません）</option>
          <option value="差">差</option>
          <option value="積">積</option>
        </select>
        <input class="form-control" type="number" name="bluff_value" placeholder="相手に見せる数値（必須）" required>
      </div>
      <button class="btn btn-outline-light w-100">ブラフを設定（ターン消費）</button>
    </form>
  </div>
"""
            else:
                bluff_block = ""

            if ru.get('guessflag', True):
                gf_block = f"""
  <div class="col-12 col-md-6">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="gf">
      <label class="form-label">ゲスフラグを立てる</label>
      <div class="small text-warning mb-2">次の相手ターンに予想してきたら相手は即死（このラウンド1回まで）</div>
      <button class="btn btn-outline-light w-100" {"disabled" if room['guess_flag_used'][pid] else ""}>立てる（このラウンド1回）</button>
      <div class="small text-warning mt-1">{ "（このラウンドは既に使用しました）" if room['guess_flag_used'][pid] else "" }</div>
    </form>
  </div>
"""
            else:
                gf_block = ""

            if ru.get('decl1', True):
                decl_block = f"""
  <div class="col-12 col-md-6">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="decl1">
      <label class="form-label">一の位を宣言（0〜9）</label>
      <input class="form-control mb-2" name="decl1_digit" type="number" min="0" max="9" {"required" if not room['decl1_used'][pid] else "disabled"} placeholder="0〜9">
      <button class="btn btn-outline-light w-100" {"disabled" if room['decl1_used'][pid] else ""}>宣言（ターン消費なし）</button>
      <div class="small text-warning mt-1">
        { "（このラウンドは既に宣言済み）" if room['decl1_used'][pid] else "宣言すると、このラウンド中は『無料info』が1ターンに2個まで置けるようになり、infoの最大所持数が10個になります。" }
      </div>
    </form>
  </div>
"""
            else:
                decl_block = ""

            decl_challenge_block = f"""
  <div class="col-12 col-md-6">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="decl1_challenge">
      <label class="form-label">相手の「一の位」宣言にチャレンジ</label>
      <button class="btn btn-outline-light w-100">嘘だ！コール</button>
      <div class="small text-warning mt-1">嘘なら正しい一の位公開＋直後に無料予想。真ならあなたは次ターンスキップ。</div>
    </form>
  </div>
""" if (ru.get('decl1', True) and (room['decl1_value'][opp] is not None and not room['decl1_resolved'][opp])) else ""

            my_turn_block = f"""
<div class="card mb-3">
  <div class="card-header">アクション</div>
  <div class="card-body">
    <div class="row g-2">
      <div class="col-12 col-md-6">
        <form method="post" class="p-2 border rounded">
          <input type="hidden" name="action" value="g">
          <label class="form-label">相手の数字を予想</label>
          <input class="form-control mb-2" name="guess" type="number" required placeholder="{room['eff_num_min']}〜{room['eff_num_max']}">
          <button class="btn btn-primary w-100" {"disabled" if room['guess_ct'][pid] > 0 else ""}>予想する</button>
          <div class="small text-warning mt-1">{ "（予想はクールタイム中）" if room['guess_ct'][pid] > 0 else "" }</div>
        </form>
      </div>

      <div class="col-12 col-md-6">
        <form method="post" class="p-2 border rounded">
          <input type="hidden" name="action" value="h">
          <div class="mb-2">
            <label class="form-label">ヒント</label>
            { "<div class='mb-2'><label class='form-label'>種類を指定</label><select class='form-select' name='hint_type'><option>和</option><option>差</option><option>積</option></select><input type='hidden' name='confirm_choice' value='1'></div>" if choose_allowed else "<div class='small text-warning mb-2'>(このターンは種類指定不可。ランダム)</div>" }
          </div>
          <button class="btn btn-outline-light w-100" {"disabled" if room['hint_ct'][pid] > 0 else ""}>ヒントをもらう</button>
          <div class="small text-warning mt-1">{ "（ヒントはクールタイム中）" if room['hint_ct'][pid] > 0 else "" }</div>
        </form>
      </div>

      <div class="col-12 col-md-6">
        <form method="post" class="p-2 border rounded">
          <input type="hidden" name="action" value="c">
          <label class="form-label">自分の数を変更</label>
          <input class="form-control mb-2" name="new_secret" type="number" required min="{room['eff_num_min']}" max="{room['eff_num_max']}" placeholder="{room['eff_num_min']}〜{room['eff_num_max']}">
          <button class="btn btn-outline-light w-100" {"disabled" if room['cooldown'][pid] > 0 else ""}>変更する（CT2）</button>
        </form>
      </div>

      {trap_block}
      {bluff_block}
      {gf_block}
      {decl_block}
      {decl_challenge_block}

    </div>
  </div>
</div>
"""

    # 右側パネル等と合わせてページ本体を組み立て
    body = f"""
<div class="row g-3">
  <div class="col-12 col-lg-8">
    {my_turn_block}
    <div class="card">
      <div class="card-header">アクション履歴</div>
      <div class="card-body">
        <div class="log-box"><ol class="mb-0">{log_html}</ol></div>
      </div>
    </div>
  </div>

  <div class="col-12 col-lg-4">
    <div class="card mb-3">
      <div class="card-header">あなた</div>
      <div class="card-body">
        <div class="mb-1"><span class="badge bg-secondary">名前</span> <span class="value">{myname}</span></div>
        <div class="mb-1"><span class="badge bg-secondary">自分の秘密の数</span> <span class="value">{room['secret'][pid]}</span></div>
        <div class="mb-1"><span class="badge bg-secondary">CT</span> c:<span class="value">{room['cooldown'][pid]}</span> / h:<span class="value">{room['hint_ct'][pid]}</span> / g:<span class="value">{room['guess_ct'][pid]}</span></div>
        <div class="mb-1"><span class="badge bg-secondary">トラップ</span><br>
        {("<span class='small text-warning'>A(kill): <span class='value'>" + (", ".join(map(str, room['trap_kill'][pid])) if room['trap_kill'][pid] else "なし") + "</span></span><br><span class='small text-warning'>B(info): <span class='value'>" + (", ".join(map(str, room['trap_info'][pid])) if room['trap_info'][pid] else "なし") + "</span></span>") if room['rules'].get('trap', True) else "<span class='small text-warning'>このルームでは無効</span>" }
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">相手</div>
      <div class="card-body">
        <div class="mb-1"><span class="badge bg-secondary">名前</span> <span class="value">{oppname}</span></div>
        <div class="mb-1"><span class="badge bg-secondary">あなたに対する予想回数</span> <span class="value">{room['tries'][opp]}</span></div>
        <div class="mb-1"><span class="badge bg-secondary">ログ閲覧権（info）</span> {"有効" if room['can_view'][opp] else "なし"}</div>
        <div class="small text-warning">レンジ: <span class="value">{room['eff_num_min']}〜{room['eff_num_max']}</span></div>
      </div>
    </div>
  </div>
</div>
"""
    return bootstrap_page(f"対戦 - {myname}", body)
@app.get('/end/<room_id>')
def end_round(room_id):
    room = room_or_404(room_id)
    if room['winner'] is None:
        return redirect(url_for('play', room_id=room_id))
    winner = room['winner']
    winner_name = room['pname'][winner]
    tries = room['tries'][winner]
    p1, p2 = room['pname'][1], room['pname'][2]
    target = room['target_points']
    match_over = (room['score'][1] >= target) or (room['score'][2] >= target)

    log_html_full = "".join(f"<li>{e}</li>" for e in room['actions'])
    body = f"""
<div class="card mb-3">
  <div class="card-header">ラウンド {room['round_no']} の結果</div>
  <div class="card-body">
    <p class="h5">勝者: {winner_name} <span class="badge bg-success">{tries} 回で正解</span></p>
    <p class="mb-1">{p1} の数: {room['secret'][1]}</p>
    <p class="mb-1">{p2} の数: {room['secret'][2]}</p>
    <p class="mb-1">誰にも知らない数: {room['hidden']}</p>
    <hr/>
    <div class="h6">現在スコア: {p1} {room['score'][1]} - {room['score'][2]} {p2}（先取 {target}）</div>
    <div class="mt-3">
      {"<a class='btn btn-primary' href='" + url_for('finish_match', room_id=room_id) + "'>マッチ終了</a>" if match_over else "<a class='btn btn-primary' href='" + url_for('next_round', room_id=room_id) + "'>次のラウンドへ</a>"}
      <a class="btn btn-outline-light ms-2" href="{url_for('play', room_id=room_id)}">対戦画面へ戻る</a>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-header">このラウンドの行動履歴（フル）</div>
  <div class="card-body">
    <div class="log-box"><ol class="mb-0">{log_html_full}</ol></div>
  </div>
</div>
"""
    return bootstrap_page("ラウンド結果", body)

@app.get('/next/<room_id>')
def next_round(room_id):
    room = room_or_404(room_id)
    if room['winner'] is None:
        return redirect(url_for('play', room_id=room_id))
    # 次ラウンド準備：負け側が先手
    loser = 2 if room['winner'] == 1 else 1
    room['starter'] = loser
    room['round_no'] += 1
    # 次ラウンドは秘密の数を再入力（安全）
    room['secret'][1] = None
    room['secret'][2] = None
    room['phase'] = 'lobby'
    return redirect(url_for('room_lobby', room_id=room_id))

@app.get('/finish/<room_id>')
def finish_match(room_id):
    room = room_or_404(room_id)
    p1, p2 = room['pname'][1], room['pname'][2]
    msg = f"🏆 マッチ終了！ {p1} {room['score'][1]} - {room['score'][2]} {p2}"
    # ルームを消す（残したいなら残してもOK）
    del rooms[room_id]
    return bootstrap_page("マッチ終了", f"<div class='alert alert-info'>{msg}</div><a class='btn btn-primary' href='{url_for('index')}'>ホームへ</a>")

# ====== アクション処理 ======

def _hint_once(room, pid, chose_by_user=False, silent=False):
    """ヒントを1回実行しログを残す（在庫からランダム消費）。"""
    opp = 2 if pid == 1 else 1
    opp_secret = room['secret'][opp]
    hidden = room['hidden']
    stock = room['available_hints'][pid]
    if stock:
        htype = random.choice(stock)
        stock.remove(htype)
    else:
        htype = random.choice(['和','差','積'])
    if htype == '和':
        val = opp_secret + hidden
    elif htype == '差':
        val = abs(opp_secret - hidden)
    else:
        val = opp_secret * hidden
    if not silent:
        myname = room['pname'][pid]
        push_log(room, f"{myname} が h（ヒントを取得）＝{val}")
    return

def handle_guess(room, pid, guess):
    opp = 2 if pid == 1 else 1
    myname = room['pname'][pid]
    opponent_secret = room['secret'][opp]

    if room['guess_ct'][pid] > 0:
        push_log(room, "（予想はクールタイム中）")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    room['tries'][pid] += 1

    # ゲスフラグ（有効時のみ）
    if room['rules'].get('guessflag', True) and room['guess_flag_armed'][opp]:
        room['guess_flag_armed'][opp] = False
        push_log(room, f"（{room['pname'][opp]} のゲスフラグが発動！{room['pname'][pid]} は即死）")
        room['score'][opp] += 1
        room['winner'] = opp
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    # 正解優先
    if guess == opponent_secret:
        push_log(room, f"{myname} が g（予想）→ {guess}（正解！相手は即死）")
        room['score'][pid] += 1
        room['winner'] = pid
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    # トラップ判定（有効時）
    kill = set(room['trap_kill'][opp]) if room['rules'].get('trap', True) else set()
    info = set(room['trap_info'][opp]) if room['rules'].get('trap', True) else set()

    if any(abs(guess - k) <= 1 for k in kill):
        push_log(room, f"{myname} が g（予想）→ {guess}（killトラップ±1命中＝即敗北）")
        room['score'][opp] += 1
        room['winner'] = opp
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    if guess in info:
        room['pending_view'][opp] = True
        room['view_cut_index'][opp] = len(room['actions'])
        push_log(room, f"{myname} が g（予想）→ {guess}（情報トラップ発動）")

    if any(abs(guess - k) <= 5 for k in kill):
        room['skip_next_turn'][pid] = True
        push_log(room, f"{myname} が g（予想）→ {guess}（kill近接±5命中：次ターンスキップ）")
        if room['guess_penalty_active'][pid]:
            room['guess_ct'][pid] = 1
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    # ハズレ → サドン・プレス（有効時のみ）
    push_log(room, f"{myname} が g（予想）→ {guess}（ハズレ）")
    if room['rules'].get('press', True) and (not room['press_used'][pid]) and (not room['press_pending'][pid]):
        room['press_pending'][pid] = True
        return redirect(url_for('play', room_id=get_current_room_id()))

    if room['guess_penalty_active'][pid]:
        room['guess_ct'][pid] = 1
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))
def handle_hint(room, pid, form):
    """ヒント実行。
    - ブラフ有効：常に確認ダイアログ（ブラフ有無に関係なく）
    - ブラフ無効：確認なしで通常ヒント
    """
    myname = room['pname'][pid]
    opp = 2 if pid == 1 else 1

    if room['hint_ct'][pid] > 0:
        push_log(room, "（ヒントはクールタイム中）")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    want_choose = bool(form.get('confirm_choice'))
    choose_type = form.get('hint_type')

    # ブラフ無効 → 通常ヒント
    if not room['rules'].get('bluff', True):
        allow_choose_now = want_choose and room['hint_choice_available'][pid] and choose_type in ('和','差','積')
        if allow_choose_now:
            room['hint_choice_available'][pid] = False  # 後攻1回の指定権だけ維持
            opp_secret = room['secret'][opp]
            hidden = room['hidden']
            if choose_type == '和':
                val = opp_secret + hidden
            elif choose_type == '差':
                val = abs(opp_secret - hidden)
            else:
                val = opp_secret * hidden
            push_log(room, f"{myname} が h（ヒント取得）{choose_type}＝{val}")
        else:
            _hint_once(room, pid, chose_by_user=False, silent=False)
        if room['hint_penalty_active'][pid]:
            room['hint_ct'][pid] = 1
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    # ここからブラフ有効：必ず確認
    decision = form.get('bluff_decision')  # 'believe' or 'accuse' or None
    has_bluff = bool(room['bluff'][opp])

    if not decision:
        keep = ""
        if want_choose:
            keep += "<input type='hidden' name='confirm_choice' value='1'>"
        if want_choose and choose_type:
            keep += f"<input type='hidden' name='hint_type' value='{choose_type}'>"
        if has_bluff:
            fake = room['bluff'][opp]
            body = f"""
<div class="card">
  <div class="card-header">ヒント（確認）</div>
  <div class="card-body">
    <p class="h5 mb-3">提示されたヒントの値： <span class="badge bg-warning text-dark">{fake['value']}</span></p>
    <p class="mb-3">このヒントはブラフだと思いますか？</p>
    <form method="post" class="d-inline me-2">
      <input type="hidden" name="action" value="h">
      <input type="hidden" name="bluff_decision" value="believe">
      {keep}
      <button class="btn btn-primary">信じる</button>
    </form>
    <form method="post" class="d-inline">
      <input type="hidden" name="action" value="h">
      <input type="hidden" name="bluff_decision" value="accuse">
      {keep}
      <button class="btn btn-outline-light">ブラフだ！と指摘する</button>
    </form>
    <div class="mt-3">
      <a class="btn btn-outline-light" href="{url_for('play', room_id=get_current_room_id())}">戻る</a>
    </div>
  </div>
</div>
"""
        else:
            body = f"""
<div class="card">
  <div class="card-header">ヒント（確認）</div>
  <div class="card-body">
    <p class="mb-3">このヒントはブラフだと思いますか？</p>
    <form method="post" class="d-inline me-2">
      <input type="hidden" name="action" value="h">
      <input type="hidden" name="bluff_decision" value="believe">
      {keep}
      <button class="btn btn-primary">信じる（通常のヒントを受け取る）</button>
    </form>
    <form method="post" class="d-inline">
      <input type="hidden" name="action" value="h">
      <input type="hidden" name="bluff_decision" value="accuse">
      {keep}
      <button class="btn btn-outline-light">ブラフだ！と指摘する</button>
    </form>
    <div class="mt-3">
      <a class="btn btn-outline-light" href="{url_for('play', room_id=get_current_room_id())}">戻る</a>
    </div>
  </div>
</div>
"""
        return bootstrap_page("ヒント確認", body)

    # 意思決定後
    if has_bluff:
        if decision == 'believe':
            push_log(room, f"{myname} は 提示ヒント（{room['bluff'][opp]['value']}）を受け入れた")
            room['bluff'][opp] = None
            if room['hint_penalty_active'][pid]:
                room['hint_ct'][pid] = 1
            switch_turn(room, pid)
            return redirect(url_for('play', room_id=get_current_room_id()))
        else:
            _hint_once(room, pid, chose_by_user=False, silent=False)
            _hint_once(room, pid, chose_by_user=False, silent=False)
            room['bluff'][opp] = None
            if room['hint_penalty_active'][pid]:
                room['hint_ct'][pid] = 1
            switch_turn(room, pid)
            return redirect(url_for('play', room_id=get_current_room_id()))
    else:
        if decision == 'accuse':
            room['hint_penalty_active'][pid] = True
            push_log(room, f"{myname} は ブラフだと指摘したが外れ（以後ヒント取得後はCT1）")
            switch_turn(room, pid)
            return redirect(url_for('play', room_id=get_current_room_id()))
        else:
            allow_choose_now = want_choose and room['hint_choice_available'][pid] and choose_type in ('和','差','積')
            if allow_choose_now:
                room['hint_choice_available'][pid] = False  # 後攻1回の指定権だけ維持
                opp_secret = room['secret'][opp]
                hidden = room['hidden']
                if choose_type == '和':
                    val = opp_secret + hidden
                elif choose_type == '差':
                    val = abs(opp_secret - hidden)
                else:
                    val = opp_secret * hidden
                push_log(room, f"{myname} が h（ヒント取得）{choose_type}＝{val}")
            else:
                _hint_once(room, pid, chose_by_user=False, silent=False)
            if room['hint_penalty_active'][pid]:
                room['hint_ct'][pid] = 1
            switch_turn(room, pid)
            return redirect(url_for('play', room_id=get_current_room_id()))
    
def handle_change(room, pid, new_secret):
    myname = room['pname'][pid]

    # ★サーバ側ガード：CT中は変更不可（UIバイパス対策）
    if room['cooldown'][pid] > 0:
        push_log(room, "（自分の数の変更はクールタイム中）")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    # トラップ衝突禁止
    my_traps = set(room['trap_kill'][pid]) | set(room['trap_info'][pid])
    if new_secret in my_traps:
        push_log(room, "⚠ その数字は現在のトラップに含まれています。別の数字を選んでください。")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    # 範囲チェック
    if not (room['eff_num_min'] <= new_secret <= room['eff_num_max']):
        push_log(room, "⚠ 範囲外の数字です。")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    room['secret'][pid] = new_secret
    room['cooldown'][pid] = 2
    # 相手のヒント在庫リセット
    opp = 2 if pid == 1 else 1
    room['available_hints'][opp] = ['和','差','積']
    push_log(room, f"{myname} が c（自分の数を変更）→ {new_secret}")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))



def handle_trap_kill(room, pid, form):
    if not room['rules'].get('trap', True):
        return push_and_back(room, pid, "（このルームではトラップは無効です）")
    myname = room['pname'][pid]
    eff_min, eff_max = room['eff_num_min'], room['eff_num_max']
    my_secret = room['secret'][pid]
    v = form.get('trap_kill_value')
    try:
        x = int(v)
    except Exception:
        push_log(room, "⚠ 無効なkillトラップ値です。")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    # 範囲＆自分の数／絶対値一致を禁止
    if not (eff_min <= x <= eff_max) or x == my_secret or (room['allow_negative'] and abs(x) == abs(my_secret)):
        push_log(room, "⚠ 無効なkillトラップ値です。")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    room['trap_kill'][pid].clear()
    room['trap_kill'][pid].append(x)
    push_log(room, f"{myname} が killトラップを {x} に設定")
    # kill はターン消費あり（従来どおり）
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_decl1(room, pid, form):
    if not room['rules'].get('decl1', True):
        return push_and_back(room, pid, "（このルームでは一の位の宣言は無効です）")
    myname = room['pname'][pid]
    if room['decl1_used'][pid]:
        return push_and_back(room, pid, "（このラウンドは既に宣言しています）")
    d = get_int(form, 'decl1_digit', default=None, min_v=0, max_v=9)
    if d is None:
        return push_and_back(room, pid, "⚠ 一の位は0〜9で入力してください。")

    room['decl1_value'][pid] = d
    room['decl1_used'][pid] = True
    room['decl1_resolved'][pid] = False

    # ★ 新効果：このラウンド中ずっと
    room['info_free_per_turn'][pid] = 2   # 無料info/ターン → 2個
    room['info_max'][pid] = 10            # 最大所持数 → 10個

    push_log(room, f"{myname} が 一の位を宣言（このラウンド中、無料infoは1ターンに2個・最大10個まで）")
    # ターン消費なし
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_decl1_challenge(room, pid):
    if not room['rules'].get('decl1', True):
        return push_and_back(room, pid, "（このルームでは一の位の宣言は無効です）")
    """嘘だ！コール。嘘なら正しい一の位を公開し、直後に無料予想。
       真ならコール側が次ターンスキップ。いずれもターンは消費。
    """
    myname = room['pname'][pid]
    opp = 2 if pid == 1 else 1
    if room['decl1_value'][opp] is None or room['decl1_resolved'][opp]:
        return push_and_back(room, pid, "（相手の宣言は現在チャレンジできません）")
    # 真偽判定（負の数は絶対値で一の位を取る）
    true_ones = abs(room['secret'][opp]) % 10
    declared = room['decl1_value'][opp]
    if declared != true_ones:
        # 嘘を見破り → 正しい一の位公開＋直後に無料予想
        push_log(room, f"{myname} が『嘘だ！』→ 成功。正しい一の位は {true_ones}")
        room['decl1_resolved'][opp] = True
        room['free_guess_pending'][pid] = True
        # 同一ターン内で無料予想へ
        return redirect(url_for('play', room_id=get_current_room_id()))
    else:
        # コール失敗 → 次ターンスキップ
        push_log(room, f"{myname} が『嘘だ！』→ 失敗。次ターンをスキップ")
        room['decl1_resolved'][opp] = True
        room['skip_next_turn'][pid] = True
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

def handle_free_guess(room, pid, guess):
    """嘘だ！成功時の無料予想。CTは無視するが、トラップ（±1即死/±5スキップ/info）は有効。
       ゲスフラグ（次の相手ターン限定）は発動しない。
    """
    opp = 2 if pid == 1 else 1
    myname = room['pname'][pid]
    room['free_guess_pending'][pid] = False  # フラグ消す

    opponent_secret = room['secret'][opp]
    # まずは正解優先
    if guess == opponent_secret:
        push_log(room, f"{myname} が 無料g（予想）→ {guess}（正解！相手は即死）")
        room['score'][pid] += 1
        room['winner'] = pid
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    # トラップ判定
    kill = set(room['trap_kill'][opp])
    info = set(room['trap_info'][opp])

    # ±1 即死（相手勝利）
    if any(abs(guess - k) <= 1 for k in kill):
        push_log(room, f"{myname} が 無料g（予想）→ {guess}（killトラップ±1命中＝即敗北）")
        room['score'][opp] += 1
        room['winner'] = opp
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    # info発動
    if guess in info:
        room['pending_view'][opp] = True
        room['view_cut_index'][opp] = len(room['actions'])
        push_log(room, f"{myname} が 無料g（予想）→ {guess}（情報トラップ発動）")

    # ±5 次ターンスキップ
    if any(abs(guess - k) <= 5 for k in kill):
        room['skip_next_turn'][pid] = True
        push_log(room, f"{myname} が 無料g（予想）→ {guess}（kill近接±5命中：次ターンスキップ）")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    # 通常ハズレ → ターン終了
    push_log(room, f"{myname} が 無料g（予想）→ {guess}（ハズレ）")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))


# === サドン・プレス（Double or Nothing） ===
def handle_press(room, pid, guess):
    if not room['rules'].get('press', True):
        return push_and_back(room, pid, "（このルームではサドン・プレスは無効です）")
    """サドン・プレス：ハズレ直後に同一ターンで追加の1回予想。
    - 当たればその場で勝利
    - 外したら次ターンスキップ
    - トラップ（±1即死/±5スキップ/info）は有効
    - このラウンドで1回だけ使用可能
    """
    opp = 2 if pid == 1 else 1
    myname = room['pname'][pid]

    # フラグ整理（ここに来ている時点で press_pending は True のはず）
    room['press_pending'][pid] = False
    room['press_used'][pid] = True

    # 予想回数カウント
    room['tries'][pid] += 1

    opponent_secret = room['secret'][opp]

    # まず正解優先
    if guess == opponent_secret:
        push_log(room, f"{myname} が プレスg（予想）→ {guess}（正解！相手は即死）")
        room['score'][pid] += 1
        room['winner'] = pid
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    # トラップ判定
    kill = set(room['trap_kill'][opp])
    info = set(room['trap_info'][opp])

    # ±1 即死（相手勝利）
    if any(abs(guess - k) <= 1 for k in kill):
        push_log(room, f"{myname} が プレスg（予想）→ {guess}（killトラップ±1命中＝即敗北）")
        room['score'][opp] += 1
        room['winner'] = opp
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    # info 発動（発動時点以降の相手行動が閲覧可）
    if guess in info:
        room['pending_view'][opp] = True
        room['view_cut_index'][opp] = len(room['actions'])
        push_log(room, f"{myname} が プレスg（予想）→ {guess}（情報トラップ発動）")

    # ±5 近接で次ターンスキップ
    if any(abs(guess - k) <= 5 for k in kill):
        room['skip_next_turn'][pid] = True
        push_log(room, f"{myname} が プレスg（予想）→ {guess}（kill近接±5命中：次ターンスキップ）")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    # ただのハズレ → 次ターンスキップ付与して交代
    push_log(room, f"{myname} が プレスg（予想）→ {guess}（ハズレ）")
    room['skip_next_turn'][pid] = True
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_trap_info(room, pid, form):
    if not room['rules'].get('trap', True):
        return push_and_back(room, pid, "（このルームではトラップは無効です）")
    myname = room['pname'][pid]
    eff_min, eff_max = room['eff_num_min'], room['eff_num_max']
    my_secret = room['secret'][pid]

    max_allowed = get_info_max(room, pid)
    free_cap = room['info_free_per_turn'][pid]
    free_used = room['info_free_used_this_turn'][pid]

    # モード判定：チェックありなら "まとめて最大3個（ターン消費）"
    bulk = form.get('info_bulk') in ('1', 'on', 'true', 'True')

    # まとめて置く（ターン消費）
    if bulk:
        # 無料infoと同一ターンでの併用を許可（ガード削除）
        candidates = ('trap_info_value', 'trap_info_value_1', 'trap_info_value_2', 'trap_info_val')
        added_list = []
        for key in candidates:
            v = form.get(key)
            if not v: continue
            try: x = int(v)
            except: continue
            if not (eff_min <= x <= eff_max): continue
            if x == my_secret or (room['allow_negative'] and abs(x) == abs(my_secret)): continue
            if x in room['trap_info'][pid] or x in added_list: continue
            if len(room['trap_info'][pid]) >= max_allowed: break
            added_list.append(x)

        if added_list:
            room['trap_info'][pid].extend(added_list)
            push_log(room, f"{myname} が infoトラップをまとめて設定 → {', '.join(map(str, added_list))}（ターン消費）")
            switch_turn(room, pid)  # まとめ置きはターン消費
        else:
            push_log(room, "⚠ infoトラップの追加はありません。")
        return redirect(url_for('play', room_id=get_current_room_id()))

    # 無料で置く（ターン消費なし）…上限 free_cap / ターン
    if free_used >= free_cap:
        push_log(room, f"（このターンの無料infoは上限 {free_cap} 個に達しています）")
        return redirect(url_for('play', room_id=get_current_room_id()))

    candidates = ('trap_info_value', 'trap_info_value_1', 'trap_info_value_2', 'trap_info_val')
    added = None
    for key in candidates:
        v = form.get(key)
        if not v: continue
        try: x = int(v)
        except: continue
        if not (eff_min <= x <= eff_max): continue
        if x == my_secret or (room['allow_negative'] and abs(x) == abs(my_secret)): continue
        if x in room['trap_info'][pid]: continue
        if len(room['trap_info'][pid]) >= max_allowed:
            push_log(room, f"（infoは最大{max_allowed}個までです）")
            return redirect(url_for('play', room_id=get_current_room_id()))
        added = x
        break

    if added is not None:
        room['trap_info'][pid].append(added)
        room['info_free_used_this_turn'][pid] += 1
        push_log(room, f"{myname} が infoトラップを {added} に設定（ターン消費なし／このターンはあと {free_cap - room['info_free_used_this_turn'][pid]} 個）")
    else:
        push_log(room, "⚠ infoトラップの追加はありません。")

    # 無料モードはターン消費なし → 交代しない
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_trap(room, pid, form):
    """共通トラップハンドラ（UIの action='t' から来る）"""
    if not room['rules'].get('trap', True):
        return push_and_back(room, pid, "（このルームではトラップは無効です）")
    kind = form.get('trap_kind')
    if kind == 'k':
        return handle_trap_kill(room, pid, form)
    elif kind == 'i':
        return handle_trap_info(room, pid, form)
    else:
        push_log(room, "⚠ 無効なトラップ種別です。")
        return redirect(url_for('play', room_id=get_current_room_id()))

def handle_bluff(room, pid, form):
    if not room['rules'].get('bluff', True):
        return push_and_back(room, pid, "（このルームではブラフヒントは無効です）")
    """ブラフヒントを設定（ターン消費あり）。次回 相手がヒント要求時に表示される。"""
    myname = room['pname'][pid]
    btype = form.get('bluff_type') or '和'
    try:
        bval = int(form.get('bluff_value'))
    except:
        push_log(room, "⚠ ブラフ値が不正です。")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    room['bluff'][pid] = {'type': btype, 'value': bval}
    push_log(room, f"{myname} が ブラフヒント を仕掛けた")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_guessflag(room, pid):
    if not room['rules'].get('guessflag', True):
        return push_and_back(room, pid, "（このルームではゲスフラグは無効です）")
    """ゲスフラグを立てる（ターン消費）。相手が“次のターン”に予想したら相手は即死。1ラウンド1回まで。"""
    myname = room['pname'][pid]
    if room['guess_flag_used'][pid]:
        push_log(room, "⚠ このラウンドでは既にゲスフラグを使っています。")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    room['guess_flag_armed'][pid] = True
    room['guess_flag_used'][pid] = True
    push_log(room, f"{myname} が ゲスフラグ を立てた")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

# === 一の位宣言／嘘だ！コール／無料予想 ===

def get_current_room_id():
    return session.get('room_id')

# ====== エラーハンドラ ======
@app.errorhandler(404)
def on_404(e):
    return bootstrap_page("404", f"""
<div class="alert alert-warning">ページが見つかりませんでした。</div>
<a class="btn btn-primary" href="{url_for('index')}">ホームへ</a>
"""), 404

@app.errorhandler(500)
def on_500(e):
    # 壊れたセッションの回復
    try:
        rid = session.get('room_id')
        pid = session.get('player_id')
        if not rid or rid not in rooms or pid not in (1,2):
            session.clear()
    except:
        session.clear()
    return bootstrap_page("エラー", f"""
<div class="alert alert-danger">Internal Server Error が発生しました。もう一度お試しください。</div>
<a class="btn btn-primary" href="{url_for('index')}">ホームへ</a>
"""), 500

# ====== 起動 ======
if __name__ == '__main__':
    # Render等の本番では gunicorn などで起動。ローカル検証は以下でOK
    app.run(host='0.0.0.0', port=5000, debug=True)
