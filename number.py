# app.py
from flask import Flask, request, redirect, url_for, render_template_string, session, abort
import random, string, os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "imigawakaranai")
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=True
)

# ====== 定数 ======
NUM_MIN = 1
NUM_MAX = 50
HIDDEN_MIN = 1
HIDDEN_MAX = 30

INFO_MAX_DEFAULT = 7

# 役割（ロール）一覧
ALL_ROLES = ['Scholar', 'Guardian', 'Trickster', 'Analyst', 'Trapper', 'Disarmer']

def has_role(room, pid, role_name):
    base = room.get('role', {}).get(pid)
    extra = room.get('extra_role', {}).get(pid)
    return base == role_name or extra == role_name

# ルール既定値（ON/OFF）
RULE_DEFAULTS = {
    'trap': True,
    'bluff': True,
    'guessflag': True,
    'decl1': True,
    'press': True,
    'roles': True,            # ロール機能
    'yn': True,               # Yes/No質問
    'dual_devotion': True,    # 二重職：献身
}

rooms = {}  # room_id -> dict(state)

# ====== ユーティリティ ======
def get_info_max(room, pid):
    """最終的な info 上限。宣言・ロール・献身ペナルティを反映。"""
    base = room.get('info_max', {}).get(pid, INFO_MAX_DEFAULT)
    roles = set([r for r in (room.get('role', {}).get(pid), room.get('extra_role', {}).get(pid)) if r])
    if 'Trapper' in roles:
        base += 3  # +3
    if room.get('devotion_penalty_active', {}).get(pid, False):
        base = max(0, base - 2)  # -2
    return base

def get_int(form, key, default=None, min_v=None, max_v=None):
    v = form.get(key)
    if v is None or v == '': return default
    try: x = int(v)
    except: return default
    if min_v is not None and x < min_v: return default
    if max_v is not None and x > max_v: return default
    return x

def push_and_back(room, pid, msg, to_play=True):
    if msg: push_log(room, msg)
    rid = get_current_room_id()
    return redirect(url_for('play', room_id=rid) if to_play else url_for('room_lobby', room_id=rid))

def gen_room_id():
    while True:
        rid = ''.join(random.choices(string.digits, k=4))
        if rid not in rooms: return rid

def eff_ranges(allow_negative: bool):
    if allow_negative:
        return -NUM_MAX, NUM_MAX, -HIDDEN_MAX, HIDDEN_MAX
    return NUM_MIN, NUM_MAX, HIDDEN_MIN, HIDDEN_MAX

def bootstrap_page(title, body_html):
    return render_template_string("""
<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{{title}}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
body{background:#0b1220;color:#f1f5f9}a,.btn-link{color:#93c5fd}a:hover,.btn-link:hover{color:#bfdbfe}
.card{background:#0f172a;border:1px solid #334155;--bs-card-cap-color:#f9a8d4;--bs-card-color:#f1f5f9}
.card-header{background:#0b1323;border-bottom:1px solid #334155;color:#f9a8d4!important;font-weight:700}
.card-title,.modal-title{color:#f9a8d4!important}.btn-primary{background:#2563eb;border-color:#1d4ed8}
.btn-primary:hover{background:#1d4ed8;border-color:#1e40af}.btn-outline-light{color:#f1f5f9;border-color:#94a3b8}
.btn-outline-light:hover{color:#0b1220;background:#e2e8f0;border-color:#e2e8f0}.badge{font-size:.9rem}
.badge.bg-secondary{background:#f472b6!important;color:#0b1220!important;border:1px solid #fda4af!important}
.form-control,.form-select{background:#0b1323;color:#f1f5f9;border-color:#475569}
.form-control::placeholder{color:#e9c5d9;opacity:1}.form-control:focus,.form-select:focus{border-color:#93c5fd;box-shadow:none}
.text-muted,.small.text-muted,.form-label,.form-check-label,.small,.text-warning{color:#e6f0ff!important}
.log-box{max-height:40vh;overflow:auto;background:#0b1323;color:#e2e8f0;padding:1rem;border:1px solid #334155;border-radius:.5rem}
.value{color:#f9a8d4;font-weight:600}
</style></head><body><div class="container py-4">
<div class="d-flex justify-content-between align-items-center mb-3">
  <h1 class="h4 m-0">やまやまやま</h1>
  <div class="d-flex gap-2">
    <button type="button" class="btn btn-sm btn-outline-light" data-bs-toggle="modal" data-bs-target="#rulesModal">ルール</button>
    <a class="btn btn-sm btn-outline-light" href="{{ url_for('index') }}">ホームへ</a>
  </div>
</div>
{{ body|safe }}
<div class="modal fade" id="rulesModal" tabindex="-1" aria-hidden="true"><div class="modal-dialog modal-lg modal-dialog-scrollable">
<div class="modal-content" style="background:#0f172a;color:#f1f5f9;border:1px solid #334155;">
  <div class="modal-header"><h5 class="modal-title">ルール説明</h5>
    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button></div>
  <div class="modal-body">
    <p class="mb-2">※ ルーム作成時のトグルで<strong>各機能をON/OFF</strong>できます。</p>
    <div class="p-3 rounded border border-secondary mb-3">
      <h6 class="mb-2">基本ルール</h6>
      <ul class="mb-0">
        <li>各プレイヤーは自分だけが知る「秘密の数」を選びます（通常は <code>{{ NUM_MIN }}</code>〜<code>{{ NUM_MAX }}</code>。負の数ON時は±範囲）。</li>
        <li>各ラウンドごとに誰にも知られない「隠し数」が自動で決まります（<code>{{ HIDDEN_MIN }}</code>〜<code>{{ HIDDEN_MAX }}</code>）。</li>
        <li>自分のターンに「予想」「ヒント」「トラップ設置」などの行動を選びます。相手の秘密の数を当てればラウンド勝利。</li>
      </ul>
    </div>
    <ol class="mb-3">
      <li class="mb-2"><strong>勝利条件</strong>：相手の秘密の数字を当てるとラウンド勝利。先取到達でマッチ勝利。</li>
      <li class="mb-2"><strong>ヒント</strong>：和/差/積から1つが得られます。後攻のみ各ラウンド1回、種類指定可。<br>
        <em>Scholar</em> はこのラウンド中ずっと種類指定可。Tricksterが相手にいる場合、あなたが得る実際の表示値は常に ±1 ずれます（ブラフ判定とは無関係）。</li>
      <li class="mb-2"><strong>トラップ</strong>（ON）：
        <ul>
          <li><strong>kill</strong>：±1命中で即死、±5命中で次ターンスキップ（設置はターン消費／上書き1個）。</li>
          <li><strong>info</strong>：踏まれると、<em>その時点以降</em>の相手行動ログを閲覧可。通常は同時最大7個・1ターンに無料1個設置。チェックで3個まとめて（ターン消費）。</li>
        </ul>
      </li>
      <li class="mb-2"><strong>ブラフヒント</strong>（ON）：相手の次回ヒント時に偽の値を提示。「信じる／ブラフだ！」で分岐。指摘成功で本物ヒント×2、失敗で以後ヒント取得後にCT付与。<em>Trickster</em>相手に失敗するとCTは<strong>2</strong>。</li>
      <li class="mb-2"><strong>ゲスフラグ</strong>（ON）：次の相手ターンに予想したら即死（各ラウンド1回）。</li>
      <li class="mb-2"><strong>一の位 宣言</strong>（ON）：各ラウンド1回、0〜9を宣言（ターン消費なし）。嘘だ！成功で正しい一の位公開＋直後に無料予想、失敗で次ターンスキップ。宣言者はこのラウンド中、無料infoが1ターン2個・上限10。</li>
      <li class="mb-2"><strong>サドン・プレス</strong>（ON）：ハズレ直後に同ターンでもう1回だけ連続予想（当たれば勝利、外せば次ターンスキップ）。各ラウンド1回。</li>
      <li class="mb-2"><strong>自分の数の変更</strong>：ラウンド2回まで。使用すると自分にCT7、相手のヒント在庫リセット。宣言効果はリセット。</li>
      <li class="mb-2"><strong>役割カード（ロール）</strong>（ON）：各ラウンド開始時にランダムで各自に1枚（相手非公開）。
        <ul>
          <li><em>Scholar</em>：そのラウンド中ずっとヒント種類を指定可。</li>
          <li><em>Guardian</em>：そのラウンド中、あなたへの「次ターンスキップ」効果を<strong>一度だけ</strong>自動無効化。</li>
          <li><em>Trickster</em>：相手が「ブラフだ！」失敗時、以後のヒントCTが<strong>2</strong>。さらに相手が受け取る本物ヒントは常に±1の誤差で表示。</li>
          <li><em>Analyst</em>：Yes/No質問がターン消費なしで<strong>各ラウンド3回</strong>、同一ターン内連続不可、クールタイム2ターン。</li>
          <li><em>Trapper</em>：info上限 +3（宣言の+10と合算、最大13）。</li>
          <li><em>Disarmer</em>：各ラウンド1回、自分のターン開始時に相手のinfoトラップを1つ自動解除。</li>
        </ul>
      </li>
      <li class="mb-2"><strong>Yes/No質問</strong>（ON）：ターン消費なし。偶奇（奇数/偶数）は質問不可。既定は<strong>ラウンドに1回</strong>まで。<br>
        形式：<code>≥X ?</code>、<code>≤X ?</code>、<code>[A,B]内？</code>（いずれも相手の秘密の数に対して）。</li>
      <li class="mb-2"><strong>二重職：献身</strong>（ON・各ラウンド1回）：候補3枚から重複しない追加ロールを1つ取得（このラウンドのみ有効）。<br>
        代償：今ターン終了、さらに <code>guess_ct=1</code> & <code>hint_ct=1</code> を付与。加えてこのラウンド中、あなたの <em>info</em> 上限は<strong>-2</strong>。</li>
    </ol>
    <p class="small text-warning">ログの詳細表示は、infoトラップで閲覧権が付与された場合のみ（発動時以降）。ロール名は相手には公開されません。</p>
  </div>
  <div class="modal-footer"><button type="button" class="btn btn-primary" data-bs-dismiss="modal">閉じる</button></div>
</div></div></div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</div></body></html>
""", title=title, body=body_html, NUM_MIN=NUM_MIN, NUM_MAX=NUM_MAX, HIDDEN_MIN=HIDDEN_MIN, HIDDEN_MAX=HIDDEN_MAX)

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
        'turn': 1,
        'pname': {1: None, 2: None},
        'secret': {1: None, 2: None},
        'hidden': None,
        'tries': {1:0, 2:0},
        'available_hints': {1: ['和','差','積'], 2: ['和','差','積']},
        'hint_choice_available': {1: False, 2: True},
        'cooldown': {1:0, 2:0},
        'change_used': {1:0, 2:0},
        'trap_kill': {1: [], 2: []},
        'trap_info': {1: [], 2: []},
        'pending_view': {1: False, 2: False},
        'can_view': {1: False, 2: False},
        'view_cut_index': {1: None, 2: None},
        'skip_next_turn': {1: False, 2: False},
        'info_set_this_turn': {1: False, 2: False},
        'info_max': {1: INFO_MAX_DEFAULT, 2: INFO_MAX_DEFAULT},
        'info_free_per_turn': {1: 1, 2: 1},
        'info_free_used_this_turn': {1: 0, 2: 0},
        'actions': [],
        'winner': None,
        'phase': 'lobby',
        'starter': 1,
        'rules': rules,

        # ブラフ
        'bluff': {1: None, 2: None},
        'hint_penalty_active': {1: False, 2: False},
        'hint_penalty_ct_value': {1: 1, 2: 1},  # Trickster相手で2になる
        'hint_ct': {1: 0, 2: 0},

        # ゲスフラグ
        'guess_flag_armed': {1: False, 2: False},
        'guess_flag_ct': {1: 0, 2: 0},
        'guess_penalty_active': {1: False, 2: False},
        'guess_ct': {1: 0, 2: 0},
        'guess_flag_warn': {1: False, 2: False},
        'guess_flag_used': {1: False, 2: False},

        # 一の位
        'decl1_value': {1: None, 2: None},
        'decl1_used': {1: False, 2: False},
        'decl1_resolved': {1: True, 2: True},
        'decl1_hint_token_ready': {1: False, 2: False},
        'decl1_hint_token_active': {1: False, 2: False},
        'free_guess_pending': {1: False, 2: False},

        # サドン・プレス
        'press_used': {1: False, 2: False},
        'press_pending': {1: False, 2: False},

        'skip_suppress_pid': None,

        # ロール／献身
        'role': {1: None, 2: None},
        'extra_role': {1: None, 2: None},
        'dual_used': {1: False, 2: False},
        'dual_candidates': {1: [], 2: []},
        'devotion_penalty_active': {1: False, 2: False},
        'guardian_shield_used': {1: False, 2: False},
        'disarm_used': {1: False, 2: False},

        # Yes/No
        'yn_used_this_turn': {1: False, 2: False},
        'yn_used_count': {1: 0, 2: 0},
        'yn_ct': {1: 0, 2: 0},
    }

