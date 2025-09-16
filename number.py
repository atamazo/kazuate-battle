# app.py
from flask import Flask, request, redirect, url_for, render_template_string, session, abort
import random, string, os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "imigawakaranai")

# ====== 定数 ======
NUM_MIN = 1
NUM_MAX = 50
HIDDEN_MIN = 1
HIDDEN_MAX = 30

# ルームの全状態を保持（簡易インメモリ）
rooms = {}  # room_id -> dict(state)

# ====== ユーティリティ ======
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
    # Bootstrap + ちょいデザイン
    return render_template_string("""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{title}}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    /* High-contrast dark theme */
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

    .form-control, .form-select { background:#0b1323; color:#f1f5f9; border-color:#475569; }
    .form-control::placeholder { color:#cbd5e1; opacity:1; }
    .form-control:focus, .form-select:focus { border-color:#93c5fd; box-shadow:none; }

    .text-muted, .small.text-muted { color:#e2e8f0 !important; }

    .log-box { max-height:40vh; overflow:auto; background:#0b1323; color:#e2e8f0; padding:1rem; border:1px solid #334155; border-radius:.5rem; }
  </style>
</head>
<body>
  <div class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h1 class="h4 m-0">Number Battle</h1>
      <a class="btn btn-sm btn-outline-light" href="{{ url_for('index') }}">ホームへ</a>
    </div>
    {{ body|safe }}
  </div>
</body>
</html>
""", title=title, body=body_html)

def init_room(allow_negative: bool, target_points: int):
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
        'hint_choice_available': {1: False, 2: True},  # 毎ラウンド後攻のみ可
        'cooldown': {1:0, 2:0},  # c のCT（自分の番カウント）
        'trap_kill': {1: [], 2: []}, # ±1即死, ±5次ターンスキップ
        'trap_info': {1: [], 2: []}, # 踏むと相手が次ターン以降ログ閲覧可
        'pending_view': {1: False, 2: False},
        'can_view': {1: False, 2: False},
        'view_cut_index': {1: None, 2: None},
        'skip_next_turn': {1: False, 2: False},
        'actions': [],
        'winner': None,   # ラウンド勝者(1 or 2)
        'phase': 'lobby', # lobby -> secrets -> play -> end_round
        'starter': 1,     # 次ラウンドの先手（負け側に自動切替）
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
        if room['cooldown'][p] > 0:
            room['cooldown'][p] -= 1
    # infoトラップの閲覧権を次ターン開始時に反映
    opp = 2 if cur_pid == 1 else 1
    if room['pending_view'][opp]:
        room['can_view'][opp] = True
        room['pending_view'][opp] = False
    # ターン交代
    room['turn'] = opp

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
    rid = gen_room_id()
    rooms[rid] = init_room(allow_neg, target_points)
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
    <p class="mb-2">このURLを相手に送ってください。</p>
    <div class="row g-2">
      <div class="col-12 col-md-6">
        <div class="p-2 rounded border border-secondary">
          <div class="small text-muted mb-1">プレイヤー1用リンク</div>
          <a href="{l1}">{l1}</a>
          <div class="mt-1"><span class="badge bg-secondary">状態</span> {p1}</div>
        </div>
      </div>
      <div class="col-12 col-md-6">
        <div class="p-2 rounded border border-secondary">
          <div class="small text-muted mb-1">プレイヤー2用リンク</div>
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
        return redirect(url_for('play', room_id=room_id))
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
        <input class="form-control" type="number" name="secret" required>
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
    room['cooldown'] = {1: 0, 2: 0}
    room['available_hints'] = {1: ['和','差','積'], 2: ['和','差','積']}
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
    # プレイヤー同定（URLだけで来たとき用）
    pid = session.get('player_id')
    rid = session.get('room_id')
    if rid != room_id or pid not in (1,2):
        # 未紐付けならロビーへ誘導
        return redirect(url_for('room_lobby', room_id=room_id))

    # まだ2人揃ってない場合
    if not (room['pname'][1] and room['pname'][2]):
        return redirect(url_for('room_lobby', room_id=room_id))

    # 勝敗確定（end_roundへ）
    if room['winner'] is not None:
        return redirect(url_for('end_round', room_id=room_id))

    # スキップ処理
    if room['skip_next_turn'][room['turn']]:
        room['skip_next_turn'][room['turn']] = False
        push_log(room, f"{room['pname'][room['turn']]} のターンは近接トラップ効果でスキップ")
        switch_turn(room, room['turn'])

    # POST: アクション処理
    if request.method == 'POST':
        if room['turn'] != pid:
            return redirect(url_for('play', room_id=room_id))  # 自分の番でなければ無視
        action = request.form.get('action')
        if action == 'g':
            guess_val = int(request.form.get('guess'))
            return handle_guess(room, pid, guess_val)
        elif action == 'h':
            return handle_hint(room, pid, request.form)
        elif action == 'c':
            new_secret = int(request.form.get('new_secret'))
            return handle_change(room, pid, new_secret)
        elif action == 't':
            return handle_trap(room, pid, request.form)

    # 表示用データ
    p1, p2 = room['pname'][1], room['pname'][2]
    myname = room['pname'][pid]
    opp   = 2 if pid == 1 else 1
    oppname = room['pname'][opp]

    c_available = (room['cooldown'][pid] == 0)
    hint_available = bool(room['available_hints'][pid]) or room['hint_choice_available'][pid]

    # 自分視点のログ拡張（infoトラップ閲覧可なら相手の行動フル表示分も含める）
    # ここでは「ログは全体共通」をシンプル表示
    log_html = "".join(f"<li>{entry}</li>" for entry in room['actions'])

    # 自分の番フォーム
    my_turn_block = ""
    if room['turn'] == pid:
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
          <button class="btn btn-primary w-100">予想する</button>
        </form>
      </div>
      <div class="col-12 col-md-6">
        <form method="post" class="p-2 border rounded">
          <input type="hidden" name="action" value="h">
          <div class="mb-2">
            <label class="form-label">ヒント</label>
            <div class="small text-muted mb-2">在庫: {", ".join(room['available_hints'][pid]) if room['available_hints'][pid] else "なし"}</div>
            {"<div class='mb-2'><label class='form-label'>種類を指定</label><select class='form-select' name='hint_type'><option>和</option><option>差</option><option>積</option></select><input type='hidden' name='confirm_choice' value='1'></div>" if room['hint_choice_available'][pid] else "<div class='text-muted small mb-2'>(このラウンドは種類指定不可。ランダム消費)</div>"}
          </div>
          <button class="btn btn-outline-light w-100" {"disabled" if not hint_available else ""}>ヒントをもらう</button>
        </form>
      </div>

      <div class="col-12 col-md-6">
        <form method="post" class="p-2 border rounded">
          <input type="hidden" name="action" value="c">
          <label class="form-label">自分の数を変更</label>
          <input class="form-control mb-2" name="new_secret" type="number" placeholder="{room['eff_num_min']}〜{room['eff_num_max']}">
          <button class="btn btn-outline-light w-100" {"disabled" if not c_available else ""}>変更する（CT2）</button>
        </form>
      </div>

      <div class="col-12 col-md-6">
        <form method="post" class="p-2 border rounded">
          <input type="hidden" name="action" value="t">
          <label class="form-label">トラップ</label>
          <select class="form-select mb-2" name="trap_kind">
            <option value="k">kill（±1即死 / ±5次ターンスキップ）</option>
            <option value="i">info（相手が踏むとあなたが次ターン以降で相手行動のフル履歴を閲覧）</option>
          </select>
          <div class="mb-2">
            <input class="form-control mb-2" name="trap_kill_value" type="number" placeholder="killは1つだけ（上書き）">
            <div class="small text-muted">infoは最大5個。必要に応じて3つまで一度に追加可：</div>
            <input class="form-control mb-2" name="trap_info_value_0" type="number" placeholder="info(1)">
            <input class="form-control mb-2" name="trap_info_value_1" type="number" placeholder="info(2)">
            <input class="form-control mb-2" name="trap_info_value_2" type="number" placeholder="info(3)">
          </div>
          <button class="btn btn-outline-light w-100">設定する</button>
        </form>
      </div>
    </div>
  </div>
