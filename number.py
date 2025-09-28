# number.py
from flask import Flask, request, redirect, url_for, render_template_string, session, abort, jsonify
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

# ルール既定値（ロール/YesNo/献身 もトグル可能）
RULE_DEFAULTS = {
    'trap': True,       # kill/info トラップ
    'bluff': True,      # ブラフヒント
    'guessflag': True,  # ゲスフラグ
    'decl1': True,      # 一の位の宣言＆嘘だ！コール
    'press': True,      # サドン・プレス（Double or Nothing）
    'roles': True,      # ロール（各ラウンドでランダム配布、非公開）
    'yn': True,         # Yes/No 質問
    'devotion': True,   # 二重職：献身（ラウンド中のみ）
}

# 役職一覧（キー名は内部名、labelは表示）
ROLES = {
    'Scholar':  '学者',
    'Guardian': '番人',
    'Trapper':  '罠師',
    'Disarmer': '解除士',
    'Trickster':'詐欺師',
    'Analyst':  '分析屋',
}

def role_label(code):
    return ROLES.get(code, '—')

# ====== ルーム状態 ======
rooms = {}  # room_id -> dict(state)

# ====== ユーティリティ ======

def get_current_room_id():
    rid = session.get('room_id')
    if rid in rooms:
        return rid
    try:
        if request.view_args and 'room_id' in request.view_args:
            rid = request.view_args.get('room_id')
            if rid in rooms:
                return rid
    except Exception:
        pass
    try:
        path = request.path or ''
        for _rid in rooms.keys():
            if f'/{_rid}' in path:
                return _rid
    except Exception:
        pass
    return None

def get_info_max(room, pid):
    base = room.get('info_max', {}).get(pid, INFO_MAX_DEFAULT)
    extra = 0
    if has_role(room, pid, 'Trapper'):
        extra += 3
    extra -= room.get('devotion_info_penalty', {}).get(pid, 0)
    return max(1, min(base + extra, 13))