def room_or_404(rid):
    room = rooms.get(rid)
    if not room: abort(404)
    return room

def player_guard(rid, pid):
    room = room_or_404(rid)
    if pid not in (1,2): abort(404)
    return room

def push_log(room, s):
    room['actions'].append(s)

def apply_skip(room, pid, note_suffix=""):
    """次ターンスキップを付与。ただしGuardianが未使用なら1回だけ無効化。"""
    # 既にスキップ予定ならそのまま
    if room['skip_next_turn'][pid]:
        return True
    # Guardianなら1回だけ無効化
    if has_role(room, pid, 'Guardian') and not room['guardian_shield_used'][pid]:
        room['guardian_shield_used'][pid] = True
        push_log(room, f"{room['pname'][pid]} への通知: 次ターンスキップは無効化された（1回限り）{note_suffix}")
        return False
    room['skip_next_turn'][pid] = True
    return True

def switch_turn(room, cur_pid):
    for p in (1,2):
        if room['cooldown'][p] > 0: room['cooldown'][p] -= 1
        if room['hint_ct'][p] > 0: room['hint_ct'][p] -= 1
        if room['guess_ct'][p] > 0: room['guess_ct'][p] -= 1
        if room['guess_flag_ct'][p] > 0: room['guess_flag_ct'][p] -= 1
        if room['yn_ct'][p] > 0: room['yn_ct'][p] -= 1

    opp = 2 if cur_pid == 1 else 1
    if room['pending_view'][opp]:
        room['can_view'][opp] = True
        room['pending_view'][opp] = False

    room['turn'] = opp
    room['info_free_used_this_turn'][opp] = 0
    room['yn_used_this_turn'][opp] = False
    room['skip_suppress_pid'] = None

    if room['rules'].get('guessflag', True):
        gf_owner = 2 if cur_pid == 1 else 1
        if room['guess_flag_armed'][gf_owner]:
            room['guess_flag_armed'][gf_owner] = False
            room['guess_flag_warn'][cur_pid] = True

# ====== ルーティング ======
@app.route('/')
def index():
    body = f"""
<div class="row g-3">
  <div class="col-12 col-lg-6"><div class="card"><div class="card-header">ルーム作成</div><div class="card-body">
    <form method="post" action="/create_room">
      <div class="mb-3">
        <label class="form-label">負の数を許可</label>
        <select class="form-select" name="allow_negative">
          <option value="n">しない</option><option value="y">する</option>
        </select>
      </div>
      <div class="mb-3">
        <label class="form-label">先取ポイント</label>
        <input type="number" class="form-control" name="target_points" min="1" value="3">
      </div>
      <hr class="my-3">
      <div class="mb-2"><span class="badge bg-secondary">ルールトグル</span></div>
      <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_trap" name="rule_trap" checked>
        <label class="form-check-label" for="rule_trap">トラップ（kill / info）</label></div>
      <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_bluff" name="rule_bluff" checked>
        <label class="form-check-label" for="rule_bluff">ブラフヒント</label></div>
      <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_guessflag" name="rule_guessflag" checked>
        <label class="form-check-label" for="rule_guessflag">ゲスフラグ</label></div>
      <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_decl1" name="rule_decl1" checked>
        <label class="form-check-label" for="rule_decl1">一の位の宣言＆嘘だ！コール</label></div>
      <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_press" name="rule_press" checked>
        <label class="form-check-label" for="rule_press">サドン・プレス</label></div>
      <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_roles" name="rule_roles" checked>
        <label class="form-check-label" for="rule_roles">役割カード（ロール）</label></div>
      <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_yn" name="rule_yn" checked>
        <label class="form-check-label" for="rule_yn">Yes/No 質問</label></div>
      <div class="form-check mb-3"><input class="form-check-input" type="checkbox" id="rule_dual" name="rule_dual" checked>
        <label class="form-check-label" for="rule_dual">二重職：献身（追加ロール獲得）</label></div>
      <button class="btn btn-primary w-100">ルームを作成</button>
    </form>
  </div></div></div>

  <div class="col-12 col-lg-6"><div class="card"><div class="card-header">ルームに参加</div><div class="card-body">
    <form method="get" action="/room">
      <div class="mb-3">
        <label class="form-label">ルームID（4桁）</label>
        <input class="form-control" name="room_id" inputmode="numeric" pattern="\\d{{4}}" placeholder="1234" required>
      </div>
      <button class="btn btn-outline-light w-100">ロビーへ</button>
    </form>
  </div></div></div>
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
        'roles': bool(request.form.get('rule_roles')),
        'yn': bool(request.form.get('rule_yn')),
        'dual_devotion': bool(request.form.get('rule_dual')),
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
<div class="card mb-3"><div class="card-header">ルーム {room_id}</div><div class="card-body">
  <div class="p-3 rounded border border-secondary mb-3">
    <div class="small text-warning">ルーム番号</div>
    <div class="h1 m-0 value">{room_id}</div>
    <div class="small">相手は「ホーム → ルームに参加」でこの番号を入力してください。</div>
  </div>
  <p class="mb-2">URLを共有したい場合はこちらを送ってください。</p>
  <div class="row g-2">
    <div class="col-12 col-md-6"><div class="p-2 rounded border border-secondary">
      <div class="small text-warning mb-1">プレイヤー1用リンク</div>
      <a href="{l1}">{l1}</a>
      <div class="mt-1"><span class="badge bg-secondary">状態</span> {p1}</div>
    </div></div>
    <div class="col-12 col-md-6"><div class="p-2 rounded border border-secondary">
      <div class="small text-warning mb-1">プレイヤー2用リンク</div>
      <a href="{l2}">{l2}</a>
      <div class="mt-1"><span class="badge bg-secondary">状態</span> {p2}</div>
    </div></div>
  </div>
  <hr/><a class="btn btn-outline-light" href="{url_for('index')}">ホームへ</a>
</div></div>
"""
    return bootstrap_page(f"ロビー {room_id}", body)