</div>
"""

    body = f"""
<div class="row g-3">
  <div class="col-12 col-lg-8">
    <div class="card mb-3">
      <div class="card-header d-flex justify-content-between align-items-center">
        <div>ルーム <span class="badge bg-secondary">{room_id}</span></div>
        <div>ラウンド <span class="badge bg-info">{room['round_no']}</span></div>
      </div>
      <div class="card-body">
        <div class="d-flex flex-wrap gap-2 align-items-center">
          <div class="me-auto">
            <div class="h5 m-0">{room['pname'][1]} <span class="badge bg-light text-dark">{room['score'][1]}</span>
              <span class="mx-2">-</span>
              <span class="badge bg-light text-dark">{room['score'][2]}</span> {room['pname'][2]}
            </div>
            <div class="text-muted small">先取 {room['target_points']}</div>
          </div>
          <div><span class="badge bg-primary">{room['pname'][room['turn']]} のターン</span></div>
        </div>
      </div>
    </div>

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
        <div class="mb-1"><span class="badge bg-secondary">名前</span> {myname}</div>
        <div class="mb-1"><span class="badge bg-secondary">自分の秘密の数</span> {room['secret'][pid]}</div>
        <div class="mb-1"><span class="badge bg-secondary">CT</span> {room['cooldown'][pid]}</div>
        <div class="mb-1"><span class="badge bg-secondary">ヒント在庫</span> {", ".join(room['available_hints'][pid]) if room['available_hints'][pid] else "なし"}</div>
        <div class="mb-1"><span class="badge bg-secondary">トラップ</span><br>
          <span class="small text-muted">A(kill): {", ".join(map(str, room['trap_kill'][pid])) if room['trap_kill'][pid] else "なし"}</span><br>
          <span class="small text-muted">B(info): {", ".join(map(str, room['trap_info'][pid])) if room['trap_info'][pid] else "なし"}</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">相手</div>
      <div class="card-body">
        <div class="mb-1"><span class="badge bg-secondary">名前</span> {oppname}</div>
        <div class="mb-1"><span class="badge bg-secondary">あなたに対する予想回数</span> {room['tries'][opp]}</div>
        <div class="mb-1"><span class="badge bg-secondary">ログ閲覧権（info）</span> {"有効" if room['can_view'][pid] else "なし"}</div>
        <div class="small text-muted">レンジ: {room['eff_num_min']}〜{room['eff_num_max']}</div>
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
    # 秘密の数を「再入力」できるよう、joinリンクへ誘導（安全）
    # （前ラウンドの値をそのままにしたい場合は、UI側で流用導線を作ることも可能）
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