def get_int(form, key, default=None, min_v=None, max_v=None):
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
    if msg:
        push_log(room, msg)
    rid = get_current_room_id()
    if rid is None:
        try:
            for k, v in rooms.items():
                if v is room:
                    rid = k
                    break
        except Exception:
            rid = None
    if rid is None:
        return redirect(url_for('index'))
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
    .card { background:#0f172a; border:1px solid #334155; --bs-card-cap-color:#f9a8d4; --bs-card-color:#f1f5f9; }
    .card-header { background:#0b1323; border-bottom:1px solid #334155; color:#f9a8d4 !important; font-weight:700; }
    .card-header .h1, .card-header .h2, .card-header .h3,
    .card-header h1, .card-header h2, .card-header h3, .card-title, .modal-title { color:#f9a8d4 !important; }
    .btn-primary { background:#2563eb; border-color:#1d4ed8; }
    .btn-primary:hover { background:#1d4ed8; border-color:#1e40af; }
    .btn-outline-light { color:#f1f5f9; border-color:#94a3b8; }
    .btn-outline-light:hover { color:#0b1220; background:#e2e8f0; border-color:#e2e8f0; }
    .badge { font-size:.9rem; }
    .badge.bg-secondary { background-color:#f472b6 !important; color:#0b1220 !important; border:1px solid #fda4af !important; }
    .form-control, .form-select { background:#0b1323; color:#f1f5f9; border-color:#475569; }
    .form-control::placeholder { color:#e9c5d9; opacity:1; }
    .form-control:focus, .form-select:focus { border-color:#93c5fd; box-shadow:none; }
    .text-muted, .small.text-muted, .form-label { color:#e6f0ff !important; }
    .form-check-label { color:#e6f0ff !important; }
    .small { color:#e6f0ff !important; }
    .small.text-warning, .text-warning { color:#93c5fd !important; }
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

            <div class="p-3 rounded border border-secondary mb-3">
              <h6 class="mb-2">基本ルール</h6>
              <ul class="mb-0">
                <li>各プレイヤーは自分だけが知る「秘密の数」を選びます（通常は <code>{{ NUM_MIN }}</code>〜<code>{{ NUM_MAX }}</code>。負の数ON時は±範囲）。</li>
                <li>各ラウンドごとに誰にも知られない「隠し数」が自動で決まります（<code>{{ HIDDEN_MIN }}</code>〜<code>{{ HIDDEN_MAX }}</code>。負の数ON時は<strong>±{{ HIDDEN_MIN }}〜{{ HIDDEN_MAX }}</strong>で0は出ない）。</li>
                <li>ターンは交互。自分のターンに「予想」「ヒント」「トラップ設置」などの行動を選びます。</li>
                <li>相手の秘密の数を当てるとラウンド勝利。先取ポイントに到達したプレイヤーがマッチ勝利。</li>
              </ul>
            </div>

            <ol class="mb-3">
              <li class="mb-2"><strong>勝利条件</strong>：相手の秘密の数字を当てる。</li>
              <li class="mb-2"><strong>基本レンジ</strong>：選べる数は <code>{{ NUM_MIN }}</code>〜<code>{{ NUM_MAX }}</code>（負の数ON時は ±範囲）。隠し数は <code>{{ HIDDEN_MIN }}</code>〜<code>{{ HIDDEN_MAX }}</code>（負の数ON時は ±範囲で0なし）。</li>
              <li class="mb-2"><strong>ヒント</strong>：和/差/積から1つが得られます。後攻のみ各ラウンド1回、種類の指定が可能。<br>※<em>学者</em>ならラウンド中ずっと種類指定可＆ヒントCT無効。</li>
              <li class="mb-2"><strong>トラップ</strong>（ON時）：
                <ul>
                  <li><strong>kill</strong>：±1命中で即死、±5命中で次ターンスキップ（設置はターン消費／上書き1個）。</li>
                  <li><strong>info</strong>：踏まれると、<em>その時点以降</em>の相手の行動履歴を閲覧可能。通常は同時最大7個・1ターンに無料1個設置（ターン消費なし）。チェックすると3個まとめて（ターン消費）。<br>
                    ※<em>罠師</em>で最大+3（宣言と重なると13上限）。※<em>解除士</em>は相手ターン開始時に1個自動解除（各ラウンド1回）。</li>
                </ul>
              </li>
              <li class="mb-2"><strong>ブラフヒント</strong>（ON時）：次回ヒントに偽の値を提示。「信じる／ブラフだ！」を選択。指摘成功で本物ヒント×2、失敗で以後ヒント取得時にCT1（<em>詐欺師</em>相手ならCT2）。<br>
                ※<em>詐欺師</em>が相手なら、本物ヒントの表示値は毎回 ±1 のノイズが乗る（ブラフ判定とは無関係）。</li>
              <li class="mb-2"><strong>ゲスフラグ</strong>（ON時）：自分ターンに設置（各ラウンド1回）。次の相手ターンで相手が予想したら即死。</li>
              <li class="mb-2"><strong>一の位 宣言（decl1）</strong>（ON時）：ターン消費なし・各ラウンド1回。「自分の一の位」を宣言。嘘だ！成功で正しい一の位公開＋直後に無料予想。失敗で次ターンスキップ。<br>
                宣言者は<strong>ラウンド中ずっと</strong>、無料infoが<strong>1ターン2個</strong>に、info最大数が<strong>10</strong>に。</li>
              <li class="mb-2"><strong>サドン・プレス</strong>（ON時）：ハズレ直後に同ターンでもう1回だけ連続予想（当たれば勝利、外せば次ターンスキップ）。各ラウンド1回。</li>
              <li class="mb-2"><strong>自分の数の変更（c）</strong>：自分のトラップ値とは重複不可。各ラウンド<strong>2回まで</strong>。使用後は自分の<span class="value">CT7</span>、かつ相手のヒント在庫をリセット。</li>
              <li class="mb-2"><strong>ロール（ON時）</strong>：各ラウンド開始時にランダム配布（自分だけ確認可）。
                <ul>
                  <li><em>学者</em>：ラウンド中ずっとヒント種類指定可＆ヒントCT無効。</li>
                  <li><em>番人</em>：自分の「次ターンスキップ」を1度だけ自動無効化（原因は何でもOK）。</li>
                  <li><em>罠師</em>：info最大 +3（宣言と重なると13上限）。</li>
                  <li><em>解除士</em>：各ラウンド1回、自分のターン開始時に相手のinfoをランダムで1つ解除。</li>
                  <li><em>詐欺師</em>：相手がブラフ指摘に失敗するとヒントCT2。さらに相手が得た本物ヒントは表示値に±1のノイズ。</li>
                  <li><em>分析屋</em>：Yes/No質問がクールタイム2、ラウンド3回まで（同一ターン連打は不可）。</li>
                </ul>
              </li>
              <li class="mb-2"><strong>Yes/No 質問（ON時）</strong>：ターン消費なしで二択質問を送れる（例：「≥X？」「≤X？」「=X？」「範囲[A,B]内？」）。奇数/偶数は質問不可。通常はラウンド1回だけ。</li>
              <li class="mb-2"><strong>二重職：献身（ON時）</strong>：自分のターンで候補3から追加で1ロールを取得（ラウンド限定）。代償として今ターン終了、さらに <code>guess_ct=1</code> & <code>hint_ct=1</code>、加えて自分のinfo最大を<strong>2個減少</strong>（そのラウンド中）。</li>
            </ol>
            <p class="small text-warning">ログは infoトラップ発動以降のみ相手の行動詳細が見える仕様です。</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-primary" data-bs-dismiss="modal">閉じる</button>
          </div>
        </div>
      </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  </div>
</body>
</html>
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

        'bluff': {1: None, 2: None},
        'hint_penalty_active': {1: False, 2: False},
        'hint_ct': {1: 0, 2: 0},
        'guess_flag_armed': {1: False, 2: False},
        'guess_flag_ct': {1: 0, 2: 0},
        'guess_penalty_active': {1: False, 2: False},
        'guess_ct': {1: 0, 2: 0},
        'guess_flag_warn': {1: False, 2: False},
        'guess_flag_used': {1: False, 2: False},

        'decl1_value': {1: None, 2: None},
        'decl1_used': {1: False, 2: False},
        'decl1_resolved': {1: True, 2: True},
        'decl1_hint_token_ready': {1: False, 2: False},
        'decl1_hint_token_active': {1: False, 2: False},
        'free_guess_pending': {1: False, 2: False},

        'press_used': {1: False, 2: False},
        'press_pending': {1: False, 2: False},

        'role_main': {1: None, 2: None},
        'role_extra': {1: None, 2: None},
        'guardian_shield_used': {1: False, 2: False},
        'disarm_used': {1: False, 2: False},

        'yn_used_count': {1:0, 2:0},
        'yn_ct': {1:0, 2:0},
        'yn_last_tick': {1:-999, 2:-999},

        'devotion_used': {1: False, 2: False},
        'devotion_offers': {1: None, 2: None},
        'devotion_info_penalty': {1: 0, 2: 0},

        'turn_serial': 0,
        'tick': 0,
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

def has_role(room, pid, code):
    if not room['rules'].get('roles', True):
        return False
    return room['role_main'][pid] == code or room['role_extra'][pid] == code

def assign_roles(room):
    if not room['rules'].get('roles', True):
        room['role_main'] = {1: None, 2: None}
        room['role_extra'] = {1: None, 2: None}
        return
    keys = list(ROLES.keys())
    room['role_main'][1] = random.choice(keys)
    room['role_main'][2] = random.choice(keys)
    room['role_extra'] = {1: None, 2: None}
    room['guardian_shield_used'] = {1: False, 2: False}
    room['disarm_used'] = {1: False, 2: False}

def set_skip(room, pid):
    if has_role(room, pid, 'Guardian') and not room['guardian_shield_used'][pid]:
        room['guardian_shield_used'][pid] = True
        push_log(room, f"{room['pname'][pid]} の番人効果により『次ターンスキップ』は無効化された（このラウンド1回）")
        return
    room['skip_next_turn'][pid] = True

def _apply_trickster_noise(room, hint_owner_pid, value):
    opp = 2 if hint_owner_pid == 1 else 1
    if has_role(room, opp, 'Trickster'):
        delta = random.choice([-1, 1])
        return value + delta
    return value

def switch_turn(room, cur_pid):
    for p in (1,2):
        if room['cooldown'][p] > 0: room['cooldown'][p] -= 1
        if room['hint_ct'][p] > 0: room['hint_ct'][p] -= 1
        if room['guess_ct'][p] > 0: room['guess_ct'][p] -= 1
        if room['guess_flag_ct'][p] > 0: room['guess_flag_ct'][p] -= 1
        if room['yn_ct'][p] > 0: room['yn_ct'][p] -= 1

    opp_prev = 2 if cur_pid == 1 else 1
    if room['pending_view'][opp_prev]:
        room['can_view'][opp_prev] = True
        room['pending_view'][opp_prev] = False

    next_pid = opp_prev
    room['turn'] = next_pid
    room['tick'] += 1
    room['turn_serial'] += 1

    room['info_free_used_this_turn'][next_pid] = 0
    room['skip_suppress_pid'] = None

    if room['rules'].get('guessflag', True):
        gf_owner = next_pid
        prev = cur_pid
        if room['guess_flag_armed'][gf_owner]:
            room['guess_flag_armed'][gf_owner] = False
            room['guess_flag_warn'][prev] = True

    if has_role(room, next_pid, 'Disarmer') and not room['disarm_used'][next_pid]:
        opp = 2 if next_pid == 1 else 1
        if room['trap_info'][opp]:
            idx = random.randrange(len(room['trap_info'][opp]))
            removed = room['trap_info'][opp].pop(idx)
            room['disarm_used'][next_pid] = True
            push_log(room, f"{room['pname'][next_pid]} の解除士が相手のinfo({removed})を解除した（このラウンド1回）")

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
          <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_trap" name="rule_trap" checked><label class="form-check-label" for="rule_trap">トラップ（kill / info）</label></div>
          <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_bluff" name="rule_bluff" checked><label class="form-check-label" for="rule_bluff">ブラフヒント</label></div>
          <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_guessflag" name="rule_guessflag" checked><label class="form-check-label" for="rule_guessflag">ゲスフラグ</label></div>
          <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_decl1" name="rule_decl1" checked><label class="form-check-label" for="rule_decl1">一の位の宣言＆嘘だ！コール</label></div>
          <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_press" name="rule_press" checked><label class="form-check-label" for="rule_press">サドン・プレス</label></div>
          <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_roles" name="rule_roles" checked><label class="form-check-label" for="rule_roles">ロール（非公開）</label></div>
          <div class="form-check"><input class="form-check-input" type="checkbox" id="rule_yn" name="rule_yn" checked><label class="form-check-label" for="rule_yn">Yes/No 質問</label></div>
          <div class="form-check mb-3"><input class="form-check-input" type="checkbox" id="rule_dev" name="rule_dev" checked><label class="form-check-label" for="rule_dev">二重職：献身</label></div>
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
        'roles': bool(request.form.get('rule_roles')),
        'yn': bool(request.form.get('rule_yn')),
        'devotion': bool(request.form.get('rule_dev')),
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
        <input class="form-control" type="number" name="secret" required min="{room['eff_num_min']}" max="{room['eff_num_max']}" placeholder="{room['eff_num_min']}〜{room['eff_num_max']}">
      </div>
      <button class="btn btn-primary w-100">参加</button>
    </form>
  </div>
</div>
"""
    return bootstrap_page("参加", body)

def start_new_round(room):
    # 1) どちらも知らない数（隠し数）：負の数ONなら ±1..30（0は出ない）
    if room['allow_negative']:
        room['hidden'] = random.choice([-1, 1]) * random.randint(HIDDEN_MIN, HIDDEN_MAX)
    else:
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

    assign_roles(room)
    room['devotion_used'] = {1: False, 2: False}
    room['devotion_offers'] = {1: None, 2: None}
    room['devotion_info_penalty'] = {1: 0, 2: 0}
    room['guardian_shield_used'] = {1: False, 2: False}
    room['disarm_used'] = {1: False, 2: False}

    room['yn_used_count'] = {1:0, 2:0}
    room['yn_ct'] = {1:0, 2:0}
    room['yn_last_tick'] = {1:-999, 2:-999}

    if room['starter'] == 1:
        room['hint_choice_available'] = {1: False, 2: True}
        room['turn'] = 1
        room['tick'] = 0
    else:
        room['hint_choice_available'] = {1: True, 2: False}
        room['turn'] = 2
        room['tick'] = 0

    room['winner'] = None
    room['phase'] = 'play'
    room['turn_serial'] += 1

@app.route('/poll/<room_id>')
def poll(room_id):
    room = room_or_404(room_id)
    return jsonify({
        'turn': room['turn'],
        'serial': room['turn_serial'],
        'winner': room['winner'],
        'phase': room['phase'],
    })

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
<div class="card mb-3">
  <div class="card-header">相手を待っています…</div>
  <div class="card-body">
  <div class="p-3 rounded border border-secondary mb-3">
    <div class="small text-warning">ルーム番号</div>
    <div class="h1 m-0 value">{room_id}</div>
    <div class="small">相手は「ホーム → ルームに参加」でこの番号を入力できます。</div>
  </div>
  <div class="alert alert-info">あなたは <span class="value">プレイヤー{pid}</span> として参加済みです。相手が参加すると自動で開始します。</div>
  <p class="mb-2">相手に送るべきリンクは <span class="value">プレイヤー{opp}用リンク</span> です。</p>
  <div class="row g-2">
    <div class="col-12 col-md-6"><div class="p-2 rounded border border-secondary"><div class="small text-warning mb-1">プレイヤー1用リンク</div><a href="{l1}">{l1}</a><div class="mt-1"><span class="badge bg-secondary">状態</span> {p1}</div></div></div>
    <div class="col-12 col-md-6"><div class="p-2 rounded border border-secondary"><div class="small text-warning mb-1">プレイヤー2用リンク</div><a href="{l2}">{l2}</a><div class="mt-1"><span class="badge bg-secondary">状態</span> {p2}</div></div></div>
  </div>
  <div class="mt-3 d-flex gap-2">
    <a class="btn btn-primary" href="{url_for('play', room_id=room_id)}">更新</a>
    <a class="btn btn-outline-light" href="{url_for('room_lobby', room_id=room_id)}">ロビーへ</a>
  </div>
  </div>
</div>
"""
        return bootstrap_page("相手待ち", wait_body)

    if room['winner'] is not None:
        return redirect(url_for('end_round', room_id=room_id))

    if room['skip_next_turn'][room['turn']] and room.get('skip_suppress_pid') != room['turn']:
        room['skip_next_turn'][room['turn']] = False
        push_log(room, f"{room['pname'][room['turn']]} のターンは近接トラップ効果でスキップ")
        cur = room['turn']
        switch_turn(room, cur)
        return redirect(url_for('play', room_id=room_id))

    if request.method == 'POST':
        if room['turn'] != pid:
            return redirect(url_for('play', room_id=room_id))
        try:
            action = request.form.get('action')
            if action == 'g':
                guess_val = get_int(request.form, 'guess', None, room['eff_num_min'], room['eff_num_max'])
                if guess_val is None:
                    return push_and_back(room, pid, "⚠ 予想値が不正です。")
                return handle_guess(room, pid, guess_val)

            elif action == 'h':
                return handle_hint(room, pid, request.form)

            elif action == 'c':
                new_secret = get_int(request.form, 'new_secret', None, room['eff_num_min'], room['eff_num_max'])
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
                press_val = get_int(request.form, 'press_guess', None, room['eff_num_min'], room['eff_num_max'])
                if press_val is None:
                    return push_and_back(room, pid, "⚠ サドン・プレスの値が不正です。")
                return handle_press(room, pid, press_val, room_id)

            elif action == 'press_skip':
                return handle_press_skip(room, pid, room_id)

            elif action == 'free_guess':
                fg_val = get_int(request.form, 'free_guess', None, room['eff_num_min'], room['eff_num_max'])
                if fg_val is None:
                    return push_and_back(room, pid, "⚠ 無料予想の値が不正です。")
                return handle_free_guess(room, pid, fg_val, room_id)

            elif action == 'yn':
                return handle_yn(room, pid, request.form)

            elif action == 'devotion_offer':
                return handle_devotion_offer(room, pid)

            elif action == 'devotion_pick':
                pick = request.form.get('pick')
                return handle_devotion_pick(room, pid, pick)

            else:
                return push_and_back(room, pid, "⚠ 不明なアクションです。")

        except Exception:
            app.logger.exception("POST処理中の例外", exc_info=True)
            rid = session.get('room_id') or room_id or get_current_room_id()
            if rid is None:
                return redirect(url_for('index'))
            return redirect(url_for('play', room_id=rid))

    p1, p2 = room['pname'][1], room['pname'][2]
    myname = room['pname'][pid]
    opp   = 2 if pid == 1 else 1
    oppname = room['pname'][opp]

    if request.method == 'GET' and room['turn'] == pid and room.get('guess_flag_warn', {}).get(pid):
        other = 2 if pid == 1 else 1
        push_log(room, f"{room['pname'][pid]} への通知: 実は前のターンに {room['pname'][other]} がゲスフラグを立てていた。危なかった！")
        room['guess_flag_warn'][pid] = False

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

    my_turn_block = ""
    ru = room['rules']
    if room['turn'] == pid:
        if room['free_guess_pending'][pid] and ru.get('decl1', True):
            my_turn_block = f"""
<div class="card mb-3"><div class="card-header">無料予想（嘘だ！成功）</div><div class="card-body">
<form method="post" class="p-2 border rounded">
  <input type="hidden" name="action" value="free_guess">
  <label class="form-label">もう一度だけ無料で予想できます</label>
  <input class="form-control mb-2" name="free_guess" type="number" required min="{room['eff_num_min']}" max="{room['eff_num_max']}" placeholder="{room['eff_num_min']}〜{room['eff_num_max']}">
  <button class="btn btn-primary w-100">予想を送る</button>
  <div class="small text-warning mt-1">※ トラップは有効。±1即死/±5スキップ/info。ゲスフラグは発動しません。</div>
</form></div></div>
"""
        elif room['press_pending'][pid] and ru.get('press', True):
            my_turn_block = f"""
<div class="card mb-3"><div class="card-header">サドン・プレス</div><div class="card-body">
  <form method="post" class="p-2 border rounded mb-2">
    <input type="hidden" name="action" value="press">
    <label class="form-label">もう一回だけ連続で予想</label>
    <input class="form-control mb-2" name="press_guess" type="number" required min="{room['eff_num_min']}" max="{room['eff_num_max']}">
    <button class="btn btn-primary w-100">もう一回だけ予想！</button>
    <div class="small text-warning mt-1">当たれば勝利。外すと次ターンスキップ（このラウンド1回）。</div>
  </form>
  <form method="post" class="p-2 border rounded">
    <input type="hidden" name="action" value="press_skip">
    <button class="btn btn-outline-light w-100">使わないで交代する</button>
  </form>
</div></div>
"""
        else:
            choose_allowed = has_role(room, pid, 'Scholar') or room['hint_choice_available'][pid]
            yn_left = 3 if has_role(room, pid, 'Analyst') else 1
            yn_left -= room['yn_used_count'][pid]
            yn_ct = room['yn_ct'][pid]
            devotion_ok = ru.get('devotion', True) and ru.get('roles', True) and (not room['devotion_used'][pid])

            trap_block = ""
            if ru.get('trap', True):
                trap_block = f"""
  <div class="col-12 col-md-6">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="t">
      <label class="form-label">トラップ</label>
      <input class="form-control mb-2" name="trap_kill_value" type="number" placeholder="killは1つだけ（上書き・ターン消費）">
      <div class="small text-warning">infoは最大{get_info_max(room, pid)}個・無料{room['info_free_per_turn'][pid]}個/ターン。チェックで3個まとめ置き（ターン消費）。</div>
      <input class="form-control mb-2" name="trap_info_value" type="number" placeholder="info(1)">
      <input class="form-control mb-2" name="trap_info_value_1" type="number" placeholder="info(2)">
      <input class="form-control mb-2" name="trap_info_value_2" type="number" placeholder="info(3)">
      <div class="form-check"><input class="form-check-input" type="checkbox" name="info_bulk" value="1" id="info_bulk"><label class="form-check-label" for="info_bulk">infoを3つまとめて置く（ターン消費）</label></div>
      <button class="btn btn-outline-light w-100 mt-2">設定する</button>
    </form>
  </div>
"""

            bluff_block = ""
            if ru.get('bluff', True):
                bluff_block = f"""
  <div class="col-12 col-md-6">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="bh">
      <label class="form-label">ブラフヒント</label>
      <select class="form-select mb-2" name="bluff_type"><option>和</option><option>差</option><option>積</option></select>
      <input class="form-control" type="number" name="bluff_value" placeholder="相手に見せる数値（必須）" required>
      <button class="btn btn-outline-light w-100 mt-2">ブラフを設定（ターン消費）</button>
    </form>
  </div>
"""

            gf_block = ""
            if ru.get('guessflag', True):
                gf_block = f"""
  <div class="col-12 col-md-6">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="gf">
      <label class="form-label">ゲスフラグ</label>
      <div class="small text-warning mb-2">次の相手ターンに予想してきたら相手は即死（各ラウンド1回）</div>
      <button class="btn btn-outline-light w-100" {"disabled" if room['guess_flag_used'][pid] else ""}>立てる</button>
      <div class="small text-warning mt-1">{ "（このラウンドは既に使用）" if room['guess_flag_used'][pid] else "" }</div>
    </form>
  </div>
"""

            decl_block = ""
            if ru.get('decl1', True):
                decl_block = f"""
  <div class="col-12 col-md-6">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="decl1">
      <label class="form-label">一の位を宣言（0〜9）</label>
      <input class="form-control mb-2" name="decl1_digit" type="number" min="0" max="9" {"required" if not room['decl1_used'][pid] else "disabled"} placeholder="0〜9">
      <button class="btn btn-outline-light w-100" {"disabled" if room['decl1_used'][pid] else ""}>宣言（ターン消費なし）</button>
      <div class="small text-warning mt-1">{ "（このラウンドは既に宣言）" if room['decl1_used'][pid] else "以後、無料infoは2個/ターン・最大10個に" }</div>
    </form>
  </div>
"""

            decl_challenge_block = ""
            if (ru.get('decl1', True) and (room['decl1_value'][opp] is not None and not room['decl1_resolved'][opp])):
                decl_challenge_block = f("""
  <div class="col-12 col-md-6">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="decl1_challenge">
      <label class="form-label">相手の宣言にチャレンジ</label>
      <button class="btn btn-outline-light w-100">『嘘だ！』コール</button>
      <div class="small text-warning mt-1">嘘なら正しい一の位公開＋直後に無料予想。真ならあなたは次ターンスキップ。</div>
    </form>
  </div>
""")

            yn_block = ""
            if ru.get('yn', True):
                yn_block = f"""
  <div class="col-12">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="yn">
      <label class="form-label">Yes/No 質問（ターン消費なし）</label>
      <div class="row g-2 align-items-end">
        <div class="col-12 col-md-4">
          <select class="form-select" name="yn_type">
            <option value="ge">相手の数は ≥ X ?</option>
            <option value="le">相手の数は ≤ X ?</option>
            <option value="eq">相手の数は = X ?</option>
            <option value="between">相手の数は [A, B] 内 ?</option>
          </select>
        </div>
        <div class="col-6 col-md-2"><input class="form-control" type="number" name="yn_x" placeholder="X"></div>
        <div class="col-6 col-md-2"><input class="form-control" type="number" name="yn_a" placeholder="A"></div>
        <div class="col-6 col-md-2"><input class="form-control" type="number" name="yn_b" placeholder="B"></div>
        <div class="col-6 col-md-2"><button class="btn btn-outline-light w-100" {"disabled" if yn_left<=0 or yn_ct>0 else ""}>質問する</button></div>
      </div>
      <div class="small text-warning mt-1">残り回数: {max(0, yn_left)}、CT: {yn_ct}（分析屋はラウンド3回/CT2）</div>
    </form>
  </div>
"""

            devotion_block = ""
            if devotion_ok:
                devotion_block = f"""
  <div class="col-12">
    <form method="post" class="p-2 border rounded">
      <input type="hidden" name="action" value="devotion_offer">
      <label class="form-label">二重職：献身（強力・代償あり）</label>
      <button class="btn btn-outline-light w-100">候補3から追加ロールを得る（今ターン終了／g&hにCT1／info上限-2）</button>
    </form>
  </div>
"""

            my_turn_block = f"""
<div class="card mb-3">
  <div class="card-header">アクション</div>
  <div class="card-body">
    <div class="row g-2">
      <div class="col-12 col-md-6">
        <form method="post" class="p-2 border rounded">
          <input type="hidden" name="action" value="g">
          <label class="form-label">相手の数字を予想</label>
          <input class="form-control mb-2" name="guess" type="number" required min="{room['eff_num_min']}" max="{room['eff_num_max']}">
          <button class="btn btn-primary w-100" {"disabled" if room['guess_ct'][pid] > 0 else ""}>予想する</button>
          <div class="small text-warning mt-1">{ "（予想はCT中）" if room['guess_ct'][pid] > 0 else "" }</div>
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
          <div class="small text-warning mt-1">{ "（ヒントはCT中）" if room['hint_ct'][pid] > 0 else "" }</div>
        </form>
      </div>

      <div class="col-12 col-md-6">
        <form method="post" class="p-2 border rounded">
          <input type="hidden" name="action" value="c">
          <label class="form-label">自分の数を変更</label>
          <input class="form-control mb-2" name="new_secret" type="number" required min="{room['eff_num_min']}" max="{room['eff_num_max']}">
          <button class="btn btn-outline-light w-100" {"disabled" if (room['cooldown'][pid] > 0 or room['change_used'][pid] >= 2) else ""}>
            変更する（CT7・ラウンド2回まで）
          </button>
          <div class="small text-warning mt-1">
            このラウンドの使用回数：<span class="value">{room['change_used'][pid]}</span>/2
            { " ／（CT中）" if room['cooldown'][pid] > 0 else "" }
          </div>
        </form>
      </div>

      {trap_block}
      {bluff_block}
      {gf_block}
      {decl_block}
      {decl_challenge_block}
      {yn_block}
      {devotion_block}
    </div>
  </div>
</div>
"""

    my_role = role_label(room['role_main'][pid]) if room['rules'].get('roles', True) else '—'
    extra_role = role_label(room['role_extra'][pid]) if room['rules'].get('roles', True) else '—'
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
        <div class="mb-1"><span class="badge bg-secondary">ロール</span> <span class="value">{my_role}</span>{ " ＋ " + extra_role if room['role_extra'][pid] else "" }</div>
        <div class="mb-1"><span class="badge bg-secondary">トラップ</span><br>
        {("<span class='small text-warning'>A(kill): <span class='value'>" + (", ".join(map(str, room['trap_kill'][pid])) if room['trap_kill'][pid] else "なし") + "</span></span><br><span class='small text-warning'>B(info): <span class='value'>" + (", ".join(map(str, room['trap_info'][pid])) if room['trap_info'][pid] else "なし") + f"</span></span><br><span class='small text-warning'>info最大: <span class='value'>{get_info_max(room, pid)}</span></span>") if room['rules'].get('trap', True) else "<span class='small text-warning'>このルームでは無効</span>" }
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

<script>
(function(){ 
  const mypid = {pid};
  let lastSerial = {room['turn_serial']};
  async function check(){ 
    try{ 
      const r = await fetch("{url_for('poll', room_id=room_id)}", {cache:"no-store"});
      const j = await r.json();
      if(j.phase !== "play" || j.winner !== null){ 
        location.reload();
        return;
      }
      if(j.serial !== lastSerial && (j.turn === mypid)){ 
        location.reload();
        return;
      }
      lastSerial = j.serial;
    }catch(e){}
  }
  setInterval(check, 1200);
})();
</script>
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

# ====== アクション処理 ======
def _hint_once(room, pid, chose_by_user=False, silent=False, chosen_type=None):
    opp = 2 if pid == 1 else 1
    opp_secret = room['secret'][opp]
    hidden = room['hidden']
    if chosen_type in ('和','差','積'):
        htype = chosen_type
        stock = room['available_hints'][pid]
        if htype in stock:
            stock.remove(htype)
    else:
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

    shown = _apply_trickster_noise(room, pid, val)

    if not silent:
        myname = room['pname'][pid]
        # 3) ログから種類が分からないよう、値のみ記録
        push_log(room, f"{myname} が h（ヒント取得）＝{shown}")
    return

def _compute_hint_value(room, pid, htype):
    opp = 2 if pid == 1 else 1
    opp_secret = room['secret'][opp]
    hidden = room['hidden']
    if htype == '和':
        return opp_secret + hidden
    elif htype == '差':
        return abs(opp_secret - hidden)
    else:
        return opp_secret * hidden

def handle_guess(room, pid, guess):
    opp = 2 if pid == 1 else 1
    myname = room['pname'][pid]
    opponent_secret = room['secret'][opp]

    if room['guess_ct'][pid] > 0:
        push_log(room, "（予想はCT中）")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    room['tries'][pid] += 1

    if room['rules'].get('guessflag', True) and room['guess_flag_armed'][opp]:
        room['guess_flag_armed'][opp] = False
        push_log(room, f"（{room['pname'][opp]} のゲスフラグが発動！{room['pname'][pid]} は即死）")
        room['score'][opp] += 1
        room['winner'] = opp
        room['turn_serial'] += 1
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    if guess == opponent_secret:
        push_log(room, f"{myname} が g（予想）→ {guess}（正解！相手は即死）")
        room['score'][pid] += 1
        room['winner'] = pid
        room['turn_serial'] += 1
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    kill = set(room['trap_kill'][opp]) if room['rules'].get('trap', True) else set()
    info = set(room['trap_info'][opp]) if room['rules'].get('trap', True) else set()

    if any(abs(guess - k) <= 1 for k in kill):
        push_log(room, f"{myname} が g（予想）→ {guess}（killトラップ±1命中＝即敗北）")
        room['score'][opp] += 1
        room['winner'] = opp
        room['turn_serial'] += 1
        return redirect(url_for('end_round', room_id=get_current_room_id()))

    if guess in info:
        room['pending_view'][opp] = True
        room['view_cut_index'][opp] = len(room['actions'])
        push_log(room, f"{myname} が g（予想）→ {guess}（情報トラップ発動）")

    if any(abs(guess - k) <= 5 for k in kill):
        set_skip(room, pid)
        push_log(room, f"{myname} が g（予想）→ {guess}（kill近接±5命中：次ターンスキップ）")
        if room['guess_penalty_active'][pid]:
            room['guess_ct'][pid] = 1
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    push_log(room, f"{myname} が g（予想）→ {guess}（ハズレ）")
    if room['rules'].get('press', True) and (not room['press_used'][pid]) and (not room['press_pending'][pid]):
        room['press_pending'][pid] = True
        return redirect(url_for('play', room_id=get_current_room_id()))

    if room['guess_penalty_active'][pid]:
        room['guess_ct'][pid] = 1
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_hint(room, pid, form):
    myname = room['pname'][pid]
    opp = 2 if pid == 1 else 1

    if room['hint_ct'][pid] > 0:
        push_log(room, "（ヒントはCT中）")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    want_choose = bool(form.get('confirm_choice'))
    choose_type = form.get('hint_type')

    if has_role(room, pid, 'Scholar'):
        want_choose = True
        if choose_type not in ('和','差','積'):
            choose_type = random.choice(['和','差','積'])

    decision = form.get('bluff_decision')
    has_bluff_flag = bool(room['bluff'][opp])

    # === 確認画面 ===
    if not decision:
        allow_choose_now = (has_role(room, pid, 'Scholar') or (want_choose and room['hint_choice_available'][pid])) and choose_type in ('和','差','積')

        keep = ""
        if want_choose:
            keep += "<input type='hidden' name='confirm_choice' value='1'>"
        if want_choose and choose_type:
            keep += f"<input type='hidden' name='hint_type' value='{choose_type}'>"

        # 2) ブラフ確認画面では「値のみ」を出す（種類は非表示）
        if has_bluff_flag:
            fake = room['bluff'][opp]
            shown_val = fake['value']
            body = f"""
<div class="card"><div class="card-header">ヒント（確認）</div><div class="card-body">
  <p class="mb-2">提示されたヒント（相手からの表示）</p>
  <div class="p-2 rounded border border-secondary mb-3">
    <div>値　：<span class="badge bg-warning text-dark">{shown_val}</span></div>
  </div>
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
  <div class="mt-3"><a class="btn btn-outline-light" href="{url_for('play', room_id=get_current_room_id())}">戻る</a></div>
</div></div>
"""
            return bootstrap_page("ヒント確認", body)
        else:
            # ブラフなしでも、プレビューは値のみ表示（種類は伏せる）
            if allow_choose_now:
                preview_type = choose_type
            else:
                stock = room['available_hints'][pid]
                if stock:
                    preview_type = random.choice(stock)
                else:
                    preview_type = random.choice(['和','差','積'])

            true_val = _compute_hint_value(room, pid, preview_type)
            shown_val = _apply_trickster_noise(room, pid, true_val)

            body = f"""
<div class="card"><div class="card-header">ヒント（確認）</div><div class="card-body">
  <p class="mb-2">今回あなたに表示されるヒント（プレビュー）</p>
  <div class="p-2 rounded border border-secondary mb-3">
    <div>値　：<span class="badge bg-warning text-dark">{shown_val}</span></div>
  </div>
  <p class="mb-3">このヒントはブラフだと思いますか？</p>
  <form method="post" class="d-inline me-2">
    <input type="hidden" name="action" value="h">
    <input type="hidden" name="bluff_decision" value="believe">
    {keep}
    <input type="hidden" name="preview_type" value="{preview_type}">
    <input type="hidden" name="preview_val" value="{shown_val}">
    <button class="btn btn-primary">このヒントを受け取る</button>
  </form>
  <form method="post" class="d-inline">
    <input type="hidden" name="action" value="h">
    <input type="hidden" name="bluff_decision" value="accuse">
    {keep}
    <button class="btn btn-outline-light">ブラフだ！と指摘する</button>
  </form>
  <div class="mt-3"><a class="btn btn-outline-light" href="{url_for('play', room_id=get_current_room_id())}">戻る</a></div>
</div></div>
"""
            return bootstrap_page("ヒント確認", body)

    # === 意思決定後 ===
    if has_bluff_flag:
        if decision == 'believe':
            push_log(room, f"{myname} は 提示ヒント（{room['bluff'][opp]['value']}）を受け入れた")
            room['bluff'][opp] = None
            if room['hint_penalty_active'][pid] and not has_role(room, pid, 'Scholar'):
                room['hint_ct'][pid] = 1
            switch_turn(room, pid)
            return redirect(url_for('play', room_id=get_current_room_id()))
        else:
            _hint_once(room, pid, chose_by_user=False, silent=False, chosen_type=None)
            _hint_once(room, pid, chose_by_user=False, silent=False, chosen_type=None)
            room['bluff'][opp] = None
            if room['hint_penalty_active'][pid] and not has_role(room, pid, 'Scholar'):
                room['hint_ct'][pid] = 1
            switch_turn(room, pid)
            return redirect(url_for('play', room_id=get_current_room_id()))
    else:
        if decision == 'accuse':
            room['hint_penalty_active'][pid] = True
            if has_role(room, opp, 'Trickster'):
                room['hint_ct'][pid] = 2
                push_log(room, f"{myname} は ブラフだと指摘したが外れ（以後ヒント取得後はCT2）")
            else:
                room['hint_ct'][pid] = 1
                push_log(room, f"{myname} は ブラフだと指摘したが外れ（以後ヒント取得後はCT1）")
            switch_turn(room, pid)
            return redirect(url_for('play', room_id=get_current_room_id()))
        else:
            prev_type = form.get('preview_type')
            prev_val_s = form.get('preview_val')
            try:
                prev_val = int(prev_val_s) if prev_val_s is not None else None
            except:
                prev_val = None

            allow_choose_now = (has_role(room, pid, 'Scholar') or (want_choose and room['hint_choice_available'][pid])) and choose_type in ('和','差','積')
            if not prev_type or prev_type not in ('和','差','積') or prev_val is None:
                if allow_choose_now and not has_role(room, pid, 'Scholar'):
                    room['hint_choice_available'][pid] = False
                _hint_once(room, pid, chose_by_user=allow_choose_now, silent=False,
                           chosen_type=choose_type if allow_choose_now else None)
            else:
                stock = room['available_hints'][pid]
                if prev_type in stock:
                    stock.remove(prev_type)
                if (not has_role(room, pid, 'Scholar')) and want_choose and room['hint_choice_available'][pid] and choose_type in ('和','差','積'):
                    room['hint_choice_available'][pid] = False
                # 3) 種類は出さず、値のみログ
                push_log(room, f"{myname} が h（ヒント取得）＝{prev_val}")

            if room['hint_penalty_active'][pid] and not has_role(room, pid, 'Scholar'):
                room['hint_ct'][pid] = 1
            switch_turn(room, pid)
            return redirect(url_for('play', room_id=get_current_room_id()))

def handle_change(room, pid, new_secret):
    myname = room['pname'][pid]
    if room['cooldown'][pid] > 0:
        push_log(room, "（自分の数の変更はCT中）")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    my_traps = set(room['trap_kill'][pid]) | set(room['trap_info'][pid])
    if new_secret in my_traps or (room['allow_negative'] and any(abs(new_secret) == abs(t) for t in my_traps)):
        push_log(room, "⚠ その数字は現在のトラップに含まれています。別の数字を選んでください。")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    if not (room['eff_num_min'] <= new_secret <= room['eff_num_max']):
        push_log(room, "⚠ 範囲外の数字です。")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    if room['change_used'][pid] >= 2:
        push_log(room, "（このラウンドでの自分の数の変更は2回まで）")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    room['secret'][pid] = new_secret
    room['cooldown'][pid] = 7
    room['change_used'][pid] += 1

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
    try:
        x = int(v)
    except Exception:
        push_log(room, "⚠ 無効なkillトラップ値です。")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    if not (eff_min <= x <= eff_max) or x == my_secret or (room['allow_negative'] and abs(x) == abs(my_secret)):
        push_log(room, "⚠ 無効なkillトラップ値です。")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))
    room['trap_kill'][pid].clear()
    room['trap_kill'][pid].append(x)
    push_log(room, f"{myname} が killトラップを {x} に設定")
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
    bulk = form.get('info_bulk') in ('1', 'on', 'true', 'True')

    if bulk:
        candidates = ('trap_info_value', 'trap_info_value_1', 'trap_info_value_2', 'trap_info_val')
        added_list = []
        for key in candidates:
            v = form.get(key)
            if not v:
                continue
            try:
                x = int(v)
            except Exception:
                continue
            if not (eff_min <= x <= eff_max):
                continue
            if x == my_secret or (room['allow_negative'] and abs(x) == abs(my_secret)):
                continue
            if x in room['trap_info'][pid] or x in added_list:
                continue
            if len(room['trap_info'][pid]) >= max_allowed:
                break
            added_list.append(x)

        if added_list:
            room['trap_info'][pid].extend(added_list)
            push_log(room, f"{myname} が infoトラップをまとめて設定 → {', '.join(map(str, added_list))}（ターン消費）")
            switch_turn(room, pid)
        else:
            push_log(room, "⚠ infoトラップの追加はありません。")
        return redirect(url_for('play', room_id=get_current_room_id()))

    # 非まとめ置き：無料枠ぶん“複数”一度に追加（ターン消費なし）
    left = max(0, free_cap - free_used)
    if left <= 0:
        push_log(room, f"（このターンの無料infoは上限 {free_cap} 個に達しています）")
        return redirect(url_for('play', room_id=get_current_room_id()))

    candidates = ('trap_info_value', 'trap_info_value_1', 'trap_info_value_2', 'trap_info_val')
    seen = set(room['trap_info'][pid])
    added_list = []
    for key in candidates:
        v = form.get(key)
        if not v:
            continue
        try:
            x = int(v)
        except Exception:
            continue
        if len(room['trap_info'][pid]) + len(added_list) >= max_allowed:
            break
        if len(added_list) >= left:
            break
        if not (eff_min <= x <= eff_max):
            continue
        if x == my_secret or (room['allow_negative'] and abs(x) == abs(my_secret)):
            continue
        if x in seen or x in added_list:
            continue
        added_list.append(x)

    if added_list:
        room['trap_info'][pid].extend(added_list)
        room['info_free_used_this_turn'][pid] += len(added_list)
        left_after = max(0, free_cap - room['info_free_used_this_turn'][pid])
        label = "複数を" if len(added_list) >= 2 else "1つを"
        push_log(room, f"{myname} が infoトラップを{label}設定 → {', '.join(map(str, added_list))}（ターン消費なし／このターンはあと {left_after} 個）")
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
    did_anything = False

    v = form.get('trap_kill_value')
    if v not in (None, ''):
        try:
            x = int(v)
        except Exception:
            x = None
        if x is not None and (eff_min <= x <= eff_max) and (x != my_secret) and (not (room['allow_negative'] and abs(x) == abs(my_secret))):
            room['trap_kill'][pid].clear()
            room['trap_kill'][pid].append(x)
            push_log(room, f"{myname} が killトラップを {x} に設定")
            turn_consumed = True
            did_anything = True
        else:
            push_log(room, "⚠ 無効なkillトラップ値です。")

    max_allowed = get_info_max(room, pid)
    free_cap   = room['info_free_per_turn'][pid]
    free_used  = room['info_free_used_this_turn'][pid]
    bulk = form.get('info_bulk') in ('1','on','true','True')

    info_keys = ('trap_info_value', 'trap_info_value_1', 'trap_info_value_2', 'trap_info_val')
    raw_inputs = []
    for k in info_keys:
        vs = form.get(k)
        if vs is None or vs == '':
            continue
        try:
            raw_inputs.append(int(vs))
        except Exception:
            continue
    seen = set()
    info_inputs_unique = []
    for x in raw_inputs:
        if x not in seen:
            seen.add(x)
            info_inputs_unique.append(x)

    if bulk and info_inputs_unique:
        added = []
        for x in info_inputs_unique:
            if not (eff_min <= x <= eff_max):
                continue
            if x == my_secret or (room['allow_negative'] and abs(x) == abs(my_secret)):
                continue
            if x in room['trap_info'][pid] or x in added:
                continue
            if len(room['trap_info'][pid]) >= max_allowed:
                break
            added.append(x)
        if added:
            room['trap_info'][pid].extend(added)
            push_log(room, f"{myname} が infoトラップをまとめて設定 → {', '.join(map(str, added))}（ターン消費）")
            turn_consumed = True
            did_anything = True
        else:
            push_log(room, "⚠ infoトラップの追加はありません。")

    elif (not bulk) and info_inputs_unique:
        left = max(0, free_cap - free_used)
        if left <= 0:
            push_log(room, f"（このターンの無料infoは上限 {free_cap} 個に達しています）")
        else:
            added = []
            already = set(room['trap_info'][pid])
            for x in info_inputs_unique:
                if len(room['trap_info'][pid]) + len(added) >= max_allowed:
                    break
                if len(added) >= left:
                    break
                if not (eff_min <= x <= eff_max):
                    continue
                if x == my_secret or (room['allow_negative'] and abs(x) == abs(my_secret)):
                    continue
                if x in already or x in added:
                    continue
                added.append(x)
            if added:
                room['trap_info'][pid].extend(added)
                room['info_free_used_this_turn'][pid] += len(added)
                left_after = max(0, free_cap - room['info_free_used_this_turn'][pid])
                label = "複数を" if len(added) >= 2 else "1つを"
                push_log(room, f"{myname} が infoトラップを{label}設定 → {', '.join(map(str, added))}（ターン消費なし／このターンはあと {left_after} 個）")
                did_anything = True
            else:
                push_log(room, "⚠ infoトラップの追加はありません。")

    if turn_consumed:
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=get_current_room_id()))

    if did_anything:
        return redirect(url_for('play', room_id=get_current_room_id()))

    push_log(room, "⚠ トラップの追加はありません。")
    return redirect(url_for('play', room_id=get_current_room_id()))

# ====== ここから追加/修正ハンドラ ======
def handle_bluff(room, pid, form):
    if not room['rules'].get('bluff', True):
        return push_and_back(room, pid, "（このルームではブラフは無効です）")

    myname = room['pname'][pid]
    t = form.get('bluff_type', '和')
    if t not in ('和', '差', '積'):
        t = '和'

    vs = form.get('bluff_value')
    try:
        val = int(vs)
    except Exception:
        push_log(room, "⚠ ブラフ値が不正です。")
        return redirect(url_for('play', room_id=get_current_room_id()))

    room['bluff'][pid] = {'type': t, 'value': val}
    # 種類は公開しない
    push_log(room, f"{myname} が ブラフヒントを仕掛けた")

    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_yn(room, pid, form):
    if not room['rules'].get('yn', True):
        return push_and_back(room, pid, "（このルームではYes/No質問は無効です）")

    myname = room['pname'][pid]
    opp = 2 if pid == 1 else 1

    limit = 3 if has_role(room, pid, 'Analyst') else 1
    if room['yn_used_count'][pid] >= limit:
        push_log(room, "（このラウンドのYes/No質問回数は上限です）")
        return redirect(url_for('play', room_id=get_current_room_id()))

    if has_role(room, pid, 'Analyst'):
        if room['yn_ct'][pid] > 0 or room['yn_last_tick'][pid] == room['tick']:
            push_log(room, "（質問は今はできません：CT中または同一ターン連打不可）")
            return redirect(url_for('play', room_id=get_current_room_id()))

    t = form.get('yn_type', 'ge')
    sx = form.get('yn_x')
    sa = form.get('yn_a')
    sb = form.get('yn_b')

    try:
        x = int(sx) if sx not in (None, '') else None
    except Exception:
        x = None
    try:
        a = int(sa) if sa not in (None, '') else None
    except Exception:
        a = None
    try:
        b = int(sb) if sb not in (None, '') else None
    except Exception:
        b = None

    target = room['secret'][opp]
    res = False
    desc = ""

    if t == 'ge' and x is not None:
        res = (target >= x)
        desc = f"≥ {x}"
    elif t == 'le' and x is not None:
        res = (target <= x)
        desc = f"≤ {x}"
    elif t == 'eq' and x is not None:
        res = (target == x)
        desc = f"= {x}"
    elif t == 'between' and a is not None and b is not None:
        lo, hi = (a, b) if a <= b else (b, a)
        res = (lo <= target <= hi)
        desc = f"[{lo}, {hi}] 内"
    else:
        push_log(room, "⚠ 質問のパラメータが不正です。")
        return redirect(url_for('play', room_id=get_current_room_id()))

    ans = "はい" if res else "いいえ"
    push_log(room, f"{myname} が yn（{desc}？）→ {ans}")

    room['yn_used_count'][pid] += 1
    if has_role(room, pid, 'Analyst'):
        room['yn_ct'][pid] = 2
        room['yn_last_tick'][pid] = room['tick']

    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_decl1(room, pid, form):
    if not room['rules'].get('decl1', True):
        return push_and_back(room, pid, "（このルームでは一の位の宣言は無効です）")

    myname = room['pname'][pid]

    if room['decl1_used'][pid]:
        push_log(room, "（このラウンドは既に宣言しています）")
        return redirect(url_for('play', room_id=get_current_room_id()))

    ds = form.get('decl1_digit')
    try:
        d = int(ds)
    except Exception:
        push_log(room, "⚠ 一の位は 0〜9 の整数で入力してください。")
        return redirect(url_for('play', room_id=get_current_room_id()))
    if not (0 <= d <= 9):
        push_log(room, "⚠ 一の位は 0〜9 の整数で入力してください。")
        return redirect(url_for('play', room_id=get_current_room_id()))

    room['decl1_value'][pid] = d
    room['decl1_used'][pid] = True
    room['decl1_resolved'][pid] = False

    room['info_free_per_turn'][pid] = 2
    room['info_max'][pid] = 10
    room['info_free_used_this_turn'][pid] = min(room['info_free_used_this_turn'][pid], room['info_free_per_turn'][pid])

    push_log(room, f"{myname} が 一の位を宣言：{d}（ターン消費なし）")
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_decl1_challenge(room, pid):
    if not room['rules'].get('decl1', True):
        return push_and_back(room, pid, "（このルームでは一の位の宣言/チャレンジは無効です）")

    myname = room['pname'][pid]
    opp = 2 if pid == 1 else 1

    if room['decl1_value'][opp] is None or room['decl1_resolved'][opp]:
        push_log(room, "（現在、挑戦できる宣言はありません）")
        return redirect(url_for('play', room_id=get_current_room_id()))

    true_digit = abs(room['secret'][opp]) % 10
    declared = room['decl1_value'][opp]

    if declared == true_digit:
        room['decl1_resolved'][opp] = True
        set_skip(room, pid)
        push_log(room, f"{myname} は『嘘だ！』→ 失敗。正しい一の位は {true_digit}。あなたは次ターンスキップ。")
    else:
        room['decl1_resolved'][opp] = True
        room['free_guess_pending'][pid] = True
        room['skip_suppress_pid'] = pid
        push_log(room, f"{myname} は『嘘だ！』→ 成功！ 相手の正しい一の位は {true_digit}。直後に無料予想が可能。")

    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_press(room, pid, press_guess, room_id):
    if not room['rules'].get('press', True) or not room['press_pending'][pid] or room['press_used'][pid]:
        return push_and_back(room, pid, "（このラウンドのサドン・プレスは使えません）")
    room['press_pending'][pid] = False
    room['press_used'][pid] = True

    opp = 2 if pid == 1 else 1
    myname = room['pname'][pid]
    opponent_secret = room['secret'][opp]

    room['tries'][pid] += 1

    if press_guess == opponent_secret:
        push_log(room, f"{myname} が press（追加予想）→ {press_guess}（正解！相手は即死）")
        room['score'][pid] += 1
        room['winner'] = pid
        room['turn_serial'] += 1
        return redirect(url_for('end_round', room_id=room_id))

    kill = set(room['trap_kill'][opp]) if room['rules'].get('trap', True) else set()
    info = set(room['trap_info'][opp]) if room['rules'].get('trap', True) else set()

    if any(abs(press_guess - k) <= 1 for k in kill):
        push_log(room, f"{myname} が press（追加予想）→ {press_guess}（killトラップ±1命中＝即敗北）")
        room['score'][opp] += 1
        room['winner'] = opp
        room['turn_serial'] += 1
        return redirect(url_for('end_round', room_id=room_id))

    if press_guess in info:
        room['pending_view'][opp] = True
        room['view_cut_index'][opp] = len(room['actions'])
        push_log(room, f"{myname} が press（追加予想）→ {press_guess}（情報トラップ発動）")

    if any(abs(press_guess - k) <= 5 for k in kill):
        set_skip(room, pid)
        push_log(room, f"{myname} が press（追加予想）→ {press_guess}（kill近接±5命中：次ターンスキップ）")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=room_id))

    push_log(room, f"{myname} が press（追加予想）→ {press_guess}（ハズレ：次ターンスキップ）")
    set_skip(room, pid)
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=room_id))

def handle_press_skip(room, pid, room_id):
    if not room['press_pending'][pid]:
        return push_and_back(room, pid, "（いまはプレス待機中ではありません）")
    room['press_pending'][pid] = False
    room['press_used'][pid] = True
    push_log(room, f"{room['pname'][pid]} は サドン・プレスを見送った")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=room_id))

def handle_free_guess(room, pid, val, room_id):
    if not room['free_guess_pending'][pid]:
        return push_and_back(room, pid, "（無料予想は現在できません）")
    room['free_guess_pending'][pid] = False

    opp = 2 if pid == 1 else 1
    myname = room['pname'][pid]
    opponent_secret = room['secret'][opp]

    room['tries'][pid] += 1

    if val == opponent_secret:
        push_log(room, f"{myname} が 無料予想 → {val}（正解！相手は即死）")
        room['score'][pid] += 1
        room['winner'] = pid
        room['turn_serial'] += 1
        return redirect(url_for('end_round', room_id=room_id))

    kill = set(room['trap_kill'][opp]) if room['rules'].get('trap', True) else set()
    info = set(room['trap_info'][opp]) if room['rules'].get('trap', True) else set()

    if any(abs(val - k) <= 1 for k in kill):
        push_log(room, f"{myname} が 無料予想 → {val}（killトラップ±1命中＝即敗北）")
        room['score'][opp] += 1
        room['winner'] = opp
        room['turn_serial'] += 1
        return redirect(url_for('end_round', room_id=room_id))

    if val in info:
        room['pending_view'][opp] = True
        room['view_cut_index'][opp] = len(room['actions'])
        push_log(room, f"{myname} が 無料予想 → {val}（情報トラップ発動）")

    if any(abs(val - k) <= 5 for k in kill):
        set_skip(room, pid)
        push_log(room, f"{myname} が 無料予想 → {val}（kill近接±5命中：次ターンスキップ）")
        switch_turn(room, pid)
        return redirect(url_for('play', room_id=room_id))

    push_log(room, f"{myname} が 無料予想 → {val}（ハズレ）")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=room_id))

def handle_guessflag(room, pid):
    if not room['rules'].get('guessflag', True):
        return push_and_back(room, pid, "（このルームではゲスフラグは無効です）")
    if room['guess_flag_used'][pid]:
        return push_and_back(room, pid, "（このラウンドのゲスフラグは既に使用済みです）")
    room['guess_flag_armed'][pid] = True
    room['guess_flag_used'][pid] = True
    push_log(room, f"{room['pname'][pid]} が ゲスフラグを立てた（次の相手ターンで予想すると即死）")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

def handle_devotion_offer(room, pid):
    if not (room['rules'].get('devotion', True) and room['rules'].get('roles', True)):
        return push_and_back(room, pid, "（このルームでは献身は無効です）")
    if room['devotion_used'][pid]:
        return push_and_back(room, pid, "（このラウンドでは既に献身を使いました）")

    keys = list(ROLES.keys())
    offers = random.sample(keys, 3) if len(keys) >= 3 else [random.choice(keys) for _ in range(3)]
    room['devotion_offers'][pid] = offers

    def opt(label_code):
        label = role_label(label_code)
        return f"""
<form method="post" class="d-inline me-2">
  <input type="hidden" name="action" value="devotion_pick">
  <input type="hidden" name="pick" value="{label_code}">
  <button class="btn btn-primary">{label}</button>
</form>"""
    buttons = "".join(opt(c) for c in offers)
    body = f"""
<div class="card"><div class="card-header">二重職：献身</div><div class="card-body">
  <p class="mb-2">以下から追加ロールを1つ選んでください（このラウンド限定）。</p>
  <div class="mb-3">{buttons}</div>
  <div class="small text-warning">選ぶと今ターンは終了し、以後このラウンド中は g/h にCT1、さらにあなたの info上限が -2 されます。</div>
  <div class="mt-3"><a class="btn btn-outline-light" href="{url_for('play', room_id=get_current_room_id())}">戻る</a></div>
</div></div>
"""
    return bootstrap_page("献身 - 候補選択", body)

def handle_devotion_pick(room, pid, pick):
    if not room['devotion_offers'][pid] or pick not in room['devotion_offers'][pid]:
        return push_and_back(room, pid, "（無効な選択です）")
    room['role_extra'][pid] = pick
    room['devotion_used'][pid] = True
    room['devotion_offers'][pid] = None
    room['guess_ct'][pid] = 1
    room['hint_ct'][pid] = 1
    room['devotion_info_penalty'][pid] = 2
    push_log(room, f"{room['pname'][pid]} が 献身で『{role_label(pick)}』を得た（今ターン終了／g&hにCT1／info上限-2）")
    switch_turn(room, pid)
    return redirect(url_for('play', room_id=get_current_room_id()))

if __name__ == '__main__':
    # app.config.update(SESSION_COOKIE_SECURE=False)
    app.run(host="0.0.0.0", port=5000, debug=True)