@app.route('/join/<room_id>/<int:player_id>', methods=['GET','POST'])
def join(room_id, player_id):
    room = player_guard(room_id, player_id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip() or f'プレイヤー{player_id}'
        secret = int(request.form.get('secret'))
        if not (room['eff_num_min'] <= secret <= room['eff_num_max']):
            err = f"{room['eff_num_min']}〜{room['eff_num_max']}の整数で入力してください。"
            return join_form(room_id, player_id, err)
        room['pname'][player_id] = name
        room['secret'][player_id] = secret
        session['room_id'] = room_id
        session['player_id'] = player_id
        if room['pname'][1] and room['pname'][2]:
            start_new_round(room)
        return redirect(url_for('play', room_id=room_id) + f"?as={player_id}")
    return join_form(room_id, player_id)

def join_form(room_id, player_id, error=None):
    room = rooms[room_id]
    body = f"""
<div class="card"><div class="card-header">ルーム {room_id} に プレイヤー{player_id} として参加</div>
<div class="card-body">
  {"<div class='alert alert-danger'>" + error + "</div>" if error else ""}
  <form method="post">
    <div class="mb-3"><label class="form-label">ニックネーム</label>
      <input class="form-control" name="name" placeholder="プレイヤー{player_id}"></div>
    <div class="mb-3"><label class="form-label">秘密の数字 ({room['eff_num_min']}〜{room['eff_num_max']})</label>
      <input class="form-control" type="number" name="secret"
        required min="{room['eff_num_min']}" max="{room['eff_num_max']}"
        placeholder="{room['eff_num_min']}〜{room['eff_num_max']}"></div>
    <button class="btn btn-primary w-100">参加</button>
  </form>
</div></div>
"""
    return bootstrap_page("参加", body)

def start_new_round(room):
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
    room['change_used'] = {1: 0, 2: 0}
    room['available_hints'] = {1: ['和','差','積'], 2: ['和','差','積']}
    room['bluff'] = {1: None, 2: None}
    room['hint_penalty_active'] = {1: False, 2: False}
    room['hint_penalty_ct_value'] = {1: 1, 2: 1}
    room['hint_ct'] = {1: 0, 2: 0}
    room['guess_flag_armed'] = {1: False, 2: False}
    room['guess_flag_ct'] = {1: 0, 2: 0}
    room['guess_penalty_active'] = {1: False, 2: False}
    room['guess_ct'] = {1: 0, 2: 0}
    room['guess_flag_warn'] = {1: False, 2: False}
    room['guess_flag_used'] = {1: False, 2: False}
    room['decl1_value'] = {1: None, 2: None}
    room['decl1_used'] = {1: False, 2: False}
    room['decl1_resolved'] = {1: True, 2: True}
    room['decl1_hint_token_ready'] = {1: False, 2: False}
    room['decl1_hint_token_active'] = {1: False, 2: False}
    room['free_guess_pending'] = {1: False, 2: False}
    room['press_used'] = {1: False, 2: False}
    room['press_pending'] = {1: False, 2: False}
    room['skip_suppress_pid'] = None

    # ロール系
    room['extra_role'] = {1: None, 2: None}
    room['dual_used'] = {1: False, 2: False}
    room['dual_candidates'] = {1: [], 2: []}
    room['devotion_penalty_active'] = {1: False, 2: False}
    room['guardian_shield_used'] = {1: False, 2: False}
    room['disarm_used'] = {1: False, 2: False}

    # Yes/No
    room['yn_used_this_turn'] = {1: False, 2: False}
    room['yn_used_count'] = {1: 0, 2: 0}
    room['yn_ct'] = {1: 0, 2: 0}

    # 先手/後手のヒント指定フラグ
    if room['starter'] == 1:
        room['hint_choice_available'] = {1: False, 2: True}
        room['turn'] = 1
    else:
        room['hint_choice_available'] = {1: True, 2: False}
        room['turn'] = 2

    # ランダムロール配布（ON時）
    if room['rules'].get('roles', True):
        room['role'][1] = random.choice(ALL_ROLES)
        room['role'][2] = random.choice(ALL_ROLES)
        # 自分だけに見える通知
        push_log(room, f"{room['pname'][1]} への通知: 今ラウンドのロールは {room['role'][1]}")
        push_log(room, f"{room['pname'][2]} への通知: 今ラウンドのロールは {room['role'][2]}")
    else:
        room['role'][1] = None
        room['role'][2] = None

    room['winner'] = None
    room['phase'] = 'play'

@app.route('/play/<room_id>', methods=['GET','POST'])
def play(room_id):
    room = room_or_404(room_id)
    as_pid = request.args.get('as')
    if as_pid in ('1','2'):
        session['room_id'] = room_id
        session['player_id'] = int(as_pid)
    pid = session.get('player_id')
    rid = session.get('room_id')
    if rid != room_id or pid not in (1,2):
        return redirect(url_for('room_lobby', room_id=room_id))
    if not (room['pname'][1] and room['pname'][2]):
        l1 = url_for('join', room_id=room_id, player_id=1, _external=True)
        l2 = url_for('join', room_id=room_id, player_id=2, _external=True)
        p1 = room['pname'][1] or '未参加'
        p2 = room['pname'][2] or '未参加'
        opp = 2 if pid == 1 else 1
        wait_body = f"""
<div class="card mb-3"><div class="card-header">相手を待っています…</div><div class="card-body">
  <div class="p-3 rounded border border-secondary mb-3">
    <div class="small text-warning">ルーム番号</div>
    <div class="h1 m-0 value">{room_id}</div>
    <div class="small">相手は「ホーム → ルームに参加」でこの番号を入力できます。</div>
  </div>
  <div class="alert alert-info">あなたは <span class="value">プレイヤー{pid}</span> として参加済みです。相手が参加すると自動で開始します。</div>
  <p class="mb-2">相手に送るべきリンクは <span class="value">プレイヤー{opp}用リンク</span> です。</p>
  <div class="row g-2">
    <div class="col-12 col-md-6"><div class="p-2 rounded border border-secondary">
      <div class="small text-warning mb-1">プレイヤー1用リンク</div><a href="{l1}">{l1}</a>
      <div class="mt-1"><span class="badge bg-secondary">状態</span> {p1}</div></div></div>
    <div class="col-12 col-md-6"><div class="p-2 rounded border border-secondary">
      <div class="small text-warning mb-1">プレイヤー2用リンク</div><a href="{l2}">{l2}</a>
      <div class="mt-1"><span class="badge bg-secondary">状態</span> {p2}</div></div></div>
  </div>
  <div class="mt-3 d-flex gap-2">
    <a class="btn btn-primary" href="{url_for('play', room_id=room_id)}">更新</a>
    <a class="btn btn-outline-light" href="{url_for('room_lobby', room_id=room_id)}">ロビーへ</a>
  </div>
</div></div>"""
        return bootstrap_page("相手待ち", wait_body)

    if room['winner'] is not None:
        return redirect(url_for('end_round', room_id=room_id))

    # スキップ（無料予想直後の抑制に注意）
    if room['skip_next_turn'][room['turn']] and room.get('skip_suppress_pid') != room['turn']:
        room['skip_next_turn'][room['turn']] = False
        push_log(room, f"{room['pname'][room['turn']]} のターンはスキップされた")
        cur = room['turn']
        switch_turn(room, cur)
        return redirect(url_for('play', room_id=room_id))

    # POST アクション
    if request.method == 'POST':
        if room['turn'] != pid:
            return redirect(url_for('play', room_id=room_id))
        try:
            action = request.form.get('action')
            if action == 'g':
                guess_val = get_int(request.form, 'guess', None, room['eff_num_min'], room['eff_num_max'])
                if guess_val is None: return push_and_back(room, pid, "⚠ 予想値が不正です。")
                return handle_guess(room, pid, guess_val)
            elif action == 'h':
                return handle_hint(room, pid, request.form)
            elif action == 'c':
                new_secret = get_int(request.form, 'new_secret', None, room['eff_num_min'], room['eff_num_max'])
                if new_secret is None: return push_and_back(room, pid, "⚠ 変更する数が不正です。")
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
                press_val = get_int(request.form, 'press_guess', None, room['eff_num_min'], room['eff_num_max'])
                if press_val is None: return push_and_back(room, pid, "⚠ サドン・プレスの値が不正です。")
                return handle_press(room, pid, press_val)
            elif action == 'press_skip':
                return handle_press_skip(room, pid)
            elif action == 'free_guess':
                fg_val = get_int(request.form, 'free_guess', None, room['eff_num_min'], room['eff_num_max'])
                if fg_val is None: return push_and_back(room, pid, "⚠ 無料予想の値が不正です。")
                return handle_free_guess(room, pid, fg_val)
            elif action == 'dual_devotion':
                return handle_dual_devotion(room, pid, request.form)
            elif action == 'yn':
                return handle_yn(room, pid, request.form)
            else:
                return push_and_back(room, pid, "⚠ 不明なアクションです。")
        except Exception:
            app.logger.exception("POST処理中の例外")
            return redirect(url_for('index'))

    # 表示用
    p1, p2 = room['pname'][1], room['pname'][2]
    myname = room['pname'][pid]
    opp = 2 if pid == 1 else 1
    oppname = room['pname'][opp]

    # 解除士：ターン開始時に1回だけ相手のinfoを解除
    if room['turn'] == pid and room['rules'].get('roles', True) and has_role(room, pid, 'Disarmer') and (not room['disarm_used'][pid]):
        if room['trap_info'][opp]:
            v = random.choice(room['trap_info'][opp])
            room['trap_info'][opp].remove(v)
            room['disarm_used'][pid] = True
            push_log(room, f"{myname} への通知: あなたの能力で相手のinfoトラップ {v} を解除した")

    change_used = room.get('change_used', {}).get(pid, 0)
    hint_available = True

    if request.method == 'GET' and room['turn'] == pid and room.get('guess_flag_warn', {}).get(pid):
        other = 2 if pid == 1 else 1
        push_log(room, f"{room['pname'][pid]} への通知: 実は前のターンに {room['pname'][other]} がゲスフラグを立てていた。危なかった！")
        room['guess_flag_warn'][pid] = False

    # ログのフィルタ
    filtered = []
    cut = room['view_cut_index'][pid]
    for idx, entry in enumerate(room['actions']):
        if entry.startswith(f"{myname} "):
            filtered.append(entry); continue
        if entry.startswith(f"{oppname} が g（予想）→"):
            filtered.append(entry); continue
        if room['can_view'][pid] and (cut is None or idx >= cut) and entry.startswith(f"{oppname} "):
            filtered.append(entry); continue
    log_html = "".join(f"<li>{e}</li>" for e in filtered)

    # 自分の番UI
    my_turn_block = ""
    ru = room['rules']
    # 役割表示（自分だけ）
    base_role = room.get('role', {}).get(pid)
    extra_role = room.get('extra_role', {}).get(pid)
    role_line = "なし"
    if base_role and extra_role: role_line = f"{base_role} ＋ {extra_role}（二重）"
    elif base_role: role_line = base_role
    elif extra_role: role_line = f"{extra_role}（二重）"

    if room['turn'] == pid:
        if room['free_guess_pending'][pid] and ru.get('decl1', True):
            my_turn_block = f"""
<div class="card mb-3"><div class="card-header">無料予想（嘘だ！成功）</div><div class="card-body">
  <form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="free_guess">
    <label class="form-label">もう一度だけ無料で予想できます</label>
    <input class="form-control mb-2" name="free_guess" type="number" required min="{room['eff_num_min']}" max="{room['eff_num_max']}" placeholder="{room['eff_num_min']}〜{room['eff_num_max']}">
    <button class="btn btn-primary w-100">予想を送る</button>
    <div class="small text-warning mt-1">※ トラップは有効。ラウンド終了を除き、予想後もあなたのターンは続きます。ゲスフラグは発動しません。</div>
  </form></div></div>"""
        elif room['press_pending'][pid] and ru.get('press', True):
            my_turn_block = f"""
<div class="card mb-3"><div class="card-header">サドン・プレス</div><div class="card-body">
  <form method="post" class="p-2 border rounded mb-2">
    <input type="hidden" name="action" value="press">
    <label class="form-label">もう一回だけ連続で予想できます</label>
    <input class="form-control mb-2" name="press_guess" type="number" required min="{room['eff_num_min']}" max="{room['eff_num_max']}">
    <button class="btn btn-primary w-100">もう一回だけ予想！</button>
    <div class="small text-warning mt-1">※ 当たれば勝利。外すと次ターンスキップ。</div>
  </form>
  <form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="press_skip">
    <label class="form-label">今回はサドン・プレスを使わない</label>
    <button class="btn btn-outline-light w-100">使わないで交代する</button>
  </form></div></div>"""
        else:
            choose_allowed = room['hint_choice_available'][pid] or (ru.get('roles', True) and has_role(room, pid, 'Scholar'))

            trap_block = ""
            if ru.get('trap', True):
                trap_block = f"""
  <div class="col-12 col-md-6"><form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="t">
    <label class="form-label">トラップ（入力した項目だけ設定）</label>
    <div class="mb-2">
      <input class="form-control mb-2" name="trap_kill_value" type="number" placeholder="killは1つだけ（上書き・ターン消費）">
      <div class="small text-warning">infoは通常 最大7個（宣言後は10個、Trapperで+3、献身で-2）。<br>無料：1ターン1個（宣言中は2個）。チェックで3個まとめ置き（ターン消費）。</div>
      <input class="form-control mb-2" name="trap_info_value" type="number" placeholder="info(1)">
      <input class="form-control mb-2" name="trap_info_value_1" type="number" placeholder="info(2)">
      <input class="form-control mb-2" name="trap_info_value_2" type="number" placeholder="info(3)">
      <div class="form-check"><input class="form-check-input" type="checkbox" name="info_bulk" value="1" id="info_bulk">
        <label class="form-check-label" for="info_bulk">infoを3つまとめて置く（ターン消費）</label></div>
    </div><button class="btn btn-outline-light w-100">設定する</button>
  </form></div>"""

            bluff_block = ""
            if ru.get('bluff', True):
                bluff_block = f"""
  <div class="col-12 col-md-6"><form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="bh">
    <label class="form-label">ブラフヒントを仕掛ける</label>
    <div class="mb-2">
      <select class="form-select mb-2" name="bluff_type"><option>和</option><option>差</option><option>積</option></select>
      <input class="form-control" type="number" name="bluff_value" placeholder="相手に見せる数値（必須）" required>
    </div><button class="btn btn-outline-light w-100">ブラフを設定（ターン消費）</button>
  </form></div>"""

            gf_block = ""
            if ru.get('guessflag', True):
                gf_block = f"""
  <div class="col-12 col-md-6"><form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="gf">
    <label class="form-label">ゲスフラグを立てる</label>
    <div class="small text-warning mb-2">次の相手ターンに予想してきたら相手は即死（各ラウンド1回）</div>
    <button class="btn btn-outline-light w-100" {"disabled" if room['guess_flag_used'][pid] else ""}>立てる</button>
    <div class="small text-warning mt-1">{ "（このラウンドは既に使用しました）" if room['guess_flag_used'][pid] else "" }</div>
  </form></div>"""

            decl_block = ""
            if ru.get('decl1', True):
                decl_block = f"""
  <div class="col-12 col-md-6"><form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="decl1">
    <label class="form-label">一の位を宣言（0〜9）</label>
    <input class="form-control mb-2" name="decl1_digit" type="number" min="0" max="9" {"required" if not room['decl1_used'][pid] else "disabled"} placeholder="0〜9">
    <button class="btn btn-outline-light w-100" {"disabled" if room['decl1_used'][pid] else ""}>宣言（ターン消費なし）</button>
    <div class="small text-warning mt-1">{ "（このラウンドは既に宣言済み）" if room['decl1_used'][pid] else "宣言すると、このラウンド中は無料infoが1ターン2個・上限10。" }</div>
  </form></div>"""

            decl_challenge_block = f"""
  <div class="col-12 col-md-6"><form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="decl1_challenge">
    <label class="form-label">相手の「一の位」宣言にチャレンジ</label>
    <button class="btn btn-outline-light w-100">嘘だ！コール</button>
    <div class="small text-warning mt-1">嘘なら正しい一の位公開＋直後に無料予想。真ならあなたは次ターンスキップ。</div>
  </form></div>""" if (ru.get('decl1', True) and (room['decl1_value'][opp] is not None and not room['decl1_resolved'][opp])) else ""

            # 二重職：献身
            dual_block = ""
            if ru.get('dual_devotion', True) and (not room['dual_used'][pid]) and ru.get('roles', True):
                dual_block = f"""
  <div class="col-12 col-md-6"><form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="dual_devotion">
    <label class="form-label">二重職：献身（候補3から追加ロールを獲得）</label>
    <button class="btn btn-outline-light w-100">候補を表示 → 選択</button>
    <div class="small text-warning mt-1">選ぶと今ターン終了／guess_ct=1 & hint_ct=1／このラウンドのinfo上限 -2（Trapperの+3と合算）。</div>
  </form></div>"""

            # Yes/No 質問（ターン消費なし）
            yn_left = (3 if (ru.get('roles', True) and has_role(room, pid, 'Analyst')) else 1) - room['yn_used_count'][pid]
            yn_block = ""
            if ru.get('yn', True):
                yn_block = f"""
  <div class="col-12 col-md-6"><form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="yn">
    <label class="form-label">Yes/No質問（ターン消費なし）</label>
    <select class="form-select mb-2" name="yn_type">
      <option value="ge">相手の数 ≥ X ?</option>
      <option value="le">相手の数 ≤ X ?</option>
      <option value="range">相手の数は [A,B] 内？</option>
    </select>
    <div class="row g-2 mb-2">
      <div class="col"><input class="form-control" name="x" type="number" placeholder="X"></div>
      <div class="col"><input class="form-control" name="a" type="number" placeholder="A（range用）"></div>
      <div class="col"><input class="form-control" name="b" type="number" placeholder="B（range用）"></div>
    </div>
    <button class="btn btn-outline-light w-100" {"disabled" if room['yn_ct'][pid]>0 or room['yn_used_this_turn'][pid] or yn_left<=0 else ""}>質問を送る</button>
    <div class="small text-warning mt-1">残り：{max(0,yn_left)} ／ CT: {room['yn_ct'][pid]} ／ 同一ターン連続不可。偶奇は質問不可。</div>
  </form></div>"""

            my_turn_block = f"""
<div class="card mb-3"><div class="card-header">アクション</div><div class="card-body"><div class="row g-2">
  <div class="col-12 col-md-6"><form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="g">
    <label class="form-label">相手の数字を予想</label>
    <input class="form-control mb-2" name="guess" type="number" required min="{room['eff_num_min']}" max="{room['eff_num_max']}" placeholder="{room['eff_num_min']}〜{room['eff_num_max']}">
    <button class="btn btn-primary w-100" {"disabled" if room['guess_ct'][pid] > 0 else ""}>予想する</button>
    <div class="small text-warning mt-1">{ "（予想はクールタイム中）" if room['guess_ct'][pid] > 0 else "" }</div>
  </form></div>

  <div class="col-12 col-md-6"><form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="h">
    <div class="mb-2"><label class="form-label">ヒント</label>
      { "<div class='mb-2'><label class='form-label'>種類を指定</label><select class='form-select' name='hint_type'><option>和</option><option>差</option><option>積</option></select><input type='hidden' name='confirm_choice' value='1'></div>" if choose_allowed else "<div class='small text-warning mb-2'>(このターンは種類指定不可。ランダム)</div>" }
    </div>
    <button class="btn btn-outline-light w-100" {"disabled" if room['hint_ct'][pid] > 0 else ""}>ヒントをもらう</button>
    <div class="small text-warning mt-1">{ "（ヒントはクールタイム中）" if room['hint_ct'][pid] > 0 else "" }</div>
  </form></div>

  <div class="col-12 col-md-6"><form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="c">
    <label class="form-label">自分の数を変更</label>
    <input class="form-control mb-2" name="new_secret" type="number" required min="{room['eff_num_min']}" max="{room['eff_num_max']}">
    <button class="btn btn-outline-light w-100" {"disabled" if (room['cooldown'][pid] > 0 or change_used >= 2) else ""}>変更する（CT7・ラウンド2回まで）</button>
    <div class="small text-warning mt-1">このラウンドの使用回数：<span class="value">{change_used}</span>/2 {" ／（クールタイム中）" if room['cooldown'][pid] > 0 else "" }</div>
  </form></div>

  {trap_block}{bluff_block}{gf_block}{decl_block}{decl_challenge_block}{dual_block}{yn_block}
</div></div></div>
"""

    # 右側パネル等
    body = f"""
<div class="row g-3">
  <div class="col-12 col-lg-8">
    {my_turn_block}
    <div class="card"><div class="card-header">アクション履歴</div><div class="card-body">
      <div class="log-box"><ol class="mb-0">{log_html}</ol></div>
    </div></div>
  </div>

  <div class="col-12 col-lg-4">
    <div class="card mb-3"><div class="card-header">あなた</div><div class="card-body">
      <div class="mb-1"><span class="badge bg-secondary">名前</span> <span class="value">{myname}</span></div>
      <div class="mb-1"><span class="badge bg-secondary">ロール</span> <span class="value">{role_line}</span></div>
      <div class="mb-1"><span class="badge bg-secondary">自分の秘密の数</span> <span class="value">{room['secret'][pid]}</span></div>
      <div class="mb-1"><span class="badge bg-secondary">CT</span> c:<span class="value">{room['cooldown'][pid]}</span> / h:<span class="value">{room['hint_ct'][pid]}</span> / g:<span class="value">{room['guess_ct'][pid]}</span> / yn:<span class="value">{room['yn_ct'][pid]}</span></div>
      <div class="mb-1"><span class="badge bg-secondary">トラップ</span><br>
      {("<span class='small text-warning'>A(kill): <span class='value'>" + (", ".join(map(str, room['trap_kill'][pid])) if room['trap_kill'][pid] else "なし") + "</span></span><br><span class='small text-warning'>B(info): <span class='value'>" + (", ".join(map(str, room['trap_info'][pid])) if room['trap_info'][pid] else "なし") + "</span></span>") if room['rules'].get('trap', True) else "<span class='small text-warning'>このルームでは無効</span>" }
      </div>
    </div></div>

    <div class="card"><div class="card-header">相手</div><div class="card-body">
      <div class="mb-1"><span class="badge bg-secondary">名前</span> <span class="value">{oppname}</span></div>
      <div class="mb-1"><span class="badge bg-secondary">あなたに対する予想回数</span> <span class="value">{room['tries'][opp]}</span></div>
      <div class="mb-1"><span class="badge bg-secondary">ログ閲覧権（info）</span> {"有効" if room['can_view'][opp] else "なし"}</div>
      <div class="small text-warning">レンジ: <span class="value">{room['eff_num_min']}〜{room['eff_num_max']}</span></div>
    </div></div>
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
<div class="card mb-3"><div class="card-header">ラウンド {room['round_no']} の結果</div><div class="card-body">
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
</div></div>
<div class="card"><div class="card-header">このラウンドの行動履歴（フル）</div><div class="card-body">
  <div class="log-box"><ol class="mb-0">{log_html_full}</ol></div>
</div></div>
"""
    return bootstrap_page("ラウンド結果", body)

@app.get('/next/<room_id>')
def next_round(room_id):
    room = room_or_404(room_id)
    if room['winner'] is None:
        return redirect(url_for('play', room_id=room_id))
    loser = 2 if room['winner'] == 1 else 1
    room['starter'] = loser
    room['round_no'] += 1
    room['secret'][1] = None
    room['secret'][2] = None
    room['phase'] = 'lobby'
    return redirect(url_for('room_lobby', room_id=room_id))

@app.get('/finish/<room_id>')
def finish_match(room_id):
    room = room_or_404(room_id)
    p1, p2 = room['pname'][1], room['pname'][2]
    msg = f"🏆 マッチ終了！ {p1} {room['score'][1]} - {room['score'][2]} {p2}"
    del rooms[room_id]
    return bootstrap_page("マッチ終了", f"<div class='alert alert-info'>{msg}</div><a class='btn btn-primary' href='{url_for('index')}'>ホームへ</a>")

# ====== コア処理 ======
def _true_hint_value(room, pid, htype):
    """実際のヒント値（相手の秘密と隠し数から計算）"""
    opp = 2 if pid == 1 else 1
    opp_secret = room['secret'][opp]
    hidden = room['hidden']
    if htype == '和':
        return opp_secret + hidden
    elif htype == '差':
        return abs(opp_secret - hidden)
    else:
        return opp_secret * hidden

def _emit_hint_log(room, pid, htype, val):
    """ヒントの表示値をログへ（Trickster効果で±1誤差を適用）"""
    opp = 2 if pid == 1 else 1
    shown = val
    if room['rules'].get('roles', True) and has_role(room, opp, 'Trickster'):
        shown = val + random.choice([-1, 1])
    myname = room['pname'][pid]
    push_log(room, f"{myname} が h（ヒント取得）{htype}＝{shown}")

def _hint_once(room, pid, chose_by_user=False, silent=False):
    stock = room['available_hints'][pid]
    if stock:
        htype = random.choice(stock)
        stock.remove(htype)
    else:
        htype = random.choice(['和','差','積'])
    val = _true_hint_value(room, pid, htype)
    if not silent:
        _emit_hint_log(room, pid, htype, val)
    return

def handle_guess(room, pid, guess):
    opp = 2 if pid == 1 else 1
    myname = room['pname'][pid]
    opponent_secret = room['secret'][opp]

    if room['guess_ct'][pid] > 0:
        push_log(room, "（予想はクールタイム中）"); switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    room['tries'][pid] += 1

    if room['rules'].get('guessflag', True) and room['guess_flag_armed'][opp]:
        room['guess_flag_armed'][opp] = False
        push_log(room, f"（{room['pname'][opp]} のゲスフラグが発動！{room['pname'][pid]} は即死）")
        room['score'][opp] += 1; room['winner'] = opp
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    if guess == opponent_secret:
        push_log(room, f"{myname} が g（予想）→ {guess}（正解！相手は即死）")
        room['score'][pid] += 1; room['winner'] = pid
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    kill = set(room['trap_kill'][opp]) if room['rules'].get('trap', True) else set()
    info = set(room['trap_info'][opp]) if room['rules'].get('trap', True) else set()

    if any(abs(guess - k) <= 1 for k in kill):
        push_log(room, f"{myname} が g（予想）→ {guess}（killトラップ±1命中＝即敗北）")
        room['score'][opp] += 1; room['winner'] = opp
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    if guess in info:
        room['pending_view'][opp] = True
        room['view_cut_index'][opp] = len(room['actions'])
        push_log(room, f"{myname} が g（予想）→ {guess}（情報トラップ発動）")

    if any(abs(guess - k) <= 5 for k in kill):
        ok = apply_skip(room, pid, "（近接±5）")
        push_log(room, f"{myname} が g（予想）→ {guess}（kill近接±5命中：次ターンスキップ{'（ただし無効化）' if not ok else ''}）")
        if room['guess_penalty_active'][pid]:
            room['guess_ct'][pid] = 1
        switch_turn(room, pid); return redirect(url_for('play', room_id=get_current_room_id()))

    push_log(room, f"{myname} が g（予想）→ {guess}（ハズレ）")
    if room['rules'].get('press', True) and (not room['press_used'][pid]) and (not room['press_pending'][pid]):
        room['press_pending'][pid] = True
        return redirect(url_for('play', room_id=get_current_room_id()))

    if room['guess_penalty_active'][pid]:
        room['guess_ct'][pid] = 1
    switch_turn(room, pid); return redirect(url_for('play', room_id=get_current_room_id()))

def handle_hint(room, pid, form):
    myname = room['pname'][pid]
    opp = 2 if pid == 1 else 1

    if room['hint_ct'][pid] > 0:
        push_log(room, "（ヒントはクールタイム中）"); switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    want_choose = bool(form.get('confirm_choice'))
    choose_type = form.get('hint_type')

    # ブラフ無効 → 通常ヒント
    if not room['rules'].get('bluff', True):
        allow_choose_now = want_choose and (room['hint_choice_available'][pid] or (room['rules'].get('roles', True) and has_role(room, pid, 'Scholar'))) and choose_type in ('和','差','積')
        if allow_choose_now:
            # 後攻の一回権は消費（Scholarは無視）
            if not has_role(room, pid, 'Scholar'):
                room['hint_choice_available'][pid] = False
            val = _true_hint_value(room, pid, choose_type)
            _emit_hint_log(room, pid, choose_type, val)
        else:
            _hint_once(room, pid, chose_by_user=False, silent=False)
        if room['hint_penalty_active'][pid]:
            room['hint_ct'][pid] = room['hint_penalty_ct_value'][pid]
        switch_turn(room, pid); return redirect(url_for('play', room_id=get_current_room_id()))

    # ブラフ有効：確認画面
    decision = form.get('bluff_decision')  # 'believe' or 'accuse' or None
    has_bluff = bool(room['bluff'][opp])

    if not decision:
        keep = ""
        if want_choose: keep += "<input type='hidden' name='confirm_choice' value='1'>"
        if want_choose and choose_type: keep += f"<input type='hidden' name='hint_type' value='{choose_type}'>"
        if has_bluff:
            fake = room['bluff'][opp]
            body = f"""
<div class="card"><div class="card-header">ヒント（確認）</div><div class="card-body">
  <p class="h5 mb-3">提示されたヒントの値： <span class="badge bg-warning text-dark">{fake['value']}</span></p>
  <p class="mb-3">このヒントはブラフだと思いますか？</p>
  <form method="post" class="d-inline me-2">
    <input type="hidden" name="action" value="h"><input type="hidden" name="bluff_decision" value="believe">{keep}
    <button class="btn btn-primary">信じる</button></form>
  <form method="post" class="d-inline">
    <input type="hidden" name="action" value="h"><input type="hidden" name="bluff_decision" value="accuse">{keep}
    <button class="btn btn-outline-light">ブラフだ！と指摘する</button></form>
  <div class="mt-3"><a class="btn btn-outline-light" href="{url_for('play', room_id=get_current_room_id())}">戻る</a></div>
</div></div>"""
        else:
            body = f"""
<div class="card"><div class="card-header">ヒント（確認）</div><div class="card-body">
  <p class="mb-3">このヒントはブラフだと思いますか？</p>
  <form method="post" class="d-inline me-2">
    <input type="hidden" name="action" value="h"><input type="hidden" name="bluff_decision" value="believe">{keep}
    <button class="btn btn-primary">信じる（通常のヒント）</button></form>
  <form method="post" class="d-inline">
    <input type="hidden" name="action" value="h"><input type="hidden" name="bluff_decision" value="accuse">{keep}
    <button class="btn btn-outline-light">ブラフだ！と指摘する</button></form>
  <div class="mt-3"><a class="btn btn-outline-light" href="{url_for('play', room_id=get_current_room_id())}">戻る</a></div>
</div></div>"""
        return bootstrap_page("ヒント確認", body)

    # 意思決定後
    if has_bluff:
        if decision == 'believe':
            push_log(room, f"{myname} は 提示ヒント（{room['bluff'][opp]['value']}）を受け入れた")
            room['bluff'][opp] = None
            if room['hint_penalty_active'][pid]:
                room['hint_ct'][pid] = room['hint_penalty_ct_value'][pid]
            switch_turn(room, pid); return redirect(url_for('play', room_id=get_current_room_id()))
        else:
            _hint_once(room, pid); _hint_once(room, pid)
            room['bluff'][opp] = None
            if room['hint_penalty_active'][pid]:
                room['hint_ct'][pid] = room['hint_penalty_ct_value'][pid]
            switch_turn(room, pid); return redirect(url_for('play', room_id=get_current_room_id()))
    else:
        if decision == 'accuse':
            room['hint_penalty_active'][pid] = True
            room['hint_penalty_ct_value'][pid] = 2 if (room['rules'].get('roles', True) and has_role(room, opp, 'Trickster')) else 1
            push_log(room, f"{myname} は ブラフだと指摘したが外れ（以後ヒント取得後はCT{room['hint_penalty_ct_value'][pid]}）")
            switch_turn(room, pid); return redirect(url_for('play', room_id=get_current_room_id()))
        else:
            allow_choose_now = want_choose and (room['hint_choice_available'][pid] or (room['rules'].get('roles', True) and has_role(room, pid, 'Scholar'))) and choose_type in ('和','差','積')
            if allow_choose_now:
                if not has_role(room, pid, 'Scholar'):
                    room['hint_choice_available'][pid] = False
                val = _true_hint_value(room, pid, choose_type)
                _emit_hint_log(room, pid, choose_type, val)
            else:
                _hint_once(room, pid)
            if room['hint_penalty_active'][pid]:
                room['hint_ct'][pid] = room['hint_penalty_ct_value'][pid]
            switch_turn(room, pid); return redirect(url_for('play', room_id=get_current_room_id()))

def handle_change(room, pid, new_secret):
    myname = room['pname'][pid]
    if room['cooldown'][pid] > 0:
        push_log(room, "（自分の数の変更はクールタイム中）"); switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    my_traps = set(room['trap_kill'][pid]) | set(room['trap_info'][pid])
    if new_secret in my_traps:
        push_log(room, "⚠ その数字は現在のトラップに含まれています。"); switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    if not (room['eff_num_min'] <= new_secret <= room['eff_num_max']):
        push_log(room, "⚠ 範囲外の数字です。"); switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    if room.get('change_used', {}).get(pid, 0) >= 2:
        push_log(room, "（このラウンドでの変更は2回まで）"); switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    room['secret'][pid] = new_secret
    room['cooldown'][pid] = 7
    room['change_used'][pid] = room.get('change_used', {}).get(pid, 0) + 1

    # 宣言効果のリセット
    room['decl1_value'][pid] = None
    room['decl1_resolved'][pid] = True
    room['decl1_used'][pid] = False
    room['info_free_per_turn'][pid] = 1
    room['info_max'][pid] = INFO_MAX_DEFAULT
    room['info_free_used_this_turn'][pid] = min(room['info_free_used_this_turn'][pid], room['info_free_per_turn'][pid])

    opp = 2 if pid == 1 else 1
    room['available_hints'][opp] = ['和','差','積']

    push_log(room, f"{myname} が c（自分の数を変更）→ {new_secret}")
    push_log(room, f"（宣言効果リセット：無料info/ターン=1、上限={INFO_MAX_DEFAULT}。再宣言可）")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_trap_kill(room, pid, form):
    if not room['rules'].get('trap', True):
        return push_and_back(room, pid, "（このルームではトラップは無効です）")
    myname = room['pname'][pid]
    eff_min, eff_max = room['eff_num_min'], room['eff_num_max']
    my_secret = room['secret'][pid]
    v = form.get('trap_kill_value')
    try: x = int(v)
    except: 
        push_log(room, "⚠ 無効なkillトラップ値です。"); switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    if not (eff_min <= x <= eff_max) or x == my_secret or (room['allow_negative'] and abs(x) == abs(my_secret)):
        push_log(room, "⚠ 無効なkillトラップ値です。"); switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    room['trap_kill'][pid].clear(); room['trap_kill'][pid].append(x)
    push_log(room, f"{myname} が killトラップを {x} に設定")
    switch_turn(room, pid); return redirect(url_for('play', room_id=get_current_room_id()))

def handle_decl1(room, pid, form):
    if not room['rules'].get('decl1', True):
        return push_and_back(room, pid, "（このルームでは一の位の宣言は無効です）")
    myname = room['pname'][pid]
    if room['decl1_used'][pid]:
        return push_and_back(room, pid, "（このラウンドは既に宣言しています）")
    d = get_int(form, 'decl1_digit', None, 0, 9)
    if d is None:
        return push_and_back(room, pid, "⚠ 一の位は0〜9で入力してください。")
    room['decl1_value'][pid] = d
    room['decl1_used'][pid] = True
    room['decl1_resolved'][pid] = False
    room['info_free_per_turn'][pid] = 2
    room['info_max'][pid] = 10
    push_log(room, f"{myname} が 一の位を {d} と宣言（このラウンド中、無料infoは1ターン2個・最大10個）")
    opp = 2 if pid == 1 else 1
    push_log(room, f"{room['pname'][opp]} への通知: {myname} が秘密の数字の一の位が {d} であると宣言した")
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_decl1_challenge(room, pid):
    if not room['rules'].get('decl1', True):
        return push_and_back(room, pid, "（このルームでは一の位の宣言は無効です）")
    myname = room['pname'][pid]; opp = 2 if pid == 1 else 1
    if room['decl1_value'][opp] is None or room['decl1_resolved'][opp]:
        return push_and_back(room, pid, "（相手の宣言は現在チャレンジできません）")
    true_ones = abs(room['secret'][opp]) % 10; declared = room['decl1_value'][opp]
    if declared != true_ones:
        push_log(room, f"{myname} が『嘘だ！』→ 成功。正しい一の位は {true_ones}")
        room['decl1_resolved'][opp] = True
        room['free_guess_pending'][pid] = True
        return redirect(url_for('play', room_id=get_current_room_id()))
    else:
        ok = apply_skip(room, pid, "（嘘だコール失敗）")
        push_log(room, f"{myname} が『嘘だ！』→ 失敗。次ターンスキップ{'（ただし無効化）' if not ok else ''}")
        room['decl1_resolved'][opp] = True
        switch_turn(room, pid); return redirect(url_for('play', room_id=get_current_room_id()))

def handle_free_guess(room, pid, guess):
    opp = 2 if pid == 1 else 1
    myname = room['pname'][pid]
    room['free_guess_pending'][pid] = False
    opponent_secret = room['secret'][opp]
    if guess == opponent_secret:
        push_log(room, f"{myname} が 無料g（予想）→ {guess}（正解！相手は即死）")
        room['score'][pid] += 1; room['winner'] = pid
        return redirect(url_for('end_round', room_id=get_current_room_id()))
    kill = set(room['trap_kill'][opp]); info = set(room['trap_info'][opp])
    if any(abs(guess - k) <= 1 for k in kill):
        push_log(room, f"{myname} が 無料g（予想）→ {guess}（killトラップ±1命中＝即敗北）")
        room['score'][opp] += 1; room['winner'] = opp
        return redirect(url_for('end_round', room_id=get_current_room_id()))
    if guess in info:
        room['pending_view'][opp] = True; room['view_cut_index'][opp] = len(room['actions'])
        push_log(room, f"{myname} が 無料g（予想）→ {guess}（情報トラップ発動）")
    if any(abs(guess - k) <= 5 for k in kill):
        room['skip_suppress_pid'] = pid
        ok = apply_skip(room, pid, "（無料g近接±5）")
        push_log(room, f"{myname} が 無料g（予想）→ {guess}（kill近接±5命中：次ターンスキップ{'（ただし無効化）' if not ok else ''}）")
        return redirect(url_for('play', room_id=get_current_room_id()))
    push_log(room, f"{myname} が 無料g（予想）→ {guess}（ハズレ）")
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_press(room, pid, guess):
    if not room['rules'].get('press', True):
        return push_and_back(room, pid, "（このルームではサドン・プレスは無効です）")
    if not room['press_pending'][pid]:
        return push_and_back(room, pid, "（サドン・プレスの機会はありません）")
    opp = 2 if pid == 1 else 1; myname = room['pname'][pid]
    room['press_pending'][pid] = False; room['press_used'][pid] = True
    room['tries'][pid] += 1
    opponent_secret = room['secret'][opp]
    if guess == opponent_secret:
        push_log(room, f"{myname} が プレスg（予想）→ {guess}（正解！相手は即死）")
        room['score'][pid] += 1; room['winner'] = pid
        return redirect(url_for('end_round', room_id=get_current_room_id()))
    kill = set(room['trap_kill'][opp]); info = set(room['trap_info'][opp])
    if any(abs(guess - k) <= 1 for k in kill):
        push_log(room, f"{myname} が プレスg（予想）→ {guess}（killトラップ±1命中＝即敗北）")
        room['score'][opp] += 1; room['winner'] = opp
        return redirect(url_for('end_round', room_id=get_current_room_id()))
    if guess in info:
        room['pending_view'][opp] = True; room['view_cut_index'][opp] = len(room['actions'])
        push_log(room, f"{myname} が プレスg（予想）→ {guess}（情報トラップ発動）")
    ok = apply_skip(room, pid, "（プレス外し）")
    push_log(room, f"{myname} が プレスg（予想）→ {guess}（ハズレ：次ターンスキップ{'（ただし無効化）' if not ok else ''}）")
    switch_turn(room, pid); return redirect(url_for('play', room_id=get_current_room_id()))

def handle_press_skip(room, pid):
    if not room['rules'].get('press', True):
        return push_and_back(room, pid, "（このルームではサドン・プレスは無効です）")
    if not room['press_pending'][pid]:
        return push_and_back(room, pid, "（サドン・プレスの機会はありません）")
    room['press_pending'][pid] = False
    push_log(room, f"{room['pname'][pid]} は サドン・プレスを使用しなかった")
    if room['hint_penalty_active'][pid]:
        room['hint_ct'][pid] = room['hint_penalty_ct_value'][pid]
    switch_turn(room, pid); return redirect(url_for('play', room_id=get_current_room_id()))

def handle_trap_info(room, pid, form):
    if not room['rules'].get('trap', True):
        return push_and_back(room, pid, "（このルームではトラップは無効です）")
    myname = room['pname'][pid]
    eff_min, eff_max = room['eff_num_min'], room['eff_num_max']
    my_secret = room['secret'][pid]
    max_allowed = get_info_max(room, pid)
    free_cap = room['info_free_per_turn'][pid]
    free_used = room['info_free_used_this_turn'][pid]
    bulk = form.get('info_bulk') in ('1','on','true','True')

    if bulk:
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
            switch_turn(room, pid)
        else:
            push_log(room, "⚠ infoトラップの追加はありません。")
        return redirect(url_for('play', room_id=get_current_room_id()))

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
        added = x; break

    if added is not None:
        room['trap_info'][pid].append(added)
        room['info_free_used_this_turn'][pid] += 1
        push_log(room, f"{myname} が infoトラップを {added} に設定（ターン消費なし／このターンはあと {free_cap - room['info_free_used_this_turn'][pid]} 個）")
    else:
        push_log(room, "⚠ infoトラップの追加はありません。")
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_trap(room, pid, form):
    if not room['rules'].get('trap', True):
        return push_and_back(room, pid, "（このルームではトラップは無効です）")
    myname = room['pname'][pid]
    eff_min, eff_max = room['eff_num_min'], room['eff_num_max']
    my_secret = room['secret'][pid]
    turn_consumed = False

    bulk = form.get('info_bulk') in ('1','on','true','True')
    info_keys = ('trap_info_value', 'trap_info_value_1', 'trap_info_value_2', 'trap_info_val')
    info_inputs = []
    for k in info_keys:
        v = form.get(k)
        if v is None or v == '': continue
        try: x = int(v)
        except: continue
        info_inputs.append(x)
    info_inputs_unique = []
    for x in info_inputs:
        if x not in info_inputs_unique: info_inputs_unique.append(x)

    max_allowed = get_info_max(room, pid)
    free_cap   = room['info_free_per_turn'][pid]
    free_used  = room['info_free_used_this_turn'][pid]

    if bulk and info_inputs_unique:
        added_bulk = []
        for x in info_inputs_unique:
            if not (eff_min <= x <= eff_max): continue
            if x == my_secret or (room['allow_negative'] and abs(x) == abs(my_secret)): continue
            if x in room['trap_info'][pid] or x in added_bulk: continue
            if len(room['trap_info'][pid]) >= max_allowed: break
            added_bulk.append(x)
        if added_bulk:
            room['trap_info'][pid].extend(added_bulk)
            push_log(room, f"{myname} が infoトラップをまとめて設定 → {', '.join(map(str, added_bulk))}（ターン消費）")
            turn_consumed = True
        else:
            push_log(room, "⚠ infoトラップの追加はありません。")

    if (not bulk) and info_inputs_unique:
        remain = max(0, free_cap - free_used)
        added_free = []
        for x in info_inputs_unique:
            if remain <= 0: break
            if not (eff_min <= x <= eff_max): continue
            if x == my_secret or (room['allow_negative'] and abs(x) == abs(my_secret)): continue
            if x in room['trap_info'][pid] or x in added_free: continue
            if len(room['trap_info'][pid]) >= max_allowed: break
            room['trap_info'][pid].append(x)
            added_free.append(x); remain -= 1
        if added_free:
            room['info_free_used_this_turn'][pid] += len(added_free)
            left = max(0, free_cap - room['info_free_used_this_turn'][pid])
            push_log(room, f"{myname} が infoトラップを {', '.join(map(str, added_free))} に設定（ターン消費なし／このターンはあと {left} 個）")
        else:
            if free_cap - free_used <= 0:
                push_log(room, f"（このターンの無料infoは上限 {free_cap} 個に達しています）")
            else:
                push_log(room, "⚠ infoトラップの追加はありません。")

    kill_v = form.get('trap_kill_value')
    if kill_v is not None and kill_v != '':
        try: kx = int(kill_v)
        except: kx = None
        if kx is None or not (eff_min <= kx <= eff_max) or kx == my_secret or (room['allow_negative'] and abs(kx) == abs(my_secret)):
            push_log(room, "⚠ 無効なkillトラップ値です。")
        else:
            room['trap_kill'][pid].clear(); room['trap_kill'][pid].append(kx)
            push_log(room, f"{myname} が killトラップを {kx} に設定")
            turn_consumed = True

    if turn_consumed:
        switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_bluff(room, pid, form):
    if not room['rules'].get('bluff', True):
        return push_and_back(room, pid, "（このルームではブラフヒントは無効です）")
    myname = room['pname'][pid]
    btype = form.get('bluff_type') or '和'
    try: bval = int(form.get('bluff_value'))
    except:
        push_log(room, "⚠ ブラフ値が不正です。"); switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    room['bluff'][pid] = {'type': btype, 'value': bval}
    push_log(room, f"{myname} が ブラフヒント を仕掛けた")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_guessflag(room, pid):
    if not room['rules'].get('guessflag', True):
        return push_and_back(room, pid, "（このルームではゲスフラグは無効です）")
    myname = room['pname'][pid]
    if room['guess_flag_used'][pid]:
        push_log(room, "⚠ このラウンドでは既にゲスフラグを使っています。"); switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    room['guess_flag_armed'][pid] = True; room['guess_flag_used'][pid] = True
    push_log(room, f"{myname} が ゲスフラグ を立てた")
    switch_turn(room, pid); return redirect(url_for('play', room_id=get_current_room_id()))

def handle_dual_devotion(room, pid, form):
    if not room['rules'].get('dual_devotion', True) or not room['rules'].get('roles', True):
        return push_and_back(room, pid, "（このルームでは二重職：献身は無効です）")
    if room['dual_used'][pid]:
        return push_and_back(room, pid, "（このラウンドでの二重職は既に使用済みです）")
    myname = room['pname'][pid]
    candidates = room['dual_candidates'][pid]
    if not candidates:
        owned = set([x for x in (room.get('role', {}).get(pid), room.get('extra_role', {}).get(pid)) if x])
        pool = [x for x in ALL_ROLES if x not in owned]
        if not pool:
            return push_and_back(room, pid, "（取得可能なロール候補がありません）")
        k = min(3, len(pool)); candidates = random.sample(pool, k=k)
        room['dual_candidates'][pid] = candidates

    pick = form.get('pick')
    if not pick:
        opts = "".join(
            f"""<form method="post" class="d-inline me-2">
                <input type="hidden" name="action" value="dual_devotion">
                <input type="hidden" name="pick" value="{c}">
                <button class="btn btn-primary mb-2">{c} を選ぶ</button>
              </form>""" for c in candidates
        )
        body = f"""
<div class="card"><div class="card-header">二重職：献身（取得するロールを選択）</div><div class="card-body">
  <p class="mb-2">候補から <strong>1つ</strong>選んでください（重複不可・このラウンドのみ有効）。</p>
  <div class="mb-3">{opts}</div>
  <div class="small text-warning">代償：今ターン終了／<code>guess_ct=1</code> と <code>hint_ct=1</code>／このラウンドの <em>info</em> 上限 <strong>-2</strong>。</div>
  <div class="mt-3"><a class="btn btn-outline-light" href="{url_for('play', room_id=get_current_room_id())}">戻る</a></div>
</div></div>"""
        return bootstrap_page("二重職：献身", body)

    if pick not in room['dual_candidates'][pid]:
        return push_and_back(room, pid, "（不正な候補が選択されました）")
    room['extra_role'][pid] = pick
    room['dual_used'][pid] = True
    room['dual_candidates'][pid] = []
    room['guess_ct'][pid] = max(room['guess_ct'][pid], 1)
    room['hint_ct'][pid] = max(room['hint_ct'][pid], 1)
    room['devotion_penalty_active'][pid] = True
    push_log(room, f"{myname} は 二重職：献身 を使った（追加ロールを獲得／このラウンドの info上限-2／今ターン終了）")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_yn(room, pid, form):
    if not room['rules'].get('yn', True):
        return push_and_back(room, pid, "（このルームではYes/No質問は無効です）")
    if room['yn_used_this_turn'][pid]:
        return push_and_back(room, pid, "（Yes/Noは同一ターンに複数回は使えません）")
    max_per_round = 3 if (room['rules'].get('roles', True) and has_role(room, pid, 'Analyst')) else 1
    if room['yn_used_count'][pid] >= max_per_round:
        return push_and_back(room, pid, f"（このラウンドのYes/Noは上限 {max_per_round} 回です）")
    if room['yn_ct'][pid] > 0:
        return push_and_back(room, pid, "（Yes/Noはクールタイム中です）")

    yn_type = form.get('yn_type')
    x = get_int(form, 'x', None, room['eff_num_min'], room['eff_num_max'])
    a = get_int(form, 'a', None, room['eff_num_min'], room['eff_num_max'])
    b = get_int(form, 'b', None, room['eff_num_min'], room['eff_num_max'])

    opp = 2 if pid == 1 else 1
    target = room['secret'][opp]
    qtext = ""
    ans = "No"

    if yn_type == 'ge' and x is not None:
        qtext = f"相手の数 ≥ {x} ?"; ans = "Yes" if target >= x else "No"
    elif yn_type == 'le' and x is not None:
        qtext = f"相手の数 ≤ {x} ?"; ans = "Yes" if target <= x else "No"
    elif yn_type == 'range' and a is not None and b is not None:
        lo, hi = (a, b) if a <= b else (b, a)
        qtext = f"相手の数は [{lo},{hi}] 内？"; ans = "Yes" if (lo <= target <= hi) else "No"
    else:
        return push_and_back(room, pid, "⚠ 質問の形式または値が不正です。")

    myname = room['pname'][pid]
    push_log(room, f"{myname} が Yes/No 質問：{qtext} → <strong>{ans}</strong>")
    room['yn_used_this_turn'][pid] = True
    room['yn_used_count'][pid] += 1
    if has_role(room, pid, 'Analyst'):
        room['yn_ct'][pid] = 2  # CT2
    # ターンは消費しない
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
    try:
        rid = session.get('room_id'); pid = session.get('player_id')
        if not rid or rid not in rooms or pid not in (1,2): session.clear()
    except: session.clear()
    return bootstrap_page("エラー", f"""
<div class="alert alert-danger">Internal Server Error が発生しました。もう一度お試しください。</div>
<a class="btn btn-primary" href="{url_for('index')}">ホームへ</a>
"""), 500

# ====== 起動 ======
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