def handle_guess(room, pid, guess):
    opp = 2 if pid == 1 else 1
    myname = room['pname'][pid]
    opponent_secret = room['secret'][opp]
    # 回数
    room['tries'][pid] += 1
    # まず「正解」優先
    if guess == opponent_secret:
        push_log(room, f"{myname} が g（予想）→ {guess}（正解！相手は即死）")
        room['score'][pid] += 1
        room['winner'] = pid
        return redirect(url_for('end_round', room_id=get_current_room_id()))
    # トラップ判定
    kill = set(room['trap_kill'][opp])
    info = set(room['trap_info'][opp])
    # ±1 即死（相手勝利）
    if any(abs(guess - k) <= 1 for k in kill):
        push_log(room, f"{myname} が g（予想）→ {guess}（killトラップ±1命中＝即敗北）")
        room['winner'] = opp
        return redirect(url_for('end_round', room_id=get_current_room_id()))
    # info（一致で発動）
    if guess in info:
        room['pending_view'][opp] = True
        room['view_cut_index'][opp] = len(room['actions'])
        push_log(room, f"{myname} が g（予想）→ {guess}（情報トラップ発動）")
    # ±5 次ターンスキップ
    if any(abs(guess - k) <= 5 for k in kill):
        room['skip_next_turn'][pid] = True
        push_log(room, f"{myname} が g（予想）→ {guess}（kill近接±5命中：次ターンスキップ）")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    # 通常ハズレ
    push_log(room, f"{myname} が g（予想）→ {guess}（ハズレ）")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_hint(room, pid, form):
    myname = room['pname'][pid]
    choose_type = False
    if room['hint_choice_available'][pid] and form.get('confirm_choice'):
        choose_type = True

    if choose_type:
        hint_type = form.get('hint_type')
        room['hint_choice_available'][pid] = False
    else:
        stock = room['available_hints'][pid]
        if not stock:
            push_log(room, "（このラウンドのヒントは出尽くしました）")
            switch_turn(room, pid)
            return redirect(url_for('play', room_id=get_current_room_id()))
        hint_type = random.choice(stock)
        stock.remove(hint_type)

    opp = 2 if pid == 1 else 1
    opp_secret = room['secret'][opp]
    hidden = room['hidden']
    if hint_type == '和':
        val = opp_secret + hidden
    elif hint_type == '差':
        val = abs(opp_secret - hidden)
    else:
        val = opp_secret * hidden
    push_log(room, f"{myname} が h（ヒント取得）{hint_type}＝{val}")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_change(room, pid, new_secret):
    myname = room['pname'][pid]
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

def handle_trap(room, pid, form):
    myname = room['pname'][pid]
    kind = form.get('trap_kind')
    eff_min, eff_max = room['eff_num_min'], room['eff_num_max']
    my_secret = room['secret'][pid]

    def valid_trap_val(v):
        if v is None: return False
        try:
            x = int(v)
        except:
            return False
        if not (eff_min <= x <= eff_max):
            return False
        if x == my_secret or (room['allow_negative'] and abs(x) == abs(my_secret)):
            return False
        return True

    if kind == 'k':
        v = form.get('trap_kill_value')
        if valid_trap_val(v):
            x = int(v)
            room['trap_kill'][pid].clear()
            room['trap_kill'][pid].append(x)
            push_log(room, f"{myname} が killトラップを {x} に設定")
        else:
            push_log(room, "⚠ 無効なkillトラップ値です。")
    elif kind == 'i':
        added = []
        for key in ('trap_info_value_0','trap_info_value_1','trap_info_value_2'):
            v = form.get(key)
            if valid_trap_val(v) and len(room['trap_info'][pid]) < 5:
                x = int(v)
                if x not in room['trap_info'][pid]:
                    room['trap_info'][pid].append(x)
                    added.append(x)
        if added:
            push_log(room, f"{myname} が infoトラップを {', '.join(map(str, added))} に設定")
        else:
            push_log(room, "⚠ infoトラップの追加はありません。")
    else:
        push_log(room, "⚠ 無効なトラップ種別です。")

    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

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
